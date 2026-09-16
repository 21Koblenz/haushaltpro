import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
# audit user must exist for username resolution
c.execute("INSERT OR IGNORE INTO users(id,username,password_hash,created_at) VALUES(1,'admin','x','2026-01-01T00:00:00+00:00')"); c.commit()
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()

giro=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000.00','currency':'EUR','start_date':'2026-09-01'}))['id']
cash=ok(client.post('/api/accounts',json={'name':'Bargeld','type':'cash','opening_balance':'100.00','currency':'EUR','start_date':'2026-09-01'}))['id']
food=ok(client.post('/api/categories',json={'name':'Test-Lebensmittel','direction':'expense'}))['id']

# Payee opt-in: without checkbox nothing is retained.
tx1=ok(client.post('/api/transactions',json={'account_id':giro,'amount':'20.00','booking_date':'2026-09-12','name':'Einkauf','payee':'ALDI','category_id':food,'tags':[],'splits':[],'remember_payee':False}))['id']
assert ok(client.get('/api/payees'))==[]
# Explicit opt-in learns and increments usage only on explicit opt-in.
ok(client.post('/api/transactions',json={'account_id':giro,'amount':'30.00','booking_date':'2026-09-12','name':'Einkauf 2','payee':'REWE','category_id':food,'tags':[],'splits':[],'remember_payee':True}))
payees=ok(client.get('/api/payees')); assert len(payees)==1 and payees[0]['name']=='REWE' and payees[0]['usage_count']==1,payees
ok(client.post('/api/transactions',json={'account_id':giro,'amount':'10.00','booking_date':'2026-09-12','name':'Einkauf 3','payee':'REWE','category_id':food,'tags':[],'splits':[],'remember_payee':True}))
payees=ok(client.get('/api/payees')); assert payees[0]['usage_count']==2,payees
# Rename preset doesn't alter existing booking payees.
ok(client.put('/api/payees/'+str(payees[0]['id']),json={'name':'REWE Markt'}))
assert ok(client.get('/api/transactions/paged?period=all&page_size=100'))['items'][0]['payee']=='REWE'

# Transfer: account balances change, household total and category report don't.
tr=ok(client.post('/api/transfers',json={'from_account_id':giro,'to_account_id':cash,'amount':'200.00','booking_date':'2026-09-12','name':'Bargeld abheben','note':'ATM'}))['id']
rows=ok(client.get('/api/transactions/paged?period=all&page_size=100'))['items']
trrows=[x for x in rows if x.get('transfer_id')==tr]
assert len(trrows)==2 and {x['transfer_side'] for x in trrows}=={'out','in'},trrows
# Before transfer: Giro 1000-20-30-10=940, cash=100. After 200 transfer: 740 / 300.
accounts=ok(client.get('/api/accounts?month=2026-09')); amap={x['name']:x for x in accounts}
assert amap['Giro']['balance']==740.0,amap['Giro']
assert amap['Bargeld']['balance']==300.0,amap['Bargeld']
assert round(amap['Giro']['balance']+amap['Bargeld']['balance'],2)==1040.0
report=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report['expense']==60.0 and report['income']==0.0,report

# Transfer update remains paired and neutral to household/category totals.
ok(client.put('/api/transfers/'+str(tr),json={'from_account_id':giro,'to_account_id':cash,'amount':'150.00','booking_date':'2026-09-12','name':'Bargeld abheben','note':'ATM korrigiert'}))
accounts=ok(client.get('/api/accounts?month=2026-09')); amap={x['name']:x for x in accounts}
assert amap['Giro']['balance']==790.0 and amap['Bargeld']['balance']==250.0,amap
assert round(amap['Giro']['balance']+amap['Bargeld']['balance'],2)==1040.0
report=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01')); assert report['expense']==60.0,report

# Audit update contains changed field AND complete current context for unchanged fields.
old=next(x for x in ok(client.get('/api/transactions/paged?period=all&page_size=100'))['items'] if x['id']==tx1)
payload={'account_id':giro,'amount':'19.80','booking_date':'2026-09-12','name':'Einkauf','payee':'ALDI','category_id':food,'tags':['test'],'splits':[],'remember_payee':False,'confidence':'fixed','fixed_cost':False}
ok(client.put('/api/transactions/'+str(tx1),json=payload))
audit=ok(client.get('/api/audit/timeline?limit=100&offset=0'))
entry=next(x for x in audit['items'] if x['action']=='transaction.update' and str(x['entity_id'])==str(tx1))
assert entry['username']=='admin',entry
assert entry['details']['changes']['amount']['old']==-2000 and entry['details']['changes']['amount']['new']==-1980,entry
current=entry['details']['current']; assert current['name']=='Einkauf' and current['payee']=='ALDI' and current['account_name']=='Giro' and current['category_name']=='Test-Lebensmittel' and current['tags']==['test'],current

# Transfer audit context is human-readable.
trentry=next(x for x in audit['items'] if x['action']=='transfer.update')
assert trentry['details']['current']['from_account_name']=='Giro' and trentry['details']['current']['to_account_name']=='Bargeld'

assert main.APP_VERSION in {'0.9.0','0.10.0','0.10.1','0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3','0.21.4','0.21.5','0.21.6','0.21.7','0.21.8','0.21.9-dev.3'}
print('v0.9.0 transfers/payees/audit plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
