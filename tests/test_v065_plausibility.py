import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
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
class FrozenDate(date):
    @classmethod
    def today(cls): return cls(2026,9,11)
main.date=FrozenDate
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()

assert main.date.today().isoformat()=='2026-09-11', main.date.today()
acc=ok(client.post('/api/accounts',json={'name':'Plausibel','type':'checking','opening_balance':10000,'currency':'EUR','start_date':'2026-01-01'}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))
exp=ok(client.post('/api/categories',json={'name':'Wohnen','direction':'expense'}))
sav=ok(client.post('/api/categories',json={'name':'ETF','direction':'savings'}))
# Full-year recurring plan: 2500 income, 1000 expense, 500 saving each month.
for payload in [
    {'category_id':inc['id'],'name':'Gehalt','amount':2500,'next_date':'2026-01-25','kind':'income'},
    {'category_id':exp['id'],'name':'Miete','amount':1000,'next_date':'2026-01-01','kind':'direct_debit'},
    {'category_id':sav['id'],'name':'ETF-Sparplan','amount':500,'next_date':'2026-01-05','kind':'direct_debit'},
]:
    rr=ok(client.post('/api/recurring',json={'account_id':acc['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,**payload}))
    # Simulate contracts that really existed since January before this upgrade.
    # Remove only the API-create safeguard that marked pre-creation dates skipped.
    c.execute("UPDATE recurring SET created_at='2026-01-01T00:00:00+00:00' WHERE id=?",(rr['id'],))
    c.execute("DELETE FROM recurring_occurrences WHERE recurring_id=? AND status='skipped'",(rr['id'],))
    c.commit()

dash=ok(client.get('/api/dashboard?month=2026-10'))
# Future October must list recurring payments and mark their source.
up={x['name']:x for x in dash['next_payments']}
assert up['Miete']['date']=='2026-10-01' and up['Miete']['source']=='transaction',up
assert up['ETF-Sparplan']['date']=='2026-10-05' and up['ETF-Sparplan']['source']=='transaction',up
assert up['Gehalt']['date']=='2026-10-25' and up['Gehalt']['source']=='transaction',up
# 12-month row ends in selected month and includes all 12 rows.
months=dash['analysis']['monthly_overview']
assert len(months)==12 and months[-1]['month']=='2026-10',months
jan=[m for m in months if m['month']=='2026-01'][0]
assert jan['income']==2500 and jan['expense']==1000 and jan['savings']==500,jan
assert jan['savings_rate_pct']==60.0,jan
# Full selected calendar year forecast: 30k income, 12k consumption, 6k explicit saving,
# plus 12k retained cash = 18k total saved = 60% savings rate.
a=dash['analysis']
assert a['annual_income']==30000.0,a
assert a['annual_expense']==12000.0,a
assert a['annual_explicit_savings']==6000.0,a
assert a['annual_total_saved']==18000.0,a
assert a['annual_savings_rate_pct']==60.0,a
assert a['annual_average_monthly_saved']==1500.0,a
# Year report exposes annual savings metrics; month view stays compatible.
y=ok(client.get('/api/reports/categories?period=year&anchor=2026-01-01'))
# Report is documentation of materialised transactions only, so with no executed rows it is zero.
assert y['savings_rate_pct']==0.0 and y['average_saved']==0.0,y
js=(root/'static/app.js').read_text(); html=(root/'static/index.html').read_text(); css=(root/'static/style.css').read_text()
assert 'recurring-mark' in js and '↻' in js and 'analysisAnnualSavingsRate' in html
assert 'reportSavingsRateCard' in html and 'savings_rate_pct' in js and '.recurring-mark' in css
assert tuple(map(int,main.APP_VERSION.split('.'))) >= (0,6,5)
print('v0.6.5 documentation/forecast/savings plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
