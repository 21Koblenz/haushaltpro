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
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()

giro=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-01-01'}))['id']
cash=ok(client.post('/api/accounts',json={'name':'Bargeld','type':'cash','opening_balance':'0','currency':'EUR','start_date':'2026-01-01'}))['id']
food=ok(client.post('/api/categories',json={'name':'Lebensmittel','direction':'expense'}))['id']
housing=ok(client.post('/api/categories',json={'name':'Wohnen','direction':'expense'}))['id']
salary=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))['id']
bonus=ok(client.post('/api/categories',json={'name':'Bonus','direction':'income'}))['id']

def tx(amount,dt,name,cid):
    return ok(client.post('/api/transactions',json={'account_id':giro,'amount':str(amount),'booking_date':dt,'name':name,'payee':name,'category_id':cid,'status':'executed','tags':[],'splits':[]}))
# September: expenses 300 + 700 = 1000; incomes 3000 + 1000 = 4000.
tx('300','2026-09-02','REWE',food); tx('700','2026-09-03','Miete',housing)
tx('3000','2026-09-04','Gehalt',salary); tx('1000','2026-09-05','Bonus',bonus)
# August adds another 100 food / 2000 salary for yearly totals.
tx('100','2026-08-10','ALDI',food); tx('2000','2026-08-25','Gehalt August',salary)
# Internal transfer of 500 must never enter report distribution.
ok(client.post('/api/transfers',json={'from_account_id':giro,'to_account_id':cash,'amount':'500','booking_date':'2026-09-06','name':'Bargeldabhebung'}))

month=ok(client.get('/api/reports/categories?period=month&month=2026-09'))
assert month['expense']==1000.0,month
assert month['income']==4000.0,month
expense={x['category_name']:x['amount'] for x in month['items'] if x['direction']=='expense'}
income={x['category_name']:x['amount'] for x in month['items'] if x['direction']=='income'}
assert expense=={'Wohnen':700.0,'Lebensmittel':300.0},expense
assert income=={'Gehalt':3000.0,'Bonus':1000.0},income
# The frontend percentages therefore are exactly 70/30 and 75/25.
assert round(expense['Wohnen']/sum(expense.values())*100,1)==70.0
assert round(expense['Lebensmittel']/sum(expense.values())*100,1)==30.0
assert round(income['Gehalt']/sum(income.values())*100,1)==75.0
assert round(income['Bonus']/sum(income.values())*100,1)==25.0

year=ok(client.get('/api/reports/categories?period=year&year=2026'))
assert year['expense']==1100.0,year
assert year['income']==6000.0,year
assert all(x['category_name']!='Interner Transfer' for x in year['items'])
print('v0.9.0 month/year category distribution + transfer exclusion: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
