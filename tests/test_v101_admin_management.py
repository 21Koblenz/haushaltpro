import sqlite3,sys,types,tempfile,shutil,json
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main

base=Path(tempfile.mkdtemp(prefix='hp101-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=5000');return c

db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()
def csrf(): return ok(client.get('/api/me'))['csrf']
def post(url,j=None): return client.post(url,json=j,headers={'X-CSRF-Token':csrf()})
def put(url,j=None): return client.put(url,json=j,headers={'X-CSRF-Token':csrf()})
def delete(url,j=None): return client.request('DELETE',url,json=j,headers={'X-CSRF-Token':csrf()})

ok(client.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
assert main.APP_VERSION in {'0.10.1','0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3'},'0.10.2'

# Create data + recurring series and verify deletion snapshot is searchable/readable.
acc=ok(post('/api/accounts',{'name':'giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}))['id']
cat=ok(post('/api/categories',{'name':'Wohnen','direction':'expense','parent_id':None}))['id']
rec=ok(post('/api/recurring',{'account_id':acc,'category_id':cat,'name':'Miete','amount':'850.00','next_date':'2026-10-01','frequency':'monthly','kind':'direct_debit','active':True,'valid_until':None,'max_amount':None,'confidence':'fixed','fixed_cost':True}))
ok(delete(f"/api/recurring/{rec['id']}?hard=true"))
timeline=ok(client.get('/api/audit/timeline?q=Miete&page=1&page_size=10'))
row=next(x for x in timeline['items'] if x['action']=='recurring.delete')
assert row['details']['snapshot']['name']=='Miete'
assert row['details']['snapshot']['amount']==-85000
assert row['details']['snapshot']['account_name']=='giro'
print('v0.10.1 recurring delete snapshot/search: PASS')

# Pagination + audit deletion with chain rebuild.
for i in range(18):
    ok(post('/api/categories',{'name':f'Kat{i}','direction':'expense','parent_id':None}))
p1=ok(client.get('/api/audit/timeline?page=1&page_size=10'));assert p1['pages']>=2 and len(p1['items'])==10 and p1['can_delete']
p2=ok(client.get('/api/audit/timeline?page=2&page_size=10'));assert p2['page']==2
victim=p1['items'][0]['id']
res=ok(delete(f'/api/audit/{victim}',{'confirmation':'LÖSCHEN'}));assert res['deleted']==victim
check=ok(client.get('/api/audit/timeline?page=1&page_size=10'));assert check['chain_ok'] is True and all(x['id']!=victim for x in check['items'])
assert any(x['action']=='audit.delete' for x in check['items'])
print('v0.10.1 audit pagination/delete/rehash: PASS')

# Book manage: create, rename, switch protection, delete non-active DB + backups.
book=ok(post('/api/books',{'name':'Kinderbuch'}));bid=book['id']
ren=ok(put(f'/api/books/{bid}',{'name':'Kinder Haushalt'}));assert ren['name']=='Kinder Haushalt'
rows=ok(client.get('/api/books'));bp=Path(next(x for x in rows if x['id']==bid)['path']);assert bp.exists()
# Cannot delete active current default? target is not active, allowed.
(main.BACKUP_DIR/bid).mkdir(parents=True,exist_ok=True);(main.BACKUP_DIR/bid/'dummy').write_text('x')
bd=ok(delete(f'/api/books/{bid}',{'confirmation':'Kinder Haushalt'}));assert bd['name']=='Kinder Haushalt' and not bp.exists() and not (main.BACKUP_DIR/bid).exists()
assert all(x['id']!=bid for x in ok(client.get('/api/books')))
print('v0.10.1 book rename/delete: PASS')

# User deletion: create normal user, make audit actions, then delete globally.
ok(post('/api/users',{'username':'kind','password':'KindPasswort123!','role':'editor'}))
child=TestClient(main.app);ok(child.post('/api/login',json={'username':'kind','password':'KindPasswort123!','trusted_device':False}))
def ccsrf(): return ok(child.get('/api/me'))['csrf']
def cpost(url,j=None): return child.post(url,json=j,headers={'X-CSRF-Token':ccsrf()})
ok(cpost('/api/categories',{'name':'KindKat','direction':'expense','parent_id':None}))
# Delete via admin.
ok(delete('/api/users/kind'))
assert child.get('/api/me').status_code==401
users=ok(client.get('/api/users'));assert all(u['username']!='kind' for u in users)
# Historical actor name survives local user-row deletion.
hist=ok(client.get('/api/audit/timeline?q=KindKat&page=1&page_size=25'))
assert any(x['username']=='kind' for x in hist['items']),hist
assert ok(client.get('/api/audit/timeline'))['chain_ok'] is True
print('v0.10.1 user delete + historical actor preservation: PASS')

# Bulk delete retains exact deleted-item manifest.
for i,d in enumerate(('2026-01-01','2026-01-02','2026-01-03')):
    ok(post('/api/transactions',{'account_id':acc,'amount':'12.34','booking_date':d,'name':f'Löschbuchung {i}','payee':'Test','category_id':cat,'status':'executed','tags':[],'splits':[]}))
ok(delete('/api/admin/transactions',{'mode':'range','from_date':'2026-01-01','to_date':'2026-01-03','confirmation':'LÖSCHEN'}))
log=ok(client.get('/api/audit/timeline?q=Löschbuchung&page=1&page_size=25'))
bulk=next(x for x in log['items'] if x['action']=='transaction.bulk_delete')
assert len(bulk['details']['deleted_items'])==3 and bulk['details']['deleted_items'][0]['name'].startswith('Löschbuchung')
print('v0.10.1 bulk-delete manifest: PASS')

shutil.rmtree(base,ignore_errors=True)
