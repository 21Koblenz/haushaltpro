import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
aid=client.post('/api/accounts',json={'name':'Perf','type':'checking','opening_balance':'0','currency':'EUR','start_date':'2026-01-01'}).json()['id']
cid=client.post('/api/categories',json={'name':'PerfCat','direction':'expense'}).json()['id']
for i in range(150):
    r=client.post('/api/transactions',json={'account_id':aid,'amount':'1.00','booking_date':'2026-09-12','name':f'B{i}','payee':'P','category_id':cid,'tags':['x','y'],'splits':[]})
    assert r.status_code<300,r.text
seen=[]
c.set_trace_callback(lambda q: seen.append(q) if q.lstrip().upper().startswith('SELECT') else None)
r=client.get('/api/transactions/paged?period=all&page=1&page_size=100'); assert r.status_code==200,r.text
c.set_trace_callback(None)
assert len(r.json()['items'])==100
# Count/rows/tags/splits plus a small fixed amount of metadata lookups. It must not scale as 2-3 SELECTs per row.
assert len(seen)<15,(len(seen),seen[:20])
print(f'v0.9.0 paged transaction query count: PASS ({len(seen)} SELECTs for 100 rows)')
c.close(); Path(tmp).unlink(missing_ok=True)
