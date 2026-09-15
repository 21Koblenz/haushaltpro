from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count=text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old,new,1)

# --- database schema: idempotent client mutations ---------------------------------
db_path=Path('app/db.py')
db=db_path.read_text(encoding='utf-8')
client_table='''
        CREATE TABLE IF NOT EXISTS client_mutations(
            request_id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
'''
anchor="""        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
"""
if 'CREATE TABLE IF NOT EXISTS client_mutations(' not in db:
    db=replace_once(db,anchor,client_table+'\n'+anchor,'init client_mutations table')

migration_anchor='''    c.execute("""CREATE TABLE IF NOT EXISTS payee_presets(
        id INTEGER PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,usage_count INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,last_used_at TEXT NOT NULL)""")
'''
migration_table='''    c.execute("""CREATE TABLE IF NOT EXISTS client_mutations(
        request_id TEXT PRIMARY KEY,endpoint TEXT NOT NULL,response_json TEXT NOT NULL,created_at TEXT NOT NULL)""")
'''
if migration_table not in db:
    db=replace_once(db,migration_anchor,migration_anchor+migration_table,'migration client_mutations table')

idx_anchor='        CREATE INDEX IF NOT EXISTS idx_payee_usage ON payee_presets(usage_count DESC, last_used_at DESC);\n'
if 'idx_client_mutations_created' not in db:
    db=replace_once(db,idx_anchor,idx_anchor+'        CREATE INDEX IF NOT EXISTS idx_client_mutations_created ON client_mutations(created_at);\n','init client mutation index')
    mig_idx='    c.execute("CREATE INDEX IF NOT EXISTS idx_payee_usage ON payee_presets(usage_count DESC,last_used_at DESC)")\n'
    db=replace_once(db,mig_idx,mig_idx+'    c.execute("CREATE INDEX IF NOT EXISTS idx_client_mutations_created ON client_mutations(created_at)")\n','migration client mutation index')

db=db.replace("schema_version','25", "schema_version','26")
db=db.replace("value='25'", "value='26'")
db_path.write_text(db,encoding='utf-8')

# --- backend idempotency -----------------------------------------------------------
main_path=Path('app/main.py')
main=main_path.read_text(encoding='utf-8')
if 'import re\n' not in main:
    main=replace_once(main,'import os\n','import os\nimport re\n','re import')
main=main.replace('APP_VERSION = "0.21.8"','APP_VERSION = "0.21.9-dev"',1)

helpers='''
IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def client_request_id(request: Request) -> str | None:
    value=(request.headers.get("X-Idempotency-Key") or "").strip()
    if not value:
        return None
    if not IDEMPOTENCY_KEY_RE.fullmatch(value):
        raise HTTPException(400,"Ungültiger Idempotency-Key")
    return value


def client_mutation_replay(c, request_id: str | None, endpoint: str):
    if not request_id:
        return None
    row=c.execute("SELECT endpoint,response_json FROM client_mutations WHERE request_id=?",(request_id,)).fetchone()
    if not row:
        return None
    if row["endpoint"] != endpoint:
        raise HTTPException(409,"Idempotency-Key wurde bereits für eine andere Aktion verwendet")
    payload=json.loads(row["response_json"])
    if isinstance(payload,dict):
        payload=dict(payload);payload["idempotent_replay"]=True
    return payload


def client_mutation_store(c, request_id: str | None, endpoint: str, payload: dict) -> None:
    if not request_id:
        return
    c.execute("DELETE FROM client_mutations WHERE created_at<?",(iso(utcnow()-timedelta(days=365)),))
    c.execute("INSERT INTO client_mutations(request_id,endpoint,response_json,created_at) VALUES(?,?,?,?)",
              (request_id,endpoint,json.dumps(payload,ensure_ascii=False,separators=(",",":")),iso(utcnow())))

'''
if 'def client_request_id(request: Request)' not in main:
    main=replace_once(main,'@app.post("/api/transactions")\ndef transaction_create',helpers+'@app.post("/api/transactions")\ndef transaction_create','idempotency helpers')

