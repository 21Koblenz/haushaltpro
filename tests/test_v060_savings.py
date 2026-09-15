import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
if static.is_symlink() or static.exists():
    try:
        if static.resolve()!=(root/'static').resolve(): static.unlink()
    except Exception: pass
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
acc=ok(client.post('/api/accounts',json={'name':'Test','type':'checking','opening_balance':5000,'currency':'EUR','start_date':'2026-01-01'}))
inc=ok(client.post('/api/categories',json={'name':'Lohn','direction':'income'}))
exp=ok(client.post('/api/categories',json={'name':'MieteX','direction':'expense'}))
sav=ok(client.post('/api/categories',json={'name':'ETF Sparplan','direction':'savings'}))
# Category alone decides the transaction type; no direction is needed.
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':2000,'booking_date':'2026-09-01','payee':'Lohn','category_id':inc['id'],'tags':[],'splits':[]}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':1000,'booking_date':'2026-09-02','payee':'Miete','category_id':exp['id'],'tags':[],'splits':[]}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':500,'booking_date':'2026-09-03','payee':'ETF','category_id':sav['id'],'tags':[],'splits':[]}))
r=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert r['income']==2000 and r['expense']==1000 and r['savings']==500,r
assert r['savings_rate_pct']==50.0,r
assert r['average_saved']>0 and r['average_saved_unit']=='day',r
# The same actual bookings must also produce the same savings rate in the annual report.
yr=ok(client.get('/api/reports/categories?period=year&anchor=2026-01-01'))
assert yr['income']==2000 and yr['expense']==1000 and yr['savings']==500,yr
assert yr['savings_rate_pct']==50.0,yr
assert yr['average_saved']>0 and yr['average_saved_unit']=='month',yr
# Savings is not consumption and contributes to the saving rate. For 2000 income, 1000 expense, 500 explicit savings + 500 retained cash = 50%.
d=ok(client.get('/api/dashboard?month=2026-09'))
assert d['analysis']['booked_savings']==500,d['analysis']
assert d['analysis']['average_daily_income']>0 and d['analysis']['average_daily_savings']>0
assert d['analysis']['savings_rate_pct']==50.0,d['analysis']
# 12-month overview must END with selected month, not previous month.
assert d['analysis']['monthly_overview'][-1]['month']=='2026-09',d['analysis']['monthly_overview'][-1]
assert d['analysis']['monthly_overview'][-1]['savings']==500
# Recurring monthly savings must propagate into future months.
rt=ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':100,'booking_date':'2026-10-15','payee':'Sparplan','category_id':sav['id'],'tags':[],'splits':[],'recurring':True,'recurring_frequency':'monthly'}))
rows=c.execute("SELECT booking_date,status FROM transactions WHERE recurring_id=? AND booking_date BETWEEN '2026-11-01' AND '2027-02-28' ORDER BY booking_date",(rt['recurring_id'],)).fetchall()
dates=[r['booking_date'] for r in rows]
assert dates==['2026-11-15','2026-12-15','2027-01-15','2027-02-15'],dates
assert all(r['status']=='planned' for r in rows),[dict(r) for r in rows]
assert main.recurring_events(c,acc['id'],main.date(2026,11,1),main.date(2027,2,28))==[]
nov=ok(client.get('/api/dashboard?month=2026-11')); dec=ok(client.get('/api/dashboard?month=2026-12'))
assert nov['month_end_balance']-dec['month_end_balance']>=100, (nov['month_end_balance'],dec['month_end_balance'])
js=(root/'static/app.js').read_text(); html=(root/'static/index.html').read_text()
assert '<label>Art<select' not in js and 'Sparen' in js and 'analysisDailyIncome' in html and 'analysisDailySavings' in html
assert tuple(map(int,main.APP_VERSION.split('-',1)[0].split('.'))) >= (0,6,0)
print('v0.6.0 savings/category-only/12-month/recurring plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
