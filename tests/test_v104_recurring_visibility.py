import sqlite3,sys,types,tempfile,shutil,calendar
from datetime import date
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main
base=Path(tempfile.mkdtemp(prefix='hp104-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()
def csrf(): return ok(client.get('/api/me'))['csrf']
def post(u,j=None): return client.post(u,json=j,headers={'X-CSRF-Token':csrf()})
def put(u,j=None): return client.put(u,json=j,headers={'X-CSRF-Token':csrf()})
ok(client.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
acc=ok(post('/api/accounts',{'name':'giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':date.today().replace(day=1).isoformat()}))['id']
cat=ok(post('/api/categories',{'name':'Wohnen','direction':'expense'}))['id']

def add_month_first(d,months=1):
    y=d.year+(d.month-1+months)//12;m=(d.month-1+months)%12+1
    return date(y,m,1)

today=date.today();next_month=add_month_first(today,1);following=add_month_first(today,2);end=date(next_month.year+1,next_month.month,1) if next_month.month==1 else date(next_month.year+(1 if next_month.month==12 else 0),(next_month.month%12)+1,1)
# initial series starts next month
r=ok(post('/api/recurring',{'account_id':acc,'category_id':cat,'name':'Miete test','amount':'100.00','next_date':next_month.isoformat(),'frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':None,'confidence':'fixed','fixed_cost':False}))
rid=r['id']
# edit effective today and move its next date beyond the end of the current version window
ok(put(f'/api/recurring/{rid}',{'account_id':acc,'category_id':cat,'name':'Miete test','amount':'100.00','next_date':following.isoformat(),'frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':add_month_first(next_month,13).isoformat(),'confidence':'fixed','fixed_cost':True,'effective_from':today.isoformat()}))
# create a future version from next month whose first actual due date is next month first
version=ok(put(f'/api/recurring/{rid}',{'account_id':acc,'category_id':cat,'name':'Miete test','amount':'100.00','next_date':next_month.isoformat(),'frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':add_month_first(next_month,13).isoformat(),'confidence':'fixed','fixed_cost':True,'effective_from':next_month.isoformat()}))
assert version['versioned'] is True,version
rows=ok(client.get('/api/recurring'))
match=[x for x in rows if x['series_id']==rid]
assert len(match)==1,rows
assert match[0]['next_date']==next_month.isoformat(),match[0]
assert match[0]['name']=='Miete test'
print('v0.10.4 versioned recurring series remains visible: PASS')
# Endpoint/list is deliberately independent from the transaction month selector.
js=(root/'static/app.js').read_text()
start=js.index('async function loadRecurring()')
block=js[start:js.index('\nfunction ',start+1) if '\nfunction ' in js[start+1:] else start+5000]
assert "api('/api/recurring')" in block
assert 'selectedMonth' not in block
assert main.APP_VERSION in {'0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.1'}
print('v0.10.4 recurring list independent of selected month: PASS')
shutil.rmtree(base,ignore_errors=True)
