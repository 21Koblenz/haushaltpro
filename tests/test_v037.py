import sqlite3, sys, types, tempfile
from pathlib import Path
from datetime import date

shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static', target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp, check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
class FrozenDate(date):
    @classmethod
    def today(cls): return cls(2026,9,11)
main.date=FrozenDate
main.db._conn=c; main.session=lambda request, write=False: ('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code < 300, (r.status_code,r.text)
    return r.json()

assert main.date.today().isoformat() == '2026-09-11'
acc=ok(client.post('/api/accounts',json={'name':'Test','type':'checking','opening_balance':1000,'currency':'EUR','start_date':'2026-01-01'}))
# Two monthly outflows before/on the 10th. They must already be included in December's "Bis heute".
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Miete','amount':500,'next_date':'2026-10-01','frequency':'monthly','kind':'direct_debit','active':True}))
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Versicherung','amount':100,'next_date':'2026-10-05','frequency':'monthly','kind':'direct_debit','active':True}))

dash=ok(client.get('/api/dashboard?month=2026-12'))
a=dash['accounts'][0]
assert a['balance_cutoff']=='2026-12-11', a
assert a['month_start_balance']==-200.0, a       # Oct + Nov already deducted
assert a['balance']==-800.0, a                  # Dec 1 + Dec 5 deducted through Dec 11
assert a['month_end_balance']==-800.0, a
series=a['forecast']
assert len(series)==31 and series[0]['date']=='2026-12-01' and series[-1]['date']=='2026-12-31'
assert series[0]['opening_balance']==-200.0 and series[0]['balance']==-700.0, series[:2]  # opening is prior month end; day 1 point is after day-1 movements
assert series[1]['balance']==-700.0, series[:3]  # rent from Dec 1 visible from start of Dec 2
assert series[5]['balance']==-800.0, series[:7]  # insurance from Dec 5 visible from start of Dec 6
print('v0.3.7 selected-month same-day cutoff + projected recurring outflows: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
