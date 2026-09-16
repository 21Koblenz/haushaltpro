const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {IDBFactory}=require('fake-indexeddb');
const source=fs.readFileSync('static/offline-sync.js','utf8');
function harness({idb=new IDBFactory(),fetch=async()=>{throw new TypeError('Network down')},fastTimeout=false}={}){
  const elements=Object.fromEntries(['connectionStatus','connectionText','connectionQueue'].map(id=>[id,{textContent:'',hidden:false,classes:new Set(),attributes:{},addEventListener(){},setAttribute(k,v){this.attributes[k]=v}}]));
  for(const e of Object.values(elements))e.classList={add(x){e.classes.add(x)},remove(...xs){xs.forEach(x=>e.classes.delete(x))}};
  const state={ctx:{csrf:'csrf-a',bookId:'book-a',username:'Alice'},fetch,events:[],elements,idb};
  const win={HaushaltProSyncContext:()=>state.ctx,addEventListener(){},dispatchEvent:e=>state.events.push(e)};
  vm.runInNewContext(source,{
    window:win,document:{readyState:'loading',hidden:false,addEventListener(){},getElementById:id=>elements[id]},
    indexedDB:idb,navigator:{onLine:true},location:{origin:'http://localhost'},localStorage:{getItem:()=>null},
    Headers,URL,FormData,AbortController,CustomEvent,crypto:require('node:crypto').webcrypto,
    setTimeout:fastTimeout?(fn,ms)=>setTimeout(fn,Math.min(ms,2)):setTimeout,clearTimeout,setInterval(){},
    fetch:(...args)=>state.fetch(...args)
  });
  state.api=win.HaushaltProOffline;return state;
}
const input={method:'POST',body:JSON.stringify({amount:'12.34',account_id:1,booking_date:'2026-09-16'})};
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'Content-Type':'application/json'}});

test('offline draft survives reload and sync uses original ID with fresh CSRF',async()=>{
  const h=harness();const queued=await h.api.request('/api/transactions',input,h.ctx);
  assert.equal(queued.queued,true);assert.equal((await h.api.pending()).length,1);
  assert.equal(h.elements.connectionText.textContent,'Keine Verbindung');
  const requests=[];const next=harness({idb:h.idb,fetch:async(u,o)=>{requests.push([u,o]);return json({id:42})}});
  next.ctx.csrf='fresh';await next.api.sync();
  assert.equal((await next.api.pending()).length,0);assert.equal(requests.length,1);
  const headers=requests[0][1].headers;
  assert.equal(headers.get('X-Idempotency-Key'),queued.id);assert.equal(headers.get('X-CSRF-Token'),'fresh');
  assert.equal(headers.get('X-HaushaltPro-Book'),'book-a');assert.equal(headers.get('X-HaushaltPro-User'),'Alice');
  assert.equal(requests[0][1].body,input.body);
});

test('lost success response is retried exactly once with the same server identity',async()=>{
  const ids=new Map();let first=true;
  const h=harness({fetch:async(u,o)=>{const key=o.headers.get('X-Idempotency-Key');if(!ids.has(key))ids.set(key,ids.size+1);if(first){first=false;throw new TypeError('reply lost')}return json({id:ids.get(key)})}});
  const result=await h.api.request('/api/transactions',input,h.ctx);assert.equal(result.queued,true);
  await Promise.all([h.api.sync(),h.api.sync(),h.api.sync()]);
  assert.equal(ids.size,1);assert.equal((await h.api.pending()).length,0);
});

test('other users and books cannot replay a queued entry; 401 retains it',async()=>{
  const h=harness();await h.api.request('/api/transfers',input,h.ctx);let calls=0;
  h.fetch=async()=>{calls++;return json({detail:'expired'},401)};
  h.ctx={...h.ctx,username:'Bob'};await h.api.sync();assert.equal(calls,0);
  h.ctx={...h.ctx,username:'Alice',bookId:'book-b'};await h.api.sync();assert.equal(calls,0);
  h.ctx={...h.ctx,bookId:'book-a'};await h.api.sync();assert.equal(calls,1);assert.equal((await h.api.pending()).length,1);
  h.ctx.csrf='renewed';h.fetch=async()=>json({id:8});await h.api.sync();assert.equal((await h.api.pending()).length,0);
});

