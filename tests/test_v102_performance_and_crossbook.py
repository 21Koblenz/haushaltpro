import sqlite3,sys,types,tempfile,shutil
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main

base=Path(tempfile.mkdtemp(prefix='hp102-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=5000');return c
db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear();main._view_cache.clear();main._view_cache_generation.clear()

from fastapi.testclient import TestClient
admin=TestClient(main.app);child=TestClient(main.app);direct=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()
def csrf(c): return ok(c.get('/api/me'))['csrf']
def post(c,u,j=None): return c.post(u,json=j,headers={'X-CSRF-Token':csrf(c)})
def put(c,u,j=None): return c.put(u,json=j,headers={'X-CSRF-Token':csrf(c)})

ok(admin.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
child_book=ok(post(admin,'/api/books',{'name':'Kind'}))['id']
ok(child.post('/api/register',json={'username':'kind','password':'KindPasswort123!'}))

# Admin stays on default book and grants child access to OTHER book explicitly.
assert ok(admin.get('/api/me'))['book']['id']=='default'
users=ok(admin.get('/api/users'))
assert any(b['id']==child_book for b in users[0]['manageable_books']),users[0]
ok(put(admin,'/api/users/kind/membership',{'role':'editor','book_id':child_book}))
ok(child.post('/api/login',json={'username':'kind','password':'KindPasswort123!','trusted_device':False}))
cme=ok(child.get('/api/me'));assert cme['book']['id']==child_book and cme['role']=='editor',cme
print('v0.10.2 cross-book membership while another book is active: PASS')

# New user can be created directly for a non-active household.
ok(post(admin,'/api/users',{'username':'direktkind','password':'DirektKindPass123!','role':'viewer','book_id':child_book}))
ok(direct.post('/api/login',json={'username':'direktkind','password':'DirektKindPass123!','trusted_device':False}))
dme=ok(direct.get('/api/me'));assert dme['book']['id']==child_book and dme['role']=='viewer',dme
print('v0.10.2 direct user creation for selected non-active book: PASS')

# Book list reports total file footprint + data counts.
books=ok(admin.get('/api/books'));default=next(b for b in books if b['id']=='default')
assert default['size_bytes']>=default['database_file_bytes']>0
assert default['transactions']==0 and default['attachments_bytes']==0
print('v0.10.2 household database stats: PASS')

# Chart calculation stays bounded instead of rebuilding a full balance for every day.
perf=sqlite3.connect(':memory:',check_same_thread=False);perf.row_factory=sqlite3.Row;perf.execute('PRAGMA foreign_keys=ON');db.init_schema(perf);db.migrate_schema(perf)
c=perf
aid=c.execute("INSERT INTO accounts(name,type,opening_balance,currency,start_date,active,created_at) VALUES('Perf','checking',100000,'EUR','2026-09-01',1,'x')").lastrowid
for d in range(1,31):
    c.execute("INSERT INTO transactions(account_id,amount,direction,booking_date,name,status,created_at,updated_at) VALUES(?,?,?,?,?,'executed','x','x')",(aid,-100,'expense',f'2026-09-{d:02d}',f'T{d}'))
c.commit()
count={'select':0}
c.set_trace_callback(lambda sql: count.__setitem__('select',count['select']+(1 if sql.lstrip().upper().startswith('SELECT') else 0)))
series=main.monthly_account_series(c,aid,'2026-09')
c.set_trace_callback(None)
assert len(series)==30
assert series[-1]['balance']==970.0,series[-1]
assert count['select']<15,count
print(f"v0.10.2 monthly chart bounded queries: PASS ({count['select']} SELECTs)")

js=(root/'static/app.js').read_text()
assert 'viewDataCache=new Map()' in js and 'requestIdleCallback' in js and 'cachedApi(' in js
assert 'sessionStorage.setItem' not in js
assert main.APP_VERSION in {'0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3','0.21.4','0.21.5','0.21.6','0.21.7'}
print('v0.10.2 frontend prefetch/cache source: PASS')
perf.close()

shutil.rmtree(base,ignore_errors=True)
