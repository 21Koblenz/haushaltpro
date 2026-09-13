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

acc=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'10000','currency':'EUR','start_date':'2026-01-01'}))['id']

def cat(name,direction): return ok(client.post('/api/categories',json={'name':name,'direction':direction}))['id']
cats={
 'Einkommen ich':cat('Einkommen ich','income'), 'Einkommen Frau':cat('Einkommen Frau','income'),
 'Miete':cat('Miete','expense'), 'Essen':cat('Essen','expense'), 'Sonstiges':cat('Sonstiges','expense'),
 'ETF':cat('ETF','savings'), 'Bitcoin':cat('Bitcoin','savings'),
}
def tx(amount,name,cid,day):
    return ok(client.post('/api/transactions',json={'account_id':acc,'amount':str(amount),'booking_date':f'2026-09-{day:02d}','name':name,'payee':name,'category_id':cid,'status':'executed','tags':[],'splits':[]}))
# income 75/25
for amount,name,day in [(3000,'Einkommen ich',1),(1000,'Einkommen Frau',2)]: tx(amount,name,cats[name],day)
# expenses 60/30/10 of their OWN group
for amount,name,day in [(600,'Miete',3),(300,'Essen',4),(100,'Sonstiges',5)]: tx(amount,name,cats[name],day)
# savings 80/20 of their OWN group
for amount,name,day in [(800,'ETF',6),(200,'Bitcoin',7)]: tx(amount,name,cats[name],day)

r=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))

def shares(direction):
    rows=[x for x in r['items'] if x['direction']==direction]
    total=sum(float(x['amount']) for x in rows)
    return {x['category_name']:round(float(x['amount'])/total*100,1) for x in rows}

assert shares('income')=={'Einkommen ich':75.0,'Einkommen Frau':25.0}, shares('income')
assert shares('expense')=={'Miete':60.0,'Essen':30.0,'Sonstiges':10.0}, shares('expense')
assert shares('savings')=={'ETF':80.0,'Bitcoin':20.0}, shares('savings')
print('Preview 13 API group shares income/expense/savings: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
