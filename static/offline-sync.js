(()=>{
'use strict';
const DB_NAME='haushaltpro-offline-v1',STORE='queue',DB_VERSION=1,HEARTBEAT_MS=15000;
const QUEUEABLE=new Set(['POST /api/transactions','POST /api/transfers','POST /api/recurring','POST /api/open-items']);
let reachable=null,syncing=false,pinging=false,lastSuccess=null,lastError='',started=false,dbPromise=null,cachedRows=[];
const sending=new Set();
const isEn=()=>((window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang')||'de')==='en');
const tr=(de,en)=>isEn()?en:de;
const makeId=()=>globalThis.crypto?.randomUUID?.()||('hp-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const context=()=>window.HaushaltProSyncContext?.()||{};
const owner=ctx=>String(ctx.username||'').toLowerCase();
const belongs=(item,ctx)=>item.user===owner(ctx)&&item.bookId===String(ctx.bookId);
function openDb(){
  if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{
    const req=indexedDB.open(DB_NAME,DB_VERSION);
    req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(STORE)){const s=db.createObjectStore(STORE,{keyPath:'id'});s.createIndex('createdAt','createdAt')}};
    req.onsuccess=()=>{const db=req.result;db.onversionchange=()=>{db.close();dbPromise=null};resolve(db)};
    req.onerror=()=>{dbPromise=null;reject(req.error)};
  });
  return dbPromise;
}
async function withStore(mode,fn){
  const db=await openDb();
  return new Promise((resolve,reject)=>{
    const tx=db.transaction(STORE,mode);let value;
    // Request success alone is insufficient: quota/commit failures can follow it.
    tx.oncomplete=()=>resolve(value);tx.onabort=()=>reject(tx.error||new Error('Offline storage aborted'));tx.onerror=()=>reject(tx.error);
    try{const req=fn(tx.objectStore(STORE));req.onsuccess=()=>{value=req.result}}catch(err){tx.abort();reject(err)}
  });
}
async function rows(){return (await withStore('readonly',s=>s.getAll()))||[]}
async function refresh(){cachedRows=await rows();render()}
async function put(item){await withStore('readwrite',s=>s.put(item));await refresh()}
async function remove(id){await withStore('readwrite',s=>s.delete(id));await refresh()}
function normalized(url){const u=new URL(url,location.origin);return u.pathname+u.search}
function queueable(url,method){const u=new URL(url,location.origin);return u.origin===location.origin&&(QUEUEABLE.has(method+' '+u.pathname)||(method==='POST'&&/^\/api\/open-items\/[1-9][0-9]*\/payments$/.test(u.pathname)))}
function render(){
  const el=document.getElementById('connectionStatus'),text=document.getElementById('connectionText'),badge=document.getElementById('connectionQueue');if(!el||!text||!badge)return;
  const ctx=context(),legacy=cachedRows.filter(x=>!x.user&&x.bookId===String(ctx.bookId)),all=cachedRows.filter(x=>x.user===owner(ctx)),n=all.length+legacy.length,current=all.filter(x=>belongs(x,ctx)).length+legacy.length;
  el.classList.remove('online','offline','syncing','error','checking');
  if(syncing){el.classList.add('syncing');text.textContent=tr('Synchronisiere …','Syncing …')}
  else if(reachable===null){el.classList.add('checking');text.textContent=tr('Verbindung prüfen …','Checking connection …')}
  else if(legacy.length&&reachable){el.classList.add('error');text.textContent=tr('Offline-Einträge prüfen','Review offline entries')}
  else if(lastError&&reachable&&current){el.classList.add('error');text.textContent=tr('Sync-Fehler','Sync error')}
  else if(reachable){el.classList.add('online');text.textContent=tr('Server verbunden','Server connected')}
  else{el.classList.add('offline');text.textContent=tr('Keine Verbindung','Offline')}
  badge.hidden=n===0;badge.textContent=n?String(n):'';
  const parts=[];if(n)parts.push(tr(`${n} Änderung${n===1?'':'en'} wartet${n!==current?` (${current} in diesem Haushaltsbuch)`:''}`,`${n} change${n===1?'':'s'} pending${n!==current?` (${current} in this book)`:''}`));
  if(cachedRows.some(x=>!x.user&&x.bookId===String(ctx.bookId)))parts.push(tr('Alte Offline-Einträge ohne Benutzerzuordnung sind zurückgehalten.','Legacy offline entries without an owner are held back.'));
  if(lastSuccess)parts.push(tr('Letzter Serverkontakt: ','Last server contact: ')+lastSuccess.toLocaleString());if(lastError)parts.push(lastError);
  parts.push(tr('Klicken: jetzt prüfen/synchronisieren','Click: check/sync now'));el.title=parts.join('\n');el.setAttribute('aria-label',text.textContent+(n?` · ${n}`:''));
}
function contact(response){
  reachable=response.status<500;
  if(reachable)lastSuccess=new Date();
  render();
}
async function fetchTimed(url,options={},timeout=15000){
  if(options.signal)return fetch(url,options);
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),timeout);
  try{return await fetch(url,{...options,signal:controller.signal})}finally{clearTimeout(timer)}
}
function writeHeaders(opt,ctx,id){
  const headers=new Headers(opt.headers||{});
  if(id)headers.set('X-Idempotency-Key',id);
  if(ctx.bookId)headers.set('X-HaushaltPro-Book',String(ctx.bookId));
  if(ctx.username)headers.set('X-HaushaltPro-User',encodeURIComponent(ctx.username));
  return headers;
}
async function request(url,opt={},ctx={}){
  const method=(opt.method||'GET').toUpperCase(),canQueue=queueable(url,method)&&typeof opt.body==='string'&&!(opt.body instanceof FormData);
  if(!canQueue){
    try{const response=await fetchTimed(url,{...opt,headers:method==='GET'?opt.headers:writeHeaders(opt,ctx)},30000);contact(response);return {response}}
    catch(err){reachable=false;render();throw err}
  }
  if(!ctx.bookId||!ctx.username)throw new Error(tr('Offline-Speichern benötigt eine Anmeldung und ein aktives Haushaltsbuch.','Offline save requires a signed-in user and an active book.'));
  JSON.parse(opt.body);
  const requestId=new Headers(opt.headers||{}).get('X-Idempotency-Key')||makeId();
  const item={id:requestId,url:normalized(url),method,body:opt.body,bookId:String(ctx.bookId),user:owner(ctx),createdAt:new Date().toISOString(),tries:0,error:null};
  // Save before sending: closing the page or losing the reply must retain the same ID.
  sending.add(requestId);
  try{
    await put(item);
    if(navigator.onLine===false||reachable===false)return queued(item);
    let response;
    try{response=await fetchTimed(url,{...opt,headers:writeHeaders(opt,ctx,requestId)});contact(response)}
    catch(err){reachable=false;lastError=String(err?.message||err);return queued(item)}
    if(response.status>=500){reachable=false;lastError=tr('Server vorübergehend nicht erreichbar.','Server temporarily unavailable.');return queued(item)}
    if(response.ok){
      // A proxy login page or truncated JSON is not a confirmed server write.
      try{const body=await response.clone().json();if(!body?.id)throw new Error('Invalid server response')}
      catch(err){reachable=false;lastError=String(err?.message||err);return queued(item)}
    }
    // Explicit 4xx: the form remains open for correction; no silent background retry.
    await remove(requestId);lastError='';render();return {response};
  }finally{sending.delete(requestId);render()}
}
function queued(item){render();window.dispatchEvent(new CustomEvent('hp-offline-queued',{detail:{id:item.id}}));return {queued:true,id:item.id}}
async function responseError(response){try{const j=await response.json();const d=j?.detail;return typeof d==='string'?d:JSON.stringify(d||j)}catch{return response.statusText||`HTTP ${response.status}`}}
async function sync(manual=false){
  if(syncing)return {synced:0};
  const ctx=context();if(!ctx.csrf||!ctx.bookId||!ctx.username){render();return {synced:0}}
  syncing=true;let synced=0;
  try{
    await refresh();
    const legacy=cachedRows.filter(x=>!x.user&&x.bookId===String(ctx.bookId));
    if(manual&&legacy.length&&window.confirm(tr(
      `${legacy.length} Offline-Einträge aus einer älteren Version warten in diesem Haushaltsbuch. Hast du diese Einträge selbst erstellt? Mit OK ordnest du sie deinem Benutzer zu und synchronisierst sie.`,
      `${legacy.length} offline entries from an older version are waiting in this book. Did you create these entries? OK assigns them to your user and syncs them.`))){
      for(const item of legacy)await put({...item,user:owner(ctx)});
    }
    const pending=cachedRows.filter(x=>belongs(x,ctx)).sort((a,b)=>String(a.createdAt).localeCompare(String(b.createdAt))||a.id.localeCompare(b.id));
    for(const item of pending){
      if(sending.has(item.id))break;
      if(!belongs(item,context())||ctx.csrf!==context().csrf)break;
      if(item.blocked&&!manual){lastError=item.error;break}
      const headers=writeHeaders({headers:{'Content-Type':'application/json','X-CSRF-Token':ctx.csrf}},ctx,item.id);
      try{
        const response=await fetchTimed(item.url,{method:item.method,body:item.body,headers,credentials:'same-origin'});contact(response);
        if(!response.ok){
          item.error=await responseError(response);item.tries=Number(item.tries||0)+1;
          item.blocked=response.status>=400&&response.status<500&&![401,403,408,429].includes(response.status);
          await put(item);lastError=item.error;break;
        }
        const body=await response.json();if(!body?.id)throw new Error('Invalid server response');
        await remove(item.id);lastError='';synced++;
      }catch(err){reachable=false;lastError=String(err?.message||err);break}
    }
  }catch(err){lastError=String(err?.message||err)}
  finally{syncing=false;render()}
  if(synced)window.dispatchEvent(new CustomEvent('hp-offline-synced',{detail:{count:synced}}));
  if(manual&&lastError)window.dispatchEvent(new CustomEvent('hp-offline-sync-error',{detail:{message:lastError}}));return {synced};
}
async function ping(manual=false){
  if(pinging||syncing)return;pinging=true;
  try{
    const r=await fetchTimed('/api/status',{credentials:'same-origin',cache:'no-store'},5000);
    const status=r.ok?await r.json():null;reachable=!!(r.ok&&status&&typeof status.version==='string'&&typeof status.initialized==='boolean');
    if(reachable){lastSuccess=new Date();await sync(manual)}
    else lastError=tr('Server nicht erreichbar.','Server unreachable.');
  }catch(err){reachable=false;lastError=tr('Server nicht erreichbar.','Server unreachable.')}
  finally{pinging=false;render()}
}
function start(){
  if(started)return;started=true;
  window.addEventListener('online',()=>ping());window.addEventListener('offline',()=>{reachable=false;render()});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)ping()});
  document.getElementById('connectionStatus')?.addEventListener('click',()=>ping(true));
  refresh().catch(err=>{lastError=String(err?.message||err);render()});setTimeout(ping,100);
  setInterval(()=>{if(!document.hidden)ping()},HEARTBEAT_MS);
}
window.HaushaltProOffline={request,sync,ping,start,pending:rows};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
