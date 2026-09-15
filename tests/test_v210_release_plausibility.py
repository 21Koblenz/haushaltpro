import sqlite3, sys, types, tempfile
from pathlib import Path

shim = types.ModuleType('sqlcipher3')
shim.dbapi2 = sqlite3
sys.modules['sqlcipher3'] = shim
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
Path('/app').mkdir(exist_ok=True)
static = Path('/app/static')
if not static.exists():
    static.symlink_to(root / 'static', target_is_directory=True)

from app import db
fd, tmp = tempfile.mkstemp(suffix='.db')
Path(tmp).unlink(missing_ok=True)
c = sqlite3.connect(tmp, check_same_thread=False)
c.row_factory = sqlite3.Row
c.execute('PRAGMA foreign_keys=ON')
db._conn = c
db.DB_PATH = Path(tmp)
db.init_schema(c)
db.migrate_schema(c)

from app import main
main.db._conn = c
main.session = lambda request, write=False: ('release-test', 1, 'csrf', 0)
main.require_book_owner = lambda request: None
main.require_system_admin = lambda request: None
c.execute("INSERT OR IGNORE INTO users(id,username,password_hash,created_at) VALUES(1,'release-test','x','2026-01-01T00:00:00+00:00')")
c.commit()

from fastapi.testclient import TestClient
client = TestClient(main.app)

def ok(r):
    assert r.status_code < 300, (r.status_code, r.text)
    return r.json()

def close(a, b, eps=0.00001):
    assert abs(float(a)-float(b)) <= eps, (a, b)

assert main.APP_VERSION in {'0.21.0','0.21.2','0.21.3','0.21.4','0.21.5','0.21.6','0.21.7','0.21.8','0.21.9-dev'}

# Fixed independent demo dataset documented for the v0.21.0 release.
giro = ok(client.post('/api/accounts', json={'name':'Girokonto','type':'checking','opening_balance':'2000.00','currency':'EUR','start_date':'2026-01-01'}))['id']
save = ok(client.post('/api/accounts', json={'name':'Tagesgeld','type':'savings','opening_balance':'5000.00','currency':'EUR','start_date':'2026-01-01'}))['id']
cash = ok(client.post('/api/accounts', json={'name':'Bargeld','type':'cash','opening_balance':'200.00','currency':'EUR','start_date':'2026-01-01'}))['id']

income = ok(client.post('/api/categories', json={'name':'Einnahmen Test','direction':'income'}))['id']
expense = ok(client.post('/api/categories', json={'name':'Ausgaben Test','direction':'expense'}))['id']

def tx(account, amount, direction, name):
    return ok(client.post('/api/transactions', json={
        'account_id': account, 'amount': str(amount), 'direction': direction,
        'booking_date': '2026-01-10', 'name': name,
        'category_id': income if direction == 'income' else expense,
        'tags': [], 'splits': []
    }))

tx(giro, '3000.00', 'income', 'Gehalt')
tx(giro, '1000.00', 'expense', 'Miete')
tx(giro, '120.00', 'expense', 'Strom')
tx(giro, '400.00', 'expense', 'Lebensmittel')
tx(cash, '100.00', 'expense', 'Freizeit')
tx(giro, '50.00', 'income', 'Erstattung')
tx(giro, '150.00', 'expense', 'Versicherung')

transfer = ok(client.post('/api/transfers', json={
    'from_account_id': giro, 'to_account_id': save, 'amount':'500.00',
    'booking_date':'2026-01-10', 'name':'Rücklage', 'note':'v0.21.0 demo'
}))['id']

accounts = ok(client.get('/api/accounts?month=2026-01'))
amap = {x['name']: x for x in accounts}
close(amap['Girokonto']['balance'], 2880.00)
close(amap['Tagesgeld']['balance'], 5500.00)
close(amap['Bargeld']['balance'], 100.00)
close(sum(x['balance'] for x in accounts), 8480.00)

month = ok(client.get('/api/reports/categories?period=month&anchor=2026-01-01'))
close(month['income'], 3050.00)
close(month['expense'], 1770.00)
close(month['income'] - month['expense'], 1280.00)

year = ok(client.get('/api/reports/categories?period=year&anchor=2026-01-01'))
close(year['income'], 3050.00)
close(year['expense'], 1770.00)

# Transfer creates two ledger sides but must be household-neutral.
rows = ok(client.get('/api/transactions/paged?period=all&page=1&page_size=100'))['items']
tr = [x for x in rows if x.get('transfer_id') == transfer]
assert len(tr) == 2 and {x['transfer_side'] for x in tr} == {'in','out'}, tr
assert len(rows) == 9, len(rows)

# Scenario engine: a constant monthly +1,280 EUR improvement must accumulate linearly.
scenario = ok(client.post('/api/planning/what-if', json={
    'horizon_months': 12,
    'monthly_income_change': '3050.00',
    'monthly_expense_change': '1770.00',
    'monthly_savings_change': '0.00',
    'one_time_change': '0.00'
}))
close(scenario['monthly_delta'], 1280.00)
assert len(scenario['series']) == 12
for i, row in enumerate(scenario['series'], 1):
    close(row['difference'], 1280.00 * i)
close(scenario['series'][-1]['difference'], 15360.00)

# Independent reference arithmetic used in release documentation.
opening = 7200.00
income_total = 3050.00
expense_total = 1770.00
closing = opening + income_total - expense_total
close(closing, 8480.00)
for months, expected in [(1, 9760.00), (3, 12320.00), (6, 16160.00), (12, 23840.00)]:
    close(closing + months * 1280.00, expected)

# Exact cents and German CSV parsing/deduplication.
imp = ok(client.post('/api/accounts', json={'name':'CSV Test','type':'checking','opening_balance':'0.00','currency':'EUR','start_date':'2026-01-01'}))['id']
csvdata = 'Datum;Betrag;Empfänger;Verwendungszweck;Transaktions-ID\n20.01.2026;1234,56;Arbeitgeber;Bonus;v210-a\n20.01.2026;-12,34;Bäcker;Frühstück;v210-b\n'.encode()
first = ok(client.post('/api/import/csv', data={'account_id':str(imp)}, files={'file':('demo.csv',csvdata,'text/csv')}))
assert first == {'imported':2,'duplicates':0,'skipped':0}, first
second = ok(client.post('/api/import/csv', data={'account_id':str(imp)}, files={'file':('demo.csv',csvdata,'text/csv')}))
assert second == {'imported':0,'duplicates':2,'skipped':0}, second
close(main.account_balance(c, imp, main.date(2026,1,31)) / 100, 1222.22)

print('v0.21.0 release demo/plausibility: PASS')
c.close()
Path(tmp).unlink(missing_ok=True)
