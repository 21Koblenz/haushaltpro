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

assert main.date.today().isoformat()=='2026-09-11'
acc=ok(client.post('/api/accounts',json={'name':'Test','type':'checking','opening_balance':2000,'currency':'EUR','start_date':'2026-01-01'}))
# December selected: account/pending cutoff remains Dec 11, but upcoming payments are based on the real current date. Since real today is Sep 11, all December dates are still upcoming.
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Versicherung','amount':100,'next_date':'2026-10-05','frequency':'monthly','kind':'direct_debit','active':True}))
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Internet','amount':50,'next_date':'2026-10-15','frequency':'monthly','kind':'direct_debit','active':True}))
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Gehalt','amount':500,'next_date':'2026-10-20','frequency':'monthly','kind':'income','active':True}))
dash=ok(client.get('/api/dashboard?month=2026-12'))
assert dash['cutoff']=='2026-12-11', dash
names=[x['name'] for x in dash['next_payments']]
assert 'Versicherung' in names and 'Internet' in names and 'Gehalt' in names, names
assert dash['pending_outflows']==50.0, dash['pending_outflows']
assert dash['pending_inflows']==500.0, dash['pending_inflows']
assert all('2026-12-01' <= x['date'] <= '2026-12-31' and x['date'] > dash['today'] for x in dash['next_payments'])
a=dash['analysis']
for key in ['booked_income','booked_expense','booked_net','savings_rate_pct','average_daily_expense','remaining_outflows','remaining_inflows','top_expense_categories','monthly_overview']:
    assert key in a, key
assert len(a['monthly_overview'])==12
print('v0.3.9 month-relative pending/upcoming + analytics: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
