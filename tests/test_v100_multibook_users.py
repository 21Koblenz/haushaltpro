import sqlite3,sys,types,tempfile,shutil
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main

base=Path(tempfile.mkdtemp(prefix='hp100-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=5000');return c

db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
admin=TestClient(main.app);child=TestClient(main.app)

def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()

def csrf(client): return ok(client.get('/api/me'))['csrf']
def post(client,url,j=None): return client.post(url,json=j,headers={'X-CSRF-Token':csrf(client)})
def put(client,url,j=None): return client.put(url,json=j,headers={'X-CSRF-Token':csrf(client)})

# Initial shared household.
ok(admin.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
me=ok(admin.get('/api/me'));assert me['book']['name']=='Haushalt' and me['role']=='owner'
shared_path=Path(ok(admin.get('/api/books'))[0]['path']);assert shared_path.exists()

# Owner can also create a user directly in Settings/API.
direct=TestClient(main.app)
ok(post(admin,'/api/users',{'username':'direkt','password':'DirektPasswort123!','role':'viewer'}))
ok(direct.post('/api/login',json={'username':'direkt','password':'DirektPasswort123!','trusted_device':False}))
dme=ok(direct.get('/api/me'));assert dme['role']=='viewer' and dme['book']['id']=='default'
assert post(direct,'/api/accounts',{'name':'NichtErlaubt','type':'cash','opening_balance':'1','currency':'EUR','start_date':'2026-09-12'}).status_code==403
print('v0.10.0 direct user creation + viewer role: PASS')

# Second user registers but has no household yet.
ok(child.post('/api/register',json={'username':'kind','password':'KindPasswort123!'}))
assert child.post('/api/login',json={'username':'kind','password':'KindPasswort123!','trusted_device':False}).status_code==403

# Admin creates an independent child household and switches into it.
book=ok(post(admin,'/api/books',{'name':'Haushalt Kind'}));child_book_id=book['id']
ok(post(admin,f'/api/books/{child_book_id}/switch'))
me=ok(admin.get('/api/me'));assert me['book']['name']=='Haushalt Kind'
child_path=Path(next(x for x in ok(admin.get('/api/books')) if x['id']==child_book_id)['path']);assert child_path.exists() and child_path!=shared_path

# Grant child editor access to exactly this household.
ok(put(admin,'/api/users/kind/membership',{'role':'editor'}))
# Child logs in; only child household is visible.
ok(child.post('/api/login',json={'username':'kind','password':'KindPasswort123!','trusted_device':False}))
cme=ok(child.get('/api/me'));assert cme['book']['id']==child_book_id and cme['role']=='editor' and len(cme['books'])==1,cme
# Child creates an account in its own DB.
acc=ok(post(child,'/api/accounts',{'name':'Taschengeld','type':'cash','opening_balance':'50.00','currency':'EUR','start_date':'2026-09-12'}));assert acc['id']
assert any(a['name']=='Taschengeld' for a in ok(child.get('/api/accounts')))

# Admin switches back to shared DB: child's account must not exist there.
ok(post(admin,'/api/books/default/switch'))
assert all(a['name']!='Taschengeld' for a in ok(admin.get('/api/accounts')))
# Physical database separation: account row only in child DB.
cc=sqlite3.connect(child_path);assert cc.execute("SELECT COUNT(*) FROM accounts WHERE name='Taschengeld'").fetchone()[0]==1;cc.close()
sc=sqlite3.connect(shared_path);assert sc.execute("SELECT COUNT(*) FROM accounts WHERE name='Taschengeld'").fetchone()[0]==0;sc.close()

# Viewer role blocks writes but allows reads.
ok(post(admin,f'/api/books/{child_book_id}/switch'))
ok(put(admin,'/api/users/kind/membership',{'role':'viewer'}))
# Existing child session must observe changed role dynamically.
assert child.get('/api/accounts').status_code==200
r=post(child,'/api/accounts',{'name':'DarfNicht','type':'cash','opening_balance':'1','currency':'EUR','start_date':'2026-09-12'});assert r.status_code==403,r.text

# Reset child password. Old sessions are invalidated; old password fails, new succeeds.
ok(post(admin,'/api/users/kind/reset-password',{'new_password':'NeuesKindPasswort456!'}))
assert child.get('/api/me').status_code==401
assert child.post('/api/login',json={'username':'kind','password':'KindPasswort123!','trusted_device':False}).status_code==401
ok(child.post('/api/login',json={'username':'kind','password':'NeuesKindPasswort456!','trusted_device':False}))
assert ok(child.get('/api/me'))['role']=='viewer'

# Storage endpoint reports this selected DB, not global combined storage.
st=ok(admin.get('/api/admin/storage'));assert st['database_path']==str(child_path) and st['database_bytes']>0
print('v0.10.0 multi-book/users/roles/reset: PASS')

# Bulk deletion is previewed and requires exact confirmation.
cat=ok(post(admin,'/api/categories',{'name':'Testausgabe','direction':'expense','parent_id':None}))['id']
for d in ('2026-01-10','2026-02-10','2026-03-10'):
    ok(post(admin,'/api/transactions',{'account_id':acc['id'],'amount':'5.00','booking_date':d,'name':'Löschtest','payee':'Test','category_id':cat,'status':'executed','tags':[],'splits':[]}))
prev=ok(admin.get('/api/admin/transactions-delete-preview?mode=range&from_date=2026-01-01&to_date=2026-02-28'));assert prev['count']==2,prev
bad=admin.request('DELETE','/api/admin/transactions',json={'mode':'range','from_date':'2026-01-01','to_date':'2026-02-28','confirmation':'nein'},headers={'X-CSRF-Token':csrf(admin)});assert bad.status_code==400
res=ok(admin.request('DELETE','/api/admin/transactions',json={'mode':'range','from_date':'2026-01-01','to_date':'2026-02-28','confirmation':'LÖSCHEN'},headers={'X-CSRF-Token':csrf(admin)}));assert res['deleted']==2,res
left=ok(admin.get('/api/transactions/paged?period=all&page_size=0'));assert sum(1 for x in left['items'] if x.get('name')=='Löschtest')==1
print('v0.10.0 bulk deletion guard: PASS')
# Backups are separated by household and portable backup is HPB4 for the selected book.
br=ok(post(admin,'/api/backup/rotate'));assert br['book_id']==child_book_id
assert any((main.BACKUP_DIR/child_book_id).rglob('*.db'))
raw=admin.post('/api/backup',json={'password':'BackupPasswort123!'},headers={'X-CSRF-Token':csrf(admin)});assert raw.status_code==200 and raw.content[:4]==b'HPB4'
ok(post(admin,'/api/books/default/switch'));br2=ok(post(admin,'/api/backup/rotate'));assert br2['book_id']=='default'
assert any((main.BACKUP_DIR/'default').rglob('*.db')) and any((main.BACKUP_DIR/child_book_id).rglob('*.db'))
print('v0.10.0 per-book backup separation: PASS')

shutil.rmtree(base,ignore_errors=True)
