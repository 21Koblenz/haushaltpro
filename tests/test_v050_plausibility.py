import sqlite3, sys, types, tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static=Path('/app/static')
if static.is_symlink() or static.exists():
    try:
        if static.resolve()!=(root/'static').resolve(): static.unlink()
    except Exception: pass
if not static.exists(): static.symlink_to(root/'static', target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()

acc=ok(client.post('/api/accounts',json={'name':'Plausibel','type':'checking','opening_balance':1000,'currency':'EUR','start_date':'2026-09-01'}))
exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))

# A recurring booking created in the bookings dialog must propagate into future months.
series_tx=ok(client.post('/api/transactions',json={
    'account_id':acc['id'],'amount':100,'direction':'expense','booking_date':'2026-10-31','payee':'Monatsabo',
    'category_id':exp['id'],'status':'executed','tags':[],'splits':[],
    'recurring':True,'recurring_frequency':'monthly','recurring_until':'2027-01-31'
}))
assert series_tx['recurring_id']
events=[e for e in main.recurring_events(c,acc['id'],main.date(2026,10,1),main.date(2027,1,31)) if e['series_id']==series_tx['recurring_id']]
assert [e['date'].isoformat() for e in events]==['2026-11-30','2026-12-31','2027-01-31'],events
# Critical short-month anchor: 31 -> 30/28 as needed -> back to 31, no permanent drift.
assert main.add_months(main.date(2026,1,31),1)==main.date(2026,2,28)
assert list(main.occurrences(main.date(2026,1,31),'monthly',main.date(2026,2,1),main.date(2026,3,31)))==[main.date(2026,2,28),main.date(2026,3,31)]

# Transaction editing must expose/retain recurrence metadata and version future changes.
oct_rows=ok(client.get('/api/transactions?month=2026-10'))
tx=next(x for x in oct_rows if x['id']==series_tx['id'])
assert tx['recurring'] is True and tx['recurring_frequency']=='monthly' and tx['recurring_until']=='2027-01-31',tx
ok(client.put(f"/api/transactions/{tx['id']}",json={
    'account_id':acc['id'],'amount':120,'direction':'expense','booking_date':'2026-10-31','payee':'Monatsabo',
    'category_id':exp['id'],'status':'executed','tags':[],'splits':[],
    'recurring':True,'recurring_frequency':'monthly','recurring_until':'2027-01-31','recurring_effective_from':'2026-12-01'
}))
series_id=series_tx['recurring_id']
events=main.recurring_events(c,acc['id'],main.date(2026,11,1),main.date(2027,1,31))
bydate={e['date'].isoformat():e['amount'] for e in events if e['series_id']==series_id}
assert bydate['2026-11-30']==-10000,bydate
assert bydate['2026-12-31']==-12000 and bydate['2027-01-31']==-12000,bydate
# The future dashboards must contain those series amounts.
nov=ok(client.get('/api/dashboard?month=2026-11')); dec=ok(client.get('/api/dashboard?month=2026-12'))
assert len(nov['total_forecast'])==30 and len(dec['total_forecast'])==31
assert dec['month_end_balance'] < nov['month_end_balance'],(nov['month_end_balance'],dec['month_end_balance'])

# Budget plausibility with actual/future entries and imported rows without explicit direction.
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':2000,'direction':'income','booking_date':'2026-11-01','payee':'Gehalt','category_id':inc['id'],'status':'executed','tags':[],'splits':[]}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':50,'direction':'expense','booking_date':'2026-11-15','payee':'Miete','category_id':exp['id'],'status':'executed','tags':[],'splits':[]}))
# Simulate bank CSV row: sign exists, direction may be NULL.
ts=main.iso(main.utcnow()); c.execute("INSERT INTO transactions(account_id,amount,direction,booking_date,payee,category_id,status,external_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(acc['id'],-2500,None,'2026-11-20','CSV Einkauf',exp['id'],'executed','csv-plausibility',ts,ts)); c.commit()
ok(client.put('/api/settings/budget_strategy',json={'value':'50_30_20'}))
b=ok(client.post('/api/budgets',json={'category_id':exp['id'],'month':'2026-11','amount':500,'strategy':'50_30_20','bucket':'needs','note':'Wohnen'}))
data=ok(client.get('/api/budgets?month=2026-11'))
entry=next(x for x in data['entries'] if x['id']==b['id'])
assert data['expected_income']==2000.0,data
assert data['booked_expense']==75.0,data
assert entry['spent']==75.0 and entry['remaining']==425.0,entry
assert data['strategy_metrics']['targets']=={'needs':1000.0,'wants':600.0,'savings':400.0},data['strategy_metrics']
ok(client.put(f"/api/budgets/{b['id']}",json={'category_id':exp['id'],'month':'2026-11','amount':600,'strategy':'50_30_20','bucket':'needs','note':'angepasst'}))
data=ok(client.get('/api/budgets?month=2026-11')); entry=next(x for x in data['entries'] if x['id']==b['id'])
assert entry['amount']==600.0 and entry['remaining']==525.0 and entry['note']=='angepasst',entry

html=(root/'static/index.html').read_text(); js=(root/'static/app.js').read_text()
# v0.7.0 reintroduces a planning *analysis* page; recurring entry management remains under Buchungen.
assert 'Wiederkehrende Buchungen' in html
assert 'Wiederkehrende Buchungen' in html and 'Serienänderung gültig ab' in js
for term in ['Zero-Based Budgeting','Envelope / Umschlag','50/30/20-Regel','Pay Yourself First']:
    assert term in html or term in js,term
assert 'data-bedit' in js and 'usage_pct' in js
assert tuple(map(int,main.APP_VERSION.split('.'))) >= (0,6,0)
print('v0.6.0 plausibility: recurring propagation/editing/anchor + actionable budgets + CSV-sign analytics: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
