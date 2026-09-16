import sqlite3
import sys
import tempfile
import types
from datetime import date as real_date
from pathlib import Path

shim = types.ModuleType('sqlcipher3')
shim.dbapi2 = sqlite3
sys.modules['sqlcipher3'] = shim
root = Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static_mount = Path('/app/static')
if static_mount.is_symlink() and static_mount.resolve() != (root / 'static').resolve():
    static_mount.unlink()
if not static_mount.exists():
    static_mount.symlink_to(root / 'static', target_is_directory=True)
sys.path.insert(0, str(root))

from app import db
fd, tmp = tempfile.mkstemp(suffix='.db')
Path(tmp).unlink(missing_ok=True)
c = sqlite3.connect(tmp, check_same_thread=False)
c.row_factory = sqlite3.Row
c.execute('PRAGMA foreign_keys=ON')
db._conn = c
db.DB_PATH = Path(tmp)
db.init_schema(c)

from app import main
main.db._conn = c
main.session = lambda request, write=False: ('test', 1, 'csrf', 0)

class FixedDate(real_date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 13)
main.date = FixedDate

from fastapi.testclient import TestClient
client = TestClient(main.app)

acc = client.post('/api/accounts', json={
    'name':'Giro','type':'checking','opening_balance':'1000.00','currency':'EUR','start_date':'2026-09-01'
})
assert acc.status_code == 200, acc.text
account_id = acc.json()['id']

# A finite two-year monthly contract must be fully visible in Transactions immediately.
contract = client.post('/api/recurring', json={
    'account_id':account_id,'category_id':1,'name':'Miete 2 Jahre','amount':'900.00',
    'next_date':'2026-11-01','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2028-10-01','confidence':'fixed','fixed_cost':True,
})
assert contract.status_code == 200, contract.text
contract_id = contract.json()['id']
assert contract.json()['generated_transactions'] == 24, contract.json()
rows = c.execute("SELECT booking_date,amount,status,recurring_id FROM transactions WHERE recurring_id=? ORDER BY booking_date",(contract_id,)).fetchall()
assert len(rows) == 24, len(rows)
assert rows[0]['booking_date'] == '2026-11-01' and rows[-1]['booking_date'] == '2028-10-01'
assert all(r['amount'] == -90000 for r in rows)
assert all(r['status'] == 'planned' for r in rows)
# The master series remains an edit/overview item even though every occurrence is already in the journal.
rec = next(x for x in client.get('/api/recurring').json() if x['series_id'] == contract_id)
assert rec['next_date'] == '2026-11-01', rec
assert rec['journal_count'] == 24, rec
# No duplicate recurring projection remains for already materialised contract dates.
assert main.recurring_events(c, account_id, real_date(2026,11,1), real_date(2028,10,1)) == []

# A future occurrence in the current month is immediately visible but remains planned.
future = client.post('/api/recurring', json={
    'account_id':account_id,'category_id':1,'name':'Versicherung geplant','amount':'100.00',
    'next_date':'2026-09-20','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2026-11-20','confidence':'fixed','fixed_cost':True,
})
assert future.status_code == 200, future.text
future_id = future.json()['id']
assert future.json()['generated_transactions'] == 3, future.json()
page = client.get('/api/transactions/paged?period=month&month=2026-09&page=1&page_size=100').json()
row = next(x for x in page['items'] if x.get('recurring_id') == future_id)
assert row['booking_date'] == '2026-09-20', row
assert row['status'] == 'planned', row
assert row['recurring'] is True, row

# Dashboard/projection counts that future planned transaction exactly once.
dash = client.get('/api/dashboard?month=2026-09')
assert dash.status_code == 200, dash.text
d = dash.json()
assert d['total_balance'] == 1000.0, d
assert d['pending_outflows'] == 100.0, d
assert d['month_end_balance'] == 900.0, d
assert not main.recurring_events(c, account_id, real_date(2026,9,20), real_date(2026,9,20))

# Due-today and later automatically generated occurrences remain planned until explicitly settled.
due = client.post('/api/recurring', json={
    'account_id':account_id,'category_id':1,'name':'Heute und später','amount':'50.00',
    'next_date':'2026-09-13','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2026-11-13','confidence':'fixed','fixed_cost':True,
})
assert due.status_code == 200, due.text
due_id = due.json()['id']
due_rows = c.execute("SELECT booking_date,status FROM transactions WHERE recurring_id=? ORDER BY booking_date",(due_id,)).fetchall()
assert [r['status'] for r in due_rows] == ['planned','planned','planned'], [dict(r) for r in due_rows]

# A mistaken past start date does not invent a historical transaction, but future schedule rows are still generated.
past = client.post('/api/recurring', json={
    'account_id':account_id,'category_id':1,'name':'Falsches Startdatum','amount':'80.00',
    'next_date':'2026-09-12','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2026-11-12','confidence':'fixed','fixed_cost':True,
})
assert past.status_code == 200, past.text
past_id = past.json()['id']
past_rows = c.execute("SELECT booking_date,status FROM transactions WHERE recurring_id=? ORDER BY booking_date",(past_id,)).fetchall()
assert [r['booking_date'] for r in past_rows] == ['2026-10-12','2026-11-12'], [dict(r) for r in past_rows]
assert all(r['status']=='planned' for r in past_rows)
missed = c.execute("SELECT status FROM recurring_occurrences WHERE recurring_id=? AND due_date='2026-09-12'",(past_id,)).fetchone()
assert missed and missed['status']=='skipped', missed

# Stopping a contract removes its future planned schedule, not executed history.
stop = client.delete(f'/api/recurring/{future_id}')
assert stop.status_code == 200, stop.text
assert c.execute("SELECT COUNT(*) FROM transactions WHERE recurring_id=? AND status='planned'",(future_id,)).fetchone()[0] == 0

# UI no longer exposes a manual 'materialize future' action and marks planned recurring rows.
js=(root/'static/app.js').read_text(encoding='utf-8')+(root/'static/transaction-cards.js').read_text(encoding='utf-8')
# Planned/posted card labels are exercised in payments-ui.test.cjs.
assert "data-exec" not in js
assert "recurring.materializeNow" not in js

print('full recurring contract schedule -> journal + no forecast double count: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
