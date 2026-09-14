import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import datetime
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
# Real audit user for user attribution.
c.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'admin','dummy','2026-09-11T18:00:00+00:00')"); c.commit()
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()

acc=ok(client.post('/api/accounts',json={'name':'Jahreskonto','type':'checking','opening_balance':'5000.00','currency':'EUR','start_date':'2026-01-01'}))['id']
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))['id']
exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))['id']
sav=ok(client.post('/api/categories',json={'name':'Sparen','direction':'savings'}))['id']
for payload in [
 {'category_id':inc,'name':'Gehalt','amount':'2500.00','next_date':'2026-01-25','kind':'income','fixed_cost':False},
 {'category_id':exp,'name':'Miete','amount':'900.00','next_date':'2026-01-01','kind':'direct_debit','fixed_cost':True},
 {'category_id':sav,'name':'Sparplan','amount':'500.00','next_date':'2026-01-28','kind':'direct_debit','fixed_cost':False},
]:
 ok(client.post('/api/recurring',json={'account_id':acc,'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,'confidence':'fixed',**payload}))

planning=ok(client.get('/api/planning/year?year=2026'))
dashboard=ok(client.get('/api/dashboard/year?year=2026'))
assert len(planning['months'])==12 and len(dashboard['months'])==12
assert planning['months']==dashboard['months']
assert planning['totals']==dashboard['totals']
assert planning['months'][0]['month']=='2026-01' and planning['months'][-1]['month']=='2026-12'
assert planning['totals']['planned_income']==30000.0,planning['totals']
assert planning['totals']['planned_expense']==10800.0,planning['totals']
assert planning['totals']['planned_savings']==6000.0,planning['totals']

# Audit timeline must show who did what and a parseable timestamp.
tl=ok(client.get('/api/audit/timeline?limit=100&offset=0'))
assert tl['chain_ok'] is True,tl
assert tl['total']>=6,tl
assert any(x['username']=='admin' and x['action']=='account.create' for x in tl['items']),tl['items']
assert any(x['username']=='admin' and x['action']=='recurring.create' for x in tl['items']),tl['items']
for x in tl['items'][:3]: datetime.fromisoformat(x['created_at'].replace('Z','+00:00'))
assert main.APP_VERSION in {'0.8.2','0.8.3','0.8.4','0.8.5','0.8.6','0.8.7','0.9.0','0.10.0','0.10.1','0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3','0.21.4','0.21.5','0.21.6','0.21.7'}
print('v0.8.2 year views + user audit timeline: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
