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
acc=client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'0','currency':'EUR','start_date':'2026-09-01'}).json()['id']
# Future finite series is immediately journalized.
r=client.post('/api/recurring',json={'account_id':acc,'category_id':1,'name':'Miete','amount':'850','next_date':'2026-11-01','frequency':'monthly','kind':'direct_debit','active':True,'valid_until':'2027-10-01','confidence':'fixed','fixed_cost':True})
assert r.status_code==200,r.text
rid=r.json()['id']; assert r.json()['generated_transactions']==12,r.json()
assert c.execute("SELECT COUNT(*) FROM transactions WHERE recurring_id=? AND status='planned'",(rid,)).fetchone()[0]==12
rec=next(x for x in client.get('/api/recurring').json() if x['series_id']==rid)
assert rec['next_date']=='2026-11-01',rec
assert rec['journal_count']==12,rec
# Mistyped past start does not create historical row, only future contract dates.
p=client.post('/api/recurring',json={'account_id':acc,'category_id':1,'name':'Falsches Datum','amount':'80','next_date':'2026-09-12','frequency':'monthly','kind':'direct_debit','active':True,'valid_until':'2026-11-12','confidence':'fixed','fixed_cost':True})
pid=p.json()['id']; dates=[x[0] for x in c.execute('SELECT booking_date FROM transactions WHERE recurring_id=? ORDER BY booking_date',(pid,)).fetchall()]
assert dates==['2026-10-12','2026-11-12'],dates
# UI is journal-first; no manual future materialization button remains.
js=(root/'static/app.js').read_text(encoding='utf-8')+(root/'static/overview-cards.js').read_text(encoding='utf-8')
assert 'recurring.inJournal' in js
# Planned/posted card labels are exercised in payments-ui.test.cjs.
assert 'data-exec' not in js and 'recurring.materializeNow' not in js
print('recurring schedule is immediately visible in journal: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