# Transaction create: replay before validation + atomic store.
old='''def transaction_create(x: TransactionIn, request: Request):
    sess=session(request, True)
    c0 = db.db()
'''
new='''def transaction_create(x: TransactionIn, request: Request):
    sess=session(request, True)
    request_id=client_request_id(request); endpoint="POST /api/transactions"
    c0 = db.db()
    replay=client_mutation_replay(c0,request_id,endpoint)
    if replay is not None:
        return replay
'''
main=replace_once(main,old,new,'transaction replay')
old='''        audit_append(c,sess[1],"transaction.create","transaction",cur.lastrowid,{"name":created_tx.get("name"),"added":audit_pick(created_tx,("name","amount","booking_date","value_date","account_name","payee","category_name","note","confidence","fixed_cost","tags"))})
        return {"id": cur.lastrowid, "recurring_id": recurring_id, "generated_transactions": len(generated_transactions)}
'''
new='''        audit_append(c,sess[1],"transaction.create","transaction",cur.lastrowid,{"name":created_tx.get("name"),"added":audit_pick(created_tx,("name","amount","booking_date","value_date","account_name","payee","category_name","note","confidence","fixed_cost","tags"))})
        result={"id":cur.lastrowid,"recurring_id":recurring_id,"generated_transactions":len(generated_transactions)}
        client_mutation_store(c,request_id,endpoint,result)
        return result
'''
main=replace_once(main,old,new,'transaction store')

# Transfer create.
old='''def transfer_create(x: TransferIn, request: Request):
    sess=session(request,True);amount=abs(cents(x.amount));ts=iso(utcnow())
'''
new='''def transfer_create(x: TransferIn, request: Request):
    sess=session(request,True);request_id=client_request_id(request);endpoint="POST /api/transfers"
    replay=client_mutation_replay(db.db(),request_id,endpoint)
    if replay is not None:
        return replay
    amount=abs(cents(x.amount));ts=iso(utcnow())
'''
main=replace_once(main,old,new,'transfer replay')
old='''        audit_append(c,sess[1],"transfer.create","transfer",tid,details)
    return {"id":tid,"recurring_transfer_id":recurring_transfer_id,"generated_transfers":generated}
'''
new='''        audit_append(c,sess[1],"transfer.create","transfer",tid,details)
        result={"id":tid,"recurring_transfer_id":recurring_transfer_id,"generated_transfers":generated}
        client_mutation_store(c,request_id,endpoint,result)
    return result
'''
main=replace_once(main,old,new,'transfer store')

# Standalone recurring create.
old='''def recurring_create(x: RecurringIn, request: Request):
    sess=session(request, True)
    c0=db.db()
'''
new='''def recurring_create(x: RecurringIn, request: Request):
    sess=session(request, True)
    request_id=client_request_id(request);endpoint="POST /api/recurring"
    c0=db.db()
    replay=client_mutation_replay(c0,request_id,endpoint)
    if replay is not None:
        return replay
'''
main=replace_once(main,old,new,'recurring replay')
old='''        audit_append(c,sess[1],"recurring.create","recurring",cur.lastrowid,{"name":created.get("name"),"added":audit_pick(created,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_until","confidence","fixed_cost","max_amount")),"generated_transactions":len(generated)})
        return {"id":cur.lastrowid,"generated_transactions":len(generated)}
'''
new='''        audit_append(c,sess[1],"recurring.create","recurring",cur.lastrowid,{"name":created.get("name"),"added":audit_pick(created,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_until","confidence","fixed_cost","max_amount")),"generated_transactions":len(generated)})
        result={"id":cur.lastrowid,"generated_transactions":len(generated)}
        client_mutation_store(c,request_id,endpoint,result)
        return result
'''
main=replace_once(main,old,new,'recurring store')
main_path.write_text(main,encoding='utf-8')

# --- browser offline queue ---------------------------------------------------------
offline_js=r'''(()=>{
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
'''
Path('static/offline-sync.js').write_text(offline_js,encoding='utf-8')

