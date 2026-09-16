import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db');Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
db._conn=c;db.DB_PATH=Path(tmp);db.init_schema(c);db.migrate_schema(c)
assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]=='27'
assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='client_mutations'").fetchone()
from app import main
real_session=main.session
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
# Parallel tabs/retries must converge to one journal row under the write lock.
from concurrent.futures import ThreadPoolExecutor
parallel_headers={'X-Idempotency-Key':'offline-concurrent-001'}
parallel_payload={**payload,'name':'Parallel retry'}
# Production uses separate read/write connections per thread. Reproduce that
# layout instead of concurrently sharing the suite's injected sqlite connection.
real_connect=db.connect
real_test_session=main.session
def plain_connect(key,path=None):
    conn=sqlite3.connect(str(path or tmp),check_same_thread=False)
    conn.row_factory=sqlite3.Row
    db._configure_runtime(conn)
    return conn
def parallel_session(request,write=False):
    db.activate(Path(tmp),'test-key')
    return ('test',1,'csrf',0)
c.commit();db._configure_runtime(c)  # production enables WAL before serving requests
db._conn=None;db.connect=plain_connect;main.session=parallel_session
try:
    with ThreadPoolExecutor(max_workers=6) as pool:
        responses=list(pool.map(lambda _:client.post('/api/transactions',json=parallel_payload,headers=parallel_headers),range(6)))
finally:
    db._close_managed_connections();db._conn=c;db.connect=real_connect;main.session=real_test_session
ids=[ok(r)['id'] for r in responses]
assert len(set(ids))==1,ids
assert c.execute("SELECT COUNT(*) FROM transactions WHERE name='Parallel retry'").fetchone()[0]==1
# A key cannot be reused for another endpoint.
assert client.post('/api/transfers',json=tr,headers=parallel_headers).status_code==409
# The real session guard rejects writes after another tab changed book/user.
from datetime import timedelta
from starlette.requests import Request
now=main.utcnow()
record={'expires_at':now+timedelta(hours=1),'trusted':True,'last_seen':now,'csrf':'test-csrf','book_id':'book-a','username':'Alice'}
original_record=main._session_record;original_activate=main._activate_session_book
main._session_record=lambda request:('test',record)
main._activate_session_book=lambda rec:({}, {'role':'owner'}, 1)
guard=real_session
def request(book='book-a',user='Alice'):
    headers=[(b'x-csrf-token',b'test-csrf'),(b'x-haushaltpro-book',book.encode()),(b'x-haushaltpro-user',user.encode())]
    return Request({'type':'http','headers':headers})
assert guard(request(),True)[1]==1
for req in (request(book='book-b'),request(user='Bob')):
    try: guard(req,True)
    except main.HTTPException as exc: assert exc.status_code==409
    else: raise AssertionError('Cross-context write accepted')
main._session_record=original_record;main._activate_session_book=original_activate
off=(root/'static/offline-sync.js').read_text(encoding='utf-8');idx=(root/'static/index.html').read_text(encoding='utf-8');app=(root/'static/app.js').read_text(encoding='utf-8')
for needle in ('indexedDB.open','POST /api/transactions','POST /api/transfers','POST /api/recurring','X-Idempotency-Key','hp-offline-synced','HEARTBEAT_MS'):assert needle in off,needle
assert 'id="connectionStatus"' in idx and '/assets/offline-sync.js?v=0.21.9-dev.2' in idx
assert 'HaushaltProOffline.request' in app and 'offlineSaveActive' in app
print('offline queue + idempotency regression: PASS')
c.close();Path(tmp).unlink(missing_ok=True)
