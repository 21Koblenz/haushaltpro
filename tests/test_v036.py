import sqlite3, sys, types, tempfile
from pathlib import Path
from datetime import date, timedelta

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
main.db._conn=c; main.session=lambda request, write=False: ('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code < 300, (r.status_code,r.text)
    return r.json()

acc=ok(client.post('/api/accounts',json={'name':'Test','type':'checking','opening_balance':1000,'currency':'EUR','start_date':'2026-01-01'}))
today=date.today(); future=today+timedelta(days=3)
# Manual transactions are forced to executed, but future-dated rows do not affect today's balance.
tx=ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':125,'direction':'expense','booking_date':future.isoformat(),'payee':'Zukunft','status':'planned','tags':[],'splits':[]}))
row=c.execute('SELECT status,amount FROM transactions WHERE id=?',(tx['id'],)).fetchone()
assert row['status']=='executed' and row['amount']==-12500, dict(row)
assert main.account_balance(c,acc['id'],today)==100000
assert main.projected_account_balance(c,acc['id'],future)==87500
# It also appears in upcoming payments.
dash=ok(client.get('/api/dashboard?month='+future.strftime('%Y-%m')))
assert any(x['name']=='Zukunft' for x in dash['next_payments']), dash['next_payments']

# Hard deleting a recurring series preserves already-created transaction rows.
rec=ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Miete','amount':50,'next_date':today.isoformat(),'frequency':'monthly','kind':'direct_debit','active':True}))
made=ok(client.post(f"/api/recurring/{rec['id']}/execute"))
assert c.execute('SELECT recurring_id FROM transactions WHERE id=?',(made['transaction_id'],)).fetchone()['recurring_id']==rec['id']
ok(client.delete(f"/api/recurring/{rec['id']}?hard=true"))
assert c.execute('SELECT 1 FROM recurring WHERE COALESCE(series_id,id)=?',(rec['id'],)).fetchone() is None
kept=c.execute('SELECT recurring_id,amount FROM transactions WHERE id=?',(made['transaction_id'],)).fetchone()
assert kept is not None and kept['recurring_id'] is None and kept['amount']==-5000, dict(kept)
print('v0.3.6 future booking + recurring hard-delete preservation: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
