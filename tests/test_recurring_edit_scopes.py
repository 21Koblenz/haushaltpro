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
    'name':'Giro','type':'checking','opening_balance':'0','currency':'EUR','start_date':'2026-09-01'
})
assert acc.status_code == 200, acc.text
account_id = acc.json()['id']

# Base contract: four monthly planned journal rows.
created = client.post('/api/recurring', json={
    'account_id':account_id,'category_id':1,'name':'Miete','amount':'900.00',
    'next_date':'2026-11-01','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2027-02-01','confidence':'fixed','fixed_cost':True,
})
assert created.status_code == 200, created.text
rid = created.json()['id']
assert created.json()['generated_transactions'] == 4, created.json()

# One-month exception: December only.
override = client.put(f'/api/recurring/{rid}/override', json={
    'due_date':'2026-12-01','amount':'950.00','note':'Nebenkosten-Nachzahlung'
})
assert override.status_code == 200, override.text
rows = c.execute("SELECT booking_date,amount,status FROM transactions WHERE recurring_id=? ORDER BY booking_date", (rid,)).fetchall()
assert [(r['booking_date'], r['amount'], r['status']) for r in rows] == [
    ('2026-11-01', -90000, 'planned'),
    ('2026-12-01', -95000, 'planned'),
    ('2027-01-01', -90000, 'planned'),
    ('2027-02-01', -90000, 'planned'),
]

# Series change from X: January and later change, December one-off remains intact.
updated = client.put(f'/api/recurring/{rid}', json={
    'account_id':account_id,'category_id':1,'name':'Miete neu','amount':'1000.00',
    'next_date':'2027-01-01','frequency':'monthly','kind':'direct_debit','active':True,
    'valid_until':'2027-02-01','confidence':'fixed','fixed_cost':True,
    'effective_from':'2027-01-01',
})
assert updated.status_code == 200, updated.text
rows = c.execute("""SELECT t.booking_date,t.amount,t.status,r.name
                    FROM transactions t JOIN recurring r ON r.id=t.recurring_id
                    WHERE COALESCE(r.series_id,r.id)=? ORDER BY t.booking_date""", (rid,)).fetchall()
assert [(r['booking_date'], r['amount'], r['status']) for r in rows] == [
    ('2026-11-01', -90000, 'planned'),
    ('2026-12-01', -95000, 'planned'),
    ('2027-01-01', -100000, 'planned'),
    ('2027-02-01', -100000, 'planned'),
], [dict(r) for r in rows]
assert c.execute("SELECT amount FROM recurring_overrides WHERE series_id=? AND due_date='2026-12-01'", (rid,)).fetchone()['amount'] == -95000

# Re-synchronization must be idempotent and must not duplicate/revert the one-month exception.
sync = client.post('/api/recurring/materialize-due')
assert sync.status_code == 200, sync.text
rows2 = c.execute("""SELECT t.booking_date,t.amount,t.status
                     FROM transactions t JOIN recurring r ON r.id=t.recurring_id
                     WHERE COALESCE(r.series_id,r.id)=? ORDER BY t.booking_date""", (rid,)).fetchall()
assert [(r['booking_date'], r['amount'], r['status']) for r in rows2] == [
    ('2026-11-01', -90000, 'planned'),
    ('2026-12-01', -95000, 'planned'),
    ('2027-01-01', -100000, 'planned'),
    ('2027-02-01', -100000, 'planned'),
]

# UI contract: transaction-row edit for a recurring row is a one-occurrence override;
# editing the series remains a separate action in the recurring overview.
js = (root/'static/app.js').read_text(encoding='utf-8')
assert 'function recurringTransactionOverrideDialog(tx)' in js
assert "row?.recurring?recurringTransactionOverrideDialog(row):txDialog(row)" in js
assert 'Die Serienänderung ab einem Stichtag erfolgt unter „Wiederkehrende Buchungen“.' in js
assert "const activeMonth=$('txPeriod')?.value==='month'?monthValue('txMonthName','txYear'):selectedMonth" in js

print('recurring edit scopes: one occurrence + series from X + resync idempotence: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
