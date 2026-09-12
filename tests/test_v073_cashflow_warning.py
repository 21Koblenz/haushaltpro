import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
a=ok(client.post('/api/accounts',json={'name':'Test','type':'checking','opening_balance':5000,'currency':'EUR','start_date':'2026-09-01'}))
inc=ok(client.post('/api/categories',json={'name':'Einkommen','direction':'income'}))['id']
exp=ok(client.post('/api/categories',json={'name':'Ausgaben','direction':'expense'}))['id']
sav=ok(client.post('/api/categories',json={'name':'Sparen','direction':'savings'}))['id']
# Case A: income 2000, expenses 1800, savings 500 => consumption +200, total -300.
for payload in [
 {'category_id':inc,'name':'Gehalt','amount':2000,'next_date':'2026-09-25','kind':'income'},
 {'category_id':exp,'name':'Kosten','amount':1800,'next_date':'2026-09-20','kind':'direct_debit'},
 {'category_id':sav,'name':'Sparen','amount':500,'next_date':'2026-09-28','kind':'direct_debit'},
]:
 ok(client.post('/api/recurring',json={'account_id':a['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,'confidence':'fixed','fixed_cost':False,**payload}))
p=ok(client.get('/api/planning/overview?month=2026-09'))
cw=p['cashflow_warning']
assert cw['consumption_negative'] is False and cw['total_negative'] is True,cw
assert cw['consumption_cashflow']==200.0 and cw['total_cashflow']==-300.0,cw
# Existing 5000 buffer means no liquidity warning although total monthly cashflow is negative.
# Cashflow warning is immediate. Liquidity warning only occurs once the 5000 EUR buffer is actually exhausted.
assert p['liquidity_warnings'] and p['liquidity_warnings'][0]['date'] > '2027-01-01',p['liquidity_warnings']
# Case B: add 400 expense => consumption -200, total -700.
ok(client.post('/api/recurring',json={'account_id':a['id'],'category_id':exp,'name':'Zusatzkosten','amount':400,'next_date':'2026-09-22','frequency':'monthly','kind':'direct_debit','max_amount':None,'active':True,'valid_until':None,'confidence':'fixed','fixed_cost':False}))
p2=ok(client.get('/api/planning/overview?month=2026-09')); cw2=p2['cashflow_warning']
assert cw2['consumption_negative'] is True and cw2['total_negative'] is True,cw2
assert cw2['consumption_cashflow']==-200.0 and cw2['total_cashflow']==-700.0,cw2
print('v0.7.3 cashflow warning plausibility: PASS')