# --- frontend integration ----------------------------------------------------------
app_path=Path('static/app.js')
app=app_path.read_text(encoding='utf-8')
app=replace_once(app,'let runtimeStatus = {registration_enabled:true,public_mode:false,setup_token_required:false};\n','let runtimeStatus = {registration_enabled:true,public_mode:false,setup_token_required:false};\nlet offlineSaveActive=false;\n','offline state')
api_start=app.index('async function api(url,opt={}){')
api_end=app.index('\nasync function materializeRecurringDue',api_start)
api_new='''async function api(url,opt={}){
  const headers={...(opt.headers||{})};
  if(opt.body && !(opt.body instanceof FormData)) headers['Content-Type']='application/json';
  if(csrf) headers['X-CSRF-Token']=csrf;
  let r;
  if(window.HaushaltProOffline){
    const outcome=await window.HaushaltProOffline.request(url,{credentials:'same-origin',...opt,headers},{bookId:currentMe?.book?.id||null});
    if(outcome.queued){offlineSaveActive=true;clearViewCache();return {offline_queued:true,queue_id:outcome.id}}
    r=outcome.response;
  }else r=await fetch(url,{credentials:'same-origin',...opt,headers});
  if(r.status===401){showAuth(false,'Sitzung gesperrt. Bitte erneut anmelden.');throw new Error('Nicht angemeldet')}
  if(!r.ok){
    const j=await r.json().catch(()=>({detail:r.statusText}));
    const detail=j?.detail;let message=r.statusText||'Fehler';
    if(typeof detail==='string')message=detail;
    else if(Array.isArray(detail))message=detail.map(x=>x?.msg||x?.message||JSON.stringify(x)).join(' · ');
    else if(detail&&typeof detail==='object')message=detail.msg||detail.message||JSON.stringify(detail);
    throw new Error(hpText(message))
  }
  const ct=r.headers.get('content-type')||'';const result=ct.includes('application/json')?await r.json():r;
  if((opt.method||'GET').toUpperCase()!=='GET')clearViewCache();return result;
}
'''
app=app[:api_start]+api_new+app[api_end:]

boot_start=app.index('async function boot(){')
boot_end=app.index('\nfunction showAuth',boot_start)
boot_new='''async function boot(){
  try{
    const st=await fetch('/api/status',{cache:'no-store'}).then(r=>r.json());runtimeStatus=st;
    if($('appVersion'))$('appVersion').textContent='Version '+(st.version||'–');
    try{const me=await api('/api/me');csrf=me.csrf;showApp(me);window.HaushaltProOffline?.sync?.(false)}catch{showAuth(!st.initialized)}
  }catch(err){
    showAuth(false,hpLang()==='en'?'Server is currently unreachable. Offline entries can be created after a successful login and page load.':'Server ist derzeit nicht erreichbar. Offline-Einträge sind nach einer erfolgreichen Anmeldung und geladenen Seite möglich.');
  }
}
'''
app=app[:boot_start]+boot_new+app[boot_end:]

modal_start=app.index('function openModal(html,onSave){')
modal_end=app.index('\nfunction accountOptions',modal_start)
modal_new='''function openModal(html,onSave){$('modalContent').innerHTML=html;$('modalForm').reset();modal.showModal();$('modalCancel').onclick=()=>modal.close();$('modalForm').onsubmit=async e=>{e.preventDefault();offlineSaveActive=false;try{await onSave(new FormData(e.currentTarget));if(offlineSaveActive){modal.close();offlineSaveActive=false;toast(hpLang()==='en'?'Saved offline – will sync automatically.':'Offline gespeichert – wird automatisch synchronisiert.');return}modal.close();await loadCommon();toast('Gespeichert')}catch(err){if(offlineSaveActive){modal.close();offlineSaveActive=false;toast(hpLang()==='en'?'Saved offline – will sync automatically.':'Offline gespeichert – wird automatisch synchronisiert.');return}toast(err.message)}}}
'''
app=app[:modal_start]+modal_new+app[modal_end:]

toast_line="function toast(msg){const e=$('toast');e.textContent=hpText(msg);e.classList.add('show');setTimeout(()=>e.classList.remove('show'),3000)}\n"
listener='''window.HaushaltProSyncContext=()=>({csrf,bookId:currentMe?.book?.id||null});
window.addEventListener('hp-offline-synced',e=>{clearViewCache();const n=Number(e.detail?.count||0);toast(hpLang()==='en'?`${n} offline ${n===1?'entry':'entries'} synced.`:`${n} Offline-${n===1?'Eintrag':'Einträge'} synchronisiert.`);if(currentMe)loadCommon().catch(()=>{})});
window.addEventListener('hp-offline-sync-error',e=>toast((hpLang()==='en'?'Sync error: ':'Sync-Fehler: ')+(e.detail?.message||'')));
'''
app=replace_once(app,toast_line,toast_line+listener,'offline listeners')
app_path.write_text(app,encoding='utf-8')

