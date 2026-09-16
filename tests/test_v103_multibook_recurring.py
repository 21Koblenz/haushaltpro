import sqlite3,sys,types,tempfile,shutil
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main
from datetime import date as real_date
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,14)
main.date=FixedDate

base=Path(tempfile.mkdtemp(prefix='hp103-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
admin=TestClient(main.app);user=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()
def csrf(c): return ok(c.get('/api/me'))['csrf']
def post(c,u,j=None): return c.post(u,json=j,headers={'X-CSRF-Token':csrf(c)})
def put(c,u,j=None): return c.put(u,json=j,headers={'X-CSRF-Token':csrf(c)})
ok(admin.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
book2=ok(post(admin,'/api/books',{'name':'Kind'}))['id']
ok(user.post('/api/register',json={'username':'multi','password':'MehrereBuecher123!'}))
# Grant two books independently. Second grant must not replace the first.
ok(put(admin,'/api/users/multi/membership',{'role':'viewer','book_id':'default'}))
ok(put(admin,'/api/users/multi/membership',{'role':'editor','book_id':book2}))
rows=ok(admin.get('/api/users'));u=next(x for x in rows if x['username']=='multi')
assert u['memberships']['default']=='viewer',u
assert u['memberships'][book2]=='editor',u
assert u['book_count']==2,u
ok(user.post('/api/login',json={'username':'multi','password':'MehrereBuecher123!','trusted_device':False}))
me=ok(user.get('/api/me'));assert len(me['books'])==2,me
print('v0.10.3 multiple household memberships: PASS')

# Recurring API: direct series must immediately appear in recurring list.
# Use admin/default database.
acc=ok(post(admin,'/api/accounts',{'name':'giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}))['id']
cat=ok(post(admin,'/api/categories',{'name':'Transport','direction':'expense'}))['id']
r=ok(post(admin,'/api/recurring',{'account_id':acc,'category_id':cat,'name':'testwiederholung','amount':'212.00','next_date':'2026-09-15','frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':None,'confidence':'fixed','fixed_cost':False}))
series=ok(admin.get('/api/recurring'))
row=next((x for x in series if x['id']==r['id']),None)
assert row and row['name']=='testwiederholung',series
assert row['next_date']=='2026-09-15',row
assert row['journal_count']==24,row
print('v0.10.3 direct recurring series visible immediately: PASS')

# A transaction explicitly marked recurring must also have a linked series visible.
t=ok(post(admin,'/api/transactions',{'account_id':acc,'amount':'5.00','booking_date':'2026-09-12','name':'test','payee':None,'category_id':cat,'status':'executed','tags':[],'splits':[],'recurring':True,'recurring_frequency':'monthly','recurring_until':None,'confidence':'fixed','fixed_cost':False}))
assert t['recurring_id'] is not None,t
series2=ok(admin.get('/api/recurring'))
assert any(x['series_id']==t['recurring_id'] for x in series2),series2
print('v0.10.3 recurring transaction linked and listed: PASS')

js=(root/'static/app.js').read_text();html=(root/'static/index.html').read_text();css=(root/'static/style.css').read_text()
assert "$('newRecurringTx').onclick=()=>recDialog(null);" in js
assert 'data-membership-user' in js and 'membership-grid' in css
assert 'txRecurringCount' in html and 'Aktive Serien' in html
assert main.APP_VERSION in {'0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3','0.21.4','0.21.5','0.21.6','0.21.7','0.21.8','0.21.9-dev.3'}
print('v0.10.3 UI source: PASS')
shutil.rmtree(base,ignore_errors=True)