test('5xx queues, status probes validate JSON, reconnect flushes automatically',async()=>{
  const h=harness({fetch:async()=>json({detail:'down'},503)});assert.equal((await h.api.request('/api/recurring',input,h.ctx)).queued,true);
  assert.equal(h.elements.connectionText.textContent,'Keine Verbindung');
  h.fetch=async()=>new Response('<html>Proxy login</html>');await h.api.ping();
  assert.equal(h.elements.connectionText.textContent,'Keine Verbindung');assert.equal((await h.api.pending()).length,1);
  h.fetch=async u=>u==='/api/status'?json({version:'test',initialized:true}):json({id:9});await h.api.ping();
  assert.equal(h.elements.connectionText.textContent,'Server verbunden');assert.equal((await h.api.pending()).length,0);
});

test('validation failures keep the form open; rejected queued writes require manual retry',async()=>{
  const h=harness({fetch:async()=>json({detail:'bad category'},422)});
  const res=await h.api.request('/api/transactions',input,h.ctx);assert.equal(res.response.status,422);assert.equal((await h.api.pending()).length,0);
  h.fetch=async()=>{throw new TypeError('offline')};await h.api.request('/api/transactions',input,h.ctx);
  let calls=0;h.fetch=async()=>{calls++;return json({detail:'category deleted'},422)};
  await h.api.sync();await h.api.sync();assert.equal(calls,1);assert.equal((await h.api.pending()).length,1);
  h.fetch=async()=>{calls++;return json({id:4})};await h.api.sync(true);assert.equal(calls,2);assert.equal((await h.api.pending()).length,0);
});

test('IndexedDB commit failure is never reported as saved or sent',async()=>{
  const idb=new IDBFactory();const original=idb.open.bind(idb);
  idb.open=(...args)=>{const req=original(...args);req.addEventListener('success',()=>{
    const db=req.result,transaction=db.transaction.bind(db);
    db.transaction=(...args)=>{const tx=transaction(...args);if(args[1]==='readwrite'){
      const objectStore=tx.objectStore.bind(tx);tx.objectStore=name=>{const store=objectStore(name),put=store.put.bind(store);store.put=(...args)=>{const r=put(...args);r.addEventListener('success',()=>tx.abort());return r};return store};
    }return tx};
  });return req};
  let calls=0;const h=harness({idb,fetch:async()=>{calls++;return json({id:1})}});
  await assert.rejects(h.api.request('/api/transactions',input,h.ctx));assert.equal(calls,0);assert.equal((await h.api.pending()).length,0);
});

test('ordinary GET responses do not reopen or read IndexedDB',async()=>{
  const idb=new IDBFactory();let opens=0;const original=idb.open.bind(idb);idb.open=(...args)=>{opens++;return original(...args)};
  const h=harness({idb,fetch:async()=>json({accounts:[]})});
  for(let i=0;i<20;i++)await h.api.request('/api/accounts',{},h.ctx);
  assert.equal(opens,0);
});

test('open items and partial payments survive a lost reply and replay once',async()=>{
  for(const url of ['/api/open-items','/api/open-items/7/payments']){
    const seen=new Set();let lost=true;
    const h=harness({fetch:async(u,opt)=>{
      seen.add(new Headers(opt.headers).get('X-Idempotency-Key'));
      if(lost){lost=false;throw new TypeError('reply lost')}
      return json({id:12});
    }});
    assert.equal((await h.api.request(url,input,h.ctx)).queued,true);
    await h.api.sync();
    assert.equal(seen.size,1);assert.equal((await h.api.pending()).length,0);
  }
});

test('unresponsive writes time out without losing the persisted draft',async()=>{
  const h=harness({fastTimeout:true,fetch:(url,opt)=>new Promise((resolve,reject)=>opt.signal.addEventListener('abort',()=>reject(new Error('timeout'))))});
  assert.equal((await h.api.request('/api/transactions',input,h.ctx)).queued,true);assert.equal((await h.api.pending()).length,1);
});

test('legacy drafts are retained until their author explicitly assigns them',async()=>{
  const h=harness();await h.api.request('/api/transactions',input,h.ctx);
  const [item]=await h.api.pending();delete item.user;
  await new Promise((resolve,reject)=>{const req=h.idb.open('haushaltpro-offline-v1');req.onsuccess=()=>{const db=req.result,tx=db.transaction('queue','readwrite');tx.objectStore('queue').put(item);tx.oncomplete=()=>{db.close();resolve()};tx.onerror=reject}});
  let calls=0;h.fetch=async()=>{calls++;return json({id:1})};await h.api.sync();
  assert.equal(calls,0);assert.equal((await h.api.pending()).length,1);
});