# Index: status indicator + offline script + cache bust.
index_path=Path('static/index.html')
index=index_path.read_text(encoding='utf-8')
old='<div class="topbar-actions"><button class="ghost theme-toggle" id="themeToggle"'
new='<div class="topbar-actions"><button class="connection-status checking" id="connectionStatus" type="button" aria-live="polite"><span class="connection-dot" aria-hidden="true"></span><span id="connectionText">Server prüfen …</span><span class="connection-queue" id="connectionQueue" hidden></span></button><button class="ghost theme-toggle" id="themeToggle"'
index=replace_once(index,old,new,'connection status control')
index=index.replace('0.21.8-recurring-payee1','0.21.9-offline1').replace('0.21.8-recurring-transfer1','0.21.9-offline1')
index=replace_once(index,'<script src="/assets/app.js?v=0.21.9-offline1"></script>','<script src="/assets/offline-sync.js?v=0.21.9-offline1"></script>\n<script src="/assets/app.js?v=0.21.9-offline1"></script>','offline script include')
index_path.write_text(index,encoding='utf-8')

css_path=Path('static/style.css')
css=css_path.read_text(encoding='utf-8')
if '.connection-status{' not in css:
    css+='''\n/* Server/offline synchronization status */\n.connection-status{display:inline-flex;align-items:center;gap:.45rem;min-height:38px;padding:.45rem .7rem;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--muted);font-size:.82rem;white-space:nowrap}.connection-status:hover{border-color:var(--accent);color:var(--text)}.connection-dot{width:.62rem;height:.62rem;border-radius:50%;background:#9ca3af;box-shadow:0 0 0 3px color-mix(in srgb,#9ca3af 18%,transparent)}.connection-status.online .connection-dot{background:#22c55e;box-shadow:0 0 0 3px color-mix(in srgb,#22c55e 20%,transparent)}.connection-status.offline .connection-dot,.connection-status.error .connection-dot{background:#ef4444;box-shadow:0 0 0 3px color-mix(in srgb,#ef4444 20%,transparent)}.connection-status.syncing .connection-dot{background:#3b82f6;box-shadow:0 0 0 3px color-mix(in srgb,#3b82f6 20%,transparent);animation:hp-sync-pulse 1s infinite alternate}.connection-queue{min-width:1.35rem;padding:.08rem .38rem;border-radius:999px;background:var(--accent);color:#fff;font-size:.72rem;font-weight:700;text-align:center}@keyframes hp-sync-pulse{to{opacity:.35}}@media(max-width:760px){.connection-status{padding:.42rem .55rem}.connection-status #connectionText{display:none}}\n'''
css_path.write_text(css,encoding='utf-8')

# Changelog: retain full history; only extend Unreleased.
ch=Path('CHANGELOG.md');text=ch.read_text(encoding='utf-8')
fixed='- The current-month analysis now includes known/planned bookings through month end, including materialized recurring expenses and income. Historical months and yearly analysis remain actual-only.\n'
if 'Offline queue for new bookings' not in text:
    text=replace_once(text,fixed,fixed+'- Offline queue for new bookings, transfers and recurring series: entries are stored locally when the server is unreachable and synchronized automatically after reconnecting.\n- Client-generated idempotency keys prevent duplicate financial entries when a request reached the server but the response was lost.\n','changelog offline fixed')
    changed='- Removed the duplicate “+ Wiederkehrende Buchung” creation button from the recurring-series tab. New recurring series are created through the normal “+ Buchung” dialog, while existing series remain manageable in the recurring tab.\n'
    text=replace_once(text,changed,changed+'- The top bar now shows live server reachability, pending offline entries and synchronization state; clicking the indicator triggers an immediate connectivity/sync check.\n','changelog offline changed')
ch.write_text(text,encoding='utf-8')

