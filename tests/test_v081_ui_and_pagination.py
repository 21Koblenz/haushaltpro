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

acc=ok(client.post('/api/accounts',json={'name':'C24','type':'checking','opening_balance':'1000.00','currency':'EUR','start_date':'2025-01-01'}))['id']
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))['id']
exp=ok(client.post('/api/categories',json={'name':'Lebensmittel','direction':'expense'}))['id']

# 36 named bookings across two years.
for i in range(1,37):
    y=2025 if i<=18 else 2026
    m=((i-1)%12)+1
    d=min(20,10+(i%10))
    ok(client.post('/api/transactions',json={
        'account_id':acc,'amount':'10.01','booking_date':f'{y:04d}-{m:02d}-{d:02d}',
        'name':f'Testbuchung {i:02d}','payee':'Supermarkt' if i%2 else 'Arbeitgeber',
        'category_id':exp if i%2 else inc,'status':'executed','tags':['probe',f'nr{i}'],'splits':[]
    }))

# Monthly pagination.
r=ok(client.get('/api/transactions/paged?period=all&page=1&page_size=10'))
assert r['total']==36 and len(r['items'])==10 and r['pages']==4,r
r2=ok(client.get('/api/transactions/paged?period=all&page=4&page_size=10'))
assert len(r2['items'])==6,r2

# All means really all.
ra=ok(client.get('/api/transactions/paged?period=all&page=1&page_size=0'))
assert len(ra['items'])==36 and ra['pages']==1 and ra['page_size']==0,ra

# Year view.
ry=ok(client.get('/api/transactions/paged?period=year&year=2025&page=1&page_size=100'))
assert ry['total']==18,ry

# Search transaction name and tag.
rs=ok(client.get('/api/transactions/paged?period=all&q=Testbuchung%2007&page=1&page_size=25'))
assert rs['total']==1 and rs['items'][0]['name']=='Testbuchung 07',rs
rt=ok(client.get('/api/transactions/paged?period=all&q=nr17&page=1&page_size=25'))
assert rt['total']==1 and rt['items'][0]['name']=='Testbuchung 17',rt

# Monthly recurring creates future yearly planning data.
ok(client.post('/api/recurring',json={'account_id':acc,'category_id':inc,'name':'Monatsgehalt','amount':'2000.00','next_date':'2026-01-25','frequency':'monthly','kind':'income','max_amount':None,'active':True,'valid_until':None,'confidence':'fixed','fixed_cost':False}))
annual=ok(client.get('/api/planning/year?year=2026'))
assert len(annual['months'])==12,annual
assert annual['months'][0]['month']=='2026-01' and annual['months'][-1]['month']=='2026-12'
assert annual['totals']['planned_income']>0,annual['totals']

assert main.APP_VERSION in {'0.8.1','0.8.2','0.8.3','0.8.4','0.8.5','0.8.6','0.8.7','0.9.0','0.10.0','0.10.1','0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0'}
print('v0.8.1 transactions/year/pagination plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
