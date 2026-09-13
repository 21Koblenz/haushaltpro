import sqlite3, sys, tempfile, types
from datetime import date as real_date
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; Path('/app').mkdir(exist_ok=True)
sm=Path('/app/static')
if sm.is_symlink() and sm.resolve()!=(root/'static').resolve(): sm.unlink()
if not sm.exists(): sm.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
class FixedDate(real_date):
 @classmethod
 def today(cls): return cls(2026,9,13)
main.date=FixedDate
from fastapi.testclient import TestClient
client=TestClient(main.app)
acc=client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}).json()['id']
r=client.post('/api/recurring',json={'account_id':acc,'category_id':1,'name':'Später fällig','amount':'100','next_date':'2026-09-20','frequency':'monthly','kind':'direct_debit','active':True,'valid_until':'2026-09-20','confidence':'fixed','fixed_cost':True})
assert r.status_code==200,r.text
rid=r.json()['id']; assert r.json()['generated_transactions']==1,r.json()
row=c.execute('SELECT booking_date,status,amount FROM transactions WHERE recurring_id=?',(rid,)).fetchone()
assert dict(row)=={'booking_date':'2026-09-20','status':'planned','amount':-10000},dict(row)
# Forecast must use the planned transaction and suppress the recurring projection.
assert main.recurring_events(c,acc,real_date(2026,9,20),real_date(2026,9,20))==[]
d=client.get('/api/dashboard?month=2026-09').json()
assert d['total_balance']==1000.0,d
assert d['pending_outflows']==100.0,d
assert d['month_end_balance']==900.0,d
# Re-sync is idempotent and must not change the economics.
sync=client.post('/api/recurring/materialize-due?month=2026-09'); assert sync.status_code==200
assert sync.json()['created']==0,sync.json()
d2=client.get('/api/dashboard?month=2026-09').json()
for k in ('total_balance','pending_outflows','pending_inflows','month_end_balance'): assert d2[k]==d[k],(k,d[k],d2[k])
print('future recurring journal rows preserve forecast exactly once: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