# Regression test for schema/idempotency/static integration.
test=r'''import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db');Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
db._conn=c;db.DB_PATH=Path(tmp);db.init_schema(c);db.migrate_schema(c)
assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]=='26'
assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='client_mutations'").fetchone()
from app import main
main.db._conn=c;main.session=lambda request,write=False:('test',1,'csrf',0);main.require_book_owner=lambda request:None;main.require_system_admin=lambda request:None
c.execute("INSERT OR IGNORE INTO users(id,username,password_hash,created_at) VALUES(1,'admin','x','2026-01-01T00:00:00+00:00')");c.commit()
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):assert r.status_code<300,(r.status_code,r.text);return r.json()
giro=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}))['id']
cash=ok(client.post('/api/accounts',json={'name':'Cash','type':'cash','opening_balance':'0','currency':'EUR','start_date':'2026-09-01'}))['id']
food=ok(client.post('/api/categories',json={'name':'OfflineFood','direction':'expense'}))['id']
headers={'X-Idempotency-Key':'offline-tx-00000001'}
payload={'account_id':giro,'amount':'12.34','booking_date':'2026-09-15','name':'Offline Einkauf','payee':'Markt','category_id':food,'tags':[],'splits':[],'remember_payee':False}
a=ok(client.post('/api/transactions',json=payload,headers=headers));b=ok(client.post('/api/transactions',json=payload,headers=headers));assert a['id']==b['id'] and b.get('idempotent_replay') is True
assert c.execute("SELECT COUNT(*) FROM transactions WHERE name='Offline Einkauf'").fetchone()[0]==1
th={'X-Idempotency-Key':'offline-transfer-0001'}
tr={'from_account_id':giro,'to_account_id':cash,'amount':'50','booking_date':'2026-09-15','name':'Offline Transfer','note':None,'recurring':False,'recurring_frequency':None,'recurring_interval_count':1,'recurring_until':None}
ta=ok(client.post('/api/transfers',json=tr,headers=th));tb=ok(client.post('/api/transfers',json=tr,headers=th));assert ta['id']==tb['id'] and tb.get('idempotent_replay') is True
assert c.execute("SELECT COUNT(*) FROM transfers WHERE name='Offline Transfer'").fetchone()[0]==1
rh={'X-Idempotency-Key':'offline-recurring-01'}
rec={'account_id':giro,'category_id':food,'name':'Offline Serie','payee':'Provider','amount':'20','next_date':'2026-10-01','frequency':'monthly','interval_count':1,'kind':'direct_debit','max_amount':None,'active':True,'valid_until':'2026-12-01','confidence':'fixed','fixed_cost':True}
ra=ok(client.post('/api/recurring',json=rec,headers=rh));rb=ok(client.post('/api/recurring',json=rec,headers=rh));assert ra['id']==rb['id'] and rb.get('idempotent_replay') is True
assert c.execute("SELECT COUNT(*) FROM recurring WHERE name='Offline Serie'").fetchone()[0]==1
bad=client.post('/api/transactions',json=payload,headers={'X-Idempotency-Key':'bad key'});assert bad.status_code==400,bad.text
off=(root/'static/offline-sync.js').read_text(encoding='utf-8');idx=(root/'static/index.html').read_text(encoding='utf-8');app=(root/'static/app.js').read_text(encoding='utf-8')
for needle in ('indexedDB.open','POST /api/transactions','POST /api/transfers','POST /api/recurring','X-Idempotency-Key','hp-offline-synced','setInterval(ping,HEARTBEAT_MS)'):assert needle in off,needle
assert 'id="connectionStatus"' in idx and '/assets/offline-sync.js?v=0.21.9-offline1' in idx
assert 'HaushaltProOffline.request' in app and 'offlineSaveActive' in app
print('offline queue + idempotency regression: PASS')
c.close();Path(tmp).unlink(missing_ok=True)
'''
Path('tests/test_offline_sync.py').write_text(test,encoding='utf-8')

# Keep legacy version assertion aware of dev build.
p=Path('tests/test_v090_transfers_payees_audit.py');s=p.read_text(encoding='utf-8')
if "'0.21.9-dev'" not in s:
    s=s.replace("'0.21.8'}","'0.21.8','0.21.9-dev'}")
p.write_text(s,encoding='utf-8')

print('offline sync patch applied')
