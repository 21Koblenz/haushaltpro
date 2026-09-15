(()=>{
'use strict';
const DB_NAME='haushaltpro-offline-v1',STORE='queue',DB_VERSION=1,HEARTBEAT_MS=15000;
const QUEUEABLE=new Set(['POST /api/transactions','POST /api/transfers','POST /api/recurring']);
let reachable=navigator.onLine!==false,syncing=false,lastSuccess=null,lastError='',started=false;
const isEn=()=>((window.HaushaltProI18n?.language?.()||localStorage.getItem('hp_lang')||'de')==='en');
const tr=(de,en)=>isEn()?en:de;
const makeId=()=>globalThis.crypto?.randomUUID?.()||('hp-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2));
const context=()=>window.HaushaltProSyncContext?.()||{};
function openDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open(DB_NAME,DB_VERSION);req.onupgradeneeded=()=>{const db=req.result;if(!db.objectStoreNames.contains(STORE)){const s=db.createObjectStore(STORE,{keyPath:'id'});s.createIndex('createdAt','createdAt')}};req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error)})}
async function withStore(mode,fn){const db=await openDb();try{return await new Promise((resolve,reject)=>{const tx=db.transaction(STORE,mode),store=tx.objectStore(STORE);let result;try{result=fn(store,resolve,reject)}catch(e){reject(e)}tx.onerror=()=>reject(tx.error);if(result&&typeof result.then==='function')result.catch(reject)})}finally{db.close()}}
async function rows(){return withStore('readonly',(s,resolve,reject)=>{const r=s.getAll();r.onsuccess=()=>resolve(r.result||[]);r.onerror=()=>reject(r.error)})}
async function put(item){return withStore('readwrite',(s,resolve,reject)=>{const r=s.put(item);r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error)})}
async function remove(id){return withStore('readwrite',(s,resolve,reject)=>{const r=s.delete(id);r.onsuccess=()=>resolve();r.onerror=()=>reject(r.error)})}
function normalized(url){const u=new URL(url,location.origin);return u.pathname+u.search}
function queueable(url,method){const u=new URL(url,location.origin);return QUEUEABLE.has(method+' '+u.pathname)}
async function render(){
  const el=document.getElementById('connectionStatus'),text=document.getElementById('connectionText'),badge=document.getElementById('connectionQueue');if(!el||!text||!badge)return;
  const all=await rows().catch(()=>[]),n=all.length,currentBook=context().bookId,current=all.filter(x=>x.bookId===currentBook).length;
  el.classList.remove('online','offline','syncing','error','checking');
  if(syncing){el.classList.add('syncing');text.textContent=tr('Synchronisiere …','Syncing …')}
  else if(lastError&&reachable&&current){el.classList.add('error');text.textContent=tr('Sync-Fehler','Sync error')}
  else if(reachable){el.classList.add('online');text.textContent=tr('Server verbunden','Server connected')}
  else{el.classList.add('offline');text.textContent=tr('Keine Verbindung','Offline')}
  badge.hidden=n===0;badge.textContent=n?String(n):'';
  const parts=[];if(n)parts.push(tr(`${n} Änderung${n===1?'':'en'} wartet${n!==current?` (${current} in diesem Haushaltsbuch)`:''}`,`${n} change${n===1?'':'s'} pending${n!==current?` (${current} in this book)`:''}`));
  if(lastSuccess)parts.push(tr('Letzter Serverkontakt: ','Last server contact: ')+lastSuccess.toLocaleString());if(lastError)parts.push(lastError);
  parts.push(tr('Klicken: jetzt prüfen/synchronisieren','Click: check/sync now'));el.title=parts.join('\n');el.setAttribute('aria-label',text.textContent+(n?` · ${n}`:''));
}
async function enqueue(url,opt,requestId,bookId){
  if(!bookId)throw new Error(tr('Offline-Speichern benötigt ein aktives Haushaltsbuch.','Offline save requires an active household book.'));
  if(typeof opt.body!=='string')throw new Error(tr('Diese Aktion kann offline nicht gepuffert werden.','This action cannot be queued offline.'));
  await put({id:requestId,url:normalized(url),method:(opt.method||'POST').toUpperCase(),body:opt.body,bookId:String(bookId),createdAt:new Date().toISOString(),tries:0,error:null});
  await render();window.dispatchEvent(new CustomEvent('hp-offline-queued',{detail:{id:requestId}}));return {queued:true,id:requestId};
}
async function request(url,opt={},ctx={}){
  const method=(opt.method||'GET').toUpperCase(),canQueue=queueable(url,method)&&!(opt.body instanceof FormData),headers=new Headers(opt.headers||{});
  const requestId=canQueue?(headers.get('X-Idempotency-Key')||makeId()):null;if(requestId)headers.set('X-Idempotency-Key',requestId);
  const options={...opt,headers};
  try{
    const response=await fetch(url,options);reachable=true;lastSuccess=new Date();
    if(canQueue&&[502,503,504].includes(response.status)){lastError=tr('Server vorübergehend nicht erreichbar.','Server temporarily unavailable.');return await enqueue(url,options,requestId,ctx.bookId)}
    lastError='';await render();return {response};
  }catch(err){
    reachable=false;lastError=String(err?.message||err||tr('Netzwerkfehler','Network error'));
    if(canQueue)return await enqueue(url,options,requestId,ctx.bookId);
    await render();throw err;
  }
}
async function responseError(response){try{const j=await response.json();const d=j?.detail;return typeof d==='string'?d:JSON.stringify(d||j)}catch{return response.statusText||`HTTP ${response.status}`}}
async function sync(manual=false){
  if(syncing)return {synced:0};const ctx=context();if(!ctx.csrf||!ctx.bookId){await render();return {synced:0}}
  const all=(await rows()).sort((a,b)=>String(a.createdAt).localeCompare(String(b.createdAt))),pending=all.filter(x=>String(x.bookId)===String(ctx.bookId));if(!pending.length){lastError='';await render();return {synced:0}}
  syncing=true;lastError='';await render();let synced=0;
  for(const item of pending){
    const headers=new Headers({'Content-Type':'application/json','X-CSRF-Token':ctx.csrf,'X-Idempotency-Key':item.id});
    try{
      const response=await fetch(item.url,{method:item.method,body:item.body,headers,credentials:'same-origin'});reachable=true;lastSuccess=new Date();
      if(response.status===401){lastError=tr('Sitzung gesperrt – nach Anmeldung erneut synchronisieren.','Session locked – sign in to sync.');break}
      if(!response.ok){const message=await responseError(response);item.tries=Number(item.tries||0)+1;item.error=message;await put(item);lastError=message;break}
      await remove(item.id);synced++;
    }catch(err){reachable=false;lastError=String(err?.message||err||tr('Netzwerkfehler','Network error'));break}
  }
  syncing=false;await render();if(synced)window.dispatchEvent(new CustomEvent('hp-offline-synced',{detail:{count:synced}}));
  if(manual&&lastError)window.dispatchEvent(new CustomEvent('hp-offline-sync-error',{detail:{message:lastError}}));return {synced};
}
async function ping(){
  if(syncing)return;let controller=null,timer=null;try{controller=new AbortController();timer=setTimeout(()=>controller.abort(),5000);const r=await fetch('/api/status',{credentials:'same-origin',cache:'no-store',signal:controller.signal});reachable=r.ok;if(r.ok){lastSuccess=new Date();lastError='';await sync(false)}}catch(err){reachable=false;if(navigator.onLine!==false)lastError=tr('Server nicht erreichbar.','Server unreachable.')}finally{if(timer)clearTimeout(timer);await render()}
}
function start(){if(started)return;started=true;window.addEventListener('online',()=>ping());window.addEventListener('offline',()=>{reachable=false;render()});document.addEventListener('visibilitychange',()=>{if(!document.hidden)ping()});document.getElementById('connectionStatus')?.addEventListener('click',()=>ping());render();setTimeout(ping,100);setInterval(ping,HEARTBEAT_MS)}
window.HaushaltProOffline={request,sync,ping,start,pending:rows};
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
