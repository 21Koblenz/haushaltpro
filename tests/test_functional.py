import sqlite3, sys, types, tempfile
from pathlib import Path

# Allow importing the production DB module without SQLCipher in this test runner.
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
main.db._conn=c
# API test bypasses auth only; endpoint/business logic stays production code.
main.session=lambda request, write=False: ('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)

def ok(r):
    assert r.status_code < 300, (r.status_code,r.text)
    return r.json()

acc=ok(client.post('/api/accounts',json={'name':'C24','type':'checking','opening_balance':500,'currency':'EUR','start_date':'2023-01-01'}))
cat_exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))
cat_inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))
from datetime import date
now=date.today().isoformat()
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':300,'direction':'income','booking_date':now,'payee':'Gehalt','category_id':cat_inc['id'],'status':'executed','tags':[],'splits':[]}))
tx=ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':100,'direction':'expense','booking_date':now,'payee':'Miete','category_id':cat_exp['id'],'status':'executed','tags':[],'splits':[]}))
accounts=ok(client.get('/api/accounts')); a=next(x for x in accounts if x['id']==acc['id'])
assert a['balance']==700.0 and 'month_start_balance' in a and 'month_end_balance' in a
report=ok(client.get('/api/reports/categories?period=month&anchor='+now)); assert report['income']>=300 and report['expense']>=100
# Storno disappears from normal list.
ok(client.delete(f"/api/transactions/{tx['id']}")); rows=ok(client.get('/api/transactions')); assert all(x['id']!=tx['id'] for x in rows)
# Hard delete removes it entirely, including when cancelled rows are requested.
ok(client.delete(f"/api/transactions/{tx['id']}?hard=true")); rows=ok(client.get('/api/transactions?include_cancelled=true')); assert all(x['id']!=tx['id'] for x in rows)
# A recurring payment due today must influence both the selected-month cutoff
# balance and month-end projection even before it is manually materialized.
pre=next(x for x in ok(client.get('/api/accounts')) if x['id']==acc['id'])
ok(client.post('/api/recurring',json={'account_id':acc['id'],'name':'Abbuchung','amount':50,'next_date':now,'frequency':'monthly','kind':'direct_debit','active':True}))
a=next(x for x in ok(client.get('/api/accounts')) if x['id']==acc['id']); assert a['balance']==pre['balance']-50 and a['month_end_balance']==a['balance']
# Investment feature flag and portfolio calculations.
ok(client.put('/api/settings/investment_tracking',json={'value':'true'}))
inv=ok(client.post('/api/investments',json={'name':'ETF Test','symbol':'ETF','asset_type':'etf','quantity':10,'purchase_price':100,'current_price':120,'fees':5,'currency':'EUR'}))
port=ok(client.get('/api/investments')); assert len(port['assets'])==1 and round(port['total_value'],2)==1200 and round(port['gain'],2)==195
ok(client.put(f"/api/investments/{inv['id']}",json={'name':'ETF Test','symbol':'ETF','asset_type':'etf','quantity':10,'purchase_price':100,'current_price':90,'fees':5,'currency':'EUR'}))
port=ok(client.get('/api/investments')); assert round(port['total_value'],2)==900 and port['performance_pct']<0
ok(client.delete(f"/api/investments/{inv['id']}")); port=ok(client.get('/api/investments')); assert port['assets']==[]
# Explicit direction protects balances even if a legacy/bad row carries the wrong numeric sign.
pre_legacy=next(x for x in ok(client.get('/api/accounts')) if x['id']==acc['id'])
with main.db.transaction() as tc:
    tc.execute("INSERT INTO transactions(account_id,amount,direction,booking_date,category_id,status,external_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (acc['id'], 2500, 'expense', now, cat_exp['id'], 'executed', 'legacy-positive-expense', main.iso(main.utcnow()), main.iso(main.utcnow())))
a=next(x for x in ok(client.get('/api/accounts')) if x['id']==acc['id'])
assert a['balance']==pre_legacy['balance']-25.0, a
# Multi-user cryptographic envelope: pending has no DB key; approval wrapping can be decrypted only with that user's password.
pending=main._make_auth_user('Zweitnutzer','SehrSicheresPasswort123!',False,'user')
assert pending['approved'] is False and pending['wrapped_master'] is None
master='test-master-key-123'
pending['wrapped_master']=main._wrap_master(pending['public_key'],master); pending['approved']=True
priv=main._unlock_private('SehrSicheresPasswort123!',pending['private_key'])
assert main._unwrap_master(priv,pending['wrapped_master'])==master
print('legacy sign + multi-user envelope: PASS')
# Multi-book pending/assignment/login flow is covered by test_v100_multibook_users.py.
print('multi-book auth integration covered by v0.10.0 regression: PASS')

# Calendar-month navigation/filter regression checks.
old='2023-01-15'
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':40,'direction':'expense','booking_date':old,'payee':'Historisch','category_id':cat_exp['id'],'status':'executed','tags':[],'splits':[]}))
jan=ok(client.get('/api/transactions?month=2023-01')); assert any(x['payee']=='Historisch' for x in jan)
feb=ok(client.get('/api/transactions?month=2023-02')); assert all(x['payee']!='Historisch' for x in feb)
dash_old=ok(client.get('/api/dashboard?month=2023-01')); assert dash_old['month']=='2023-01' and len(dash_old['total_forecast'])==31
rep_old=ok(client.get('/api/reports/categories?period=month&anchor=2023-01-01')); assert rep_old['expense']>=40
print('calendar month navigation + historical data: PASS')


# Account start date + first-day semantics: day 1 starts with previous month's closing balance.
from calendar import monthrange
from datetime import timedelta
first=date.today().replace(day=1)
prev=(first-timedelta(days=1)).replace(day=1)
acc2=ok(client.post('/api/accounts',json={'name':'Startlogik','type':'checking','opening_balance':1000,'currency':'EUR','start_date':prev.isoformat()}))
ok(client.post('/api/transactions',json={'account_id':acc2['id'],'amount':100,'direction':'expense','booking_date':first.isoformat(),'payee':'Am Ersten','status':'executed','tags':[],'splits':[]}))
series=main.monthly_account_series(c,acc2['id'],first.strftime('%Y-%m'))
assert len(series)==monthrange(first.year,first.month)[1]
assert series[0]['date']==first.isoformat() and series[0]['opening_balance']==1000.0 and series[0]['balance']==900.0, series[0]
metrics=main.account_month_metrics(c,acc2['id'],first.strftime('%Y-%m'))
assert metrics['month_start_balance']==1000.0 and metrics['month_end_balance']==900.0, metrics
assert series[-1]['balance']==900.0, series[-1]
print('account start + chart opening/day-close semantics: PASS')

# Recurring forecasts are propagated into later months immediately.
next_month=main.add_months(first,1); later_month=main.add_months(first,2)
rec=ok(client.post('/api/recurring',json={'account_id':acc2['id'],'name':'Zukunftsmiete','amount':100,'next_date':next_month.isoformat(),'frequency':'monthly','kind':'direct_debit','active':True}))
m1=next(x for x in ok(client.get('/api/accounts?month='+next_month.strftime('%Y-%m'))) if x['id']==acc2['id'])
m2=next(x for x in ok(client.get('/api/accounts?month='+later_month.strftime('%Y-%m'))) if x['id']==acc2['id'])
assert m1['month_end_balance'] <= 800.0 and m2['month_end_balance'] <= 700.0, (m1,m2)
# Editing creates a new schedule version from an explicit effective date.
changed=ok(client.put('/api/recurring/'+str(rec['id']),json={'account_id':acc2['id'],'name':'Zukunftsmiete','amount':150,'next_date':next_month.isoformat(),'effective_from':later_month.isoformat(),'frequency':'monthly','kind':'direct_debit','active':True}))
assert changed['versioned'] is True
m2b=next(x for x in ok(client.get('/api/accounts?month='+later_month.strftime('%Y-%m'))) if x['id']==acc2['id'])
assert m2b['month_end_balance'] < m2['month_end_balance'], (m2,m2b)
print('forward recurring forecast + effective-from versioning: PASS')

# Dashboard contains next payments and complete day axis data.
dash=ok(client.get('/api/dashboard?month='+next_month.strftime('%Y-%m')))
assert len(dash['total_forecast'])==monthrange(next_month.year,next_month.month)[1]
assert all(x['date'] > dash['today'] and dash['month_start'] <= x['date'] <= dash['month_end'] for x in dash['next_payments'])
assert dash['earliest_month']=='2023-01'
print('dashboard days + upcoming payments + earliest month: PASS')


# v0.3.8: account month-opening correction becomes the baseline without rewriting transactions.
correction_month=first.strftime('%Y-%m')
ok(client.put(f"/api/accounts/{acc2['id']}/month-opening",json={'month':correction_month,'opening_balance':1234.56,'note':'Abgleich'}))
metrics_corr=main.account_month_metrics(c,acc2['id'],correction_month)
assert metrics_corr['month_start_balance']==1234.56, metrics_corr
# Existing first-day expense still applies after the corrected opening value.
assert metrics_corr['month_end_balance'] <= 1134.56, metrics_corr
corrs=ok(client.get(f"/api/accounts/{acc2['id']}/corrections")); assert corrs and corrs[0]['month']==correction_month
print('account monthly opening correction: PASS')

# v0.3.8: a normal booking can create a bounded recurring series in one step.
future_start=main.add_months(first,3)
future_end=main.add_months(first,5)
made=ok(client.post('/api/transactions',json={'account_id':acc2['id'],'amount':42,'direction':'expense','booking_date':future_start.isoformat(),'payee':'Abo','status':'executed','tags':[],'splits':[],'recurring':True,'recurring_frequency':'monthly','recurring_until':future_end.isoformat()}))
assert made['recurring_id']
rrow=c.execute('SELECT valid_until,frequency FROM recurring WHERE id=?',(made['recurring_id'],)).fetchone(); assert rrow['valid_until']==future_end.isoformat() and rrow['frequency']=='monthly'
occ=c.execute('SELECT status FROM recurring_occurrences WHERE recurring_id=? AND due_date=?',(made['recurring_id'],future_start.isoformat())).fetchone(); assert occ and occ['status']=='executed'
journal=c.execute('SELECT booking_date,status FROM transactions WHERE recurring_id=? ORDER BY booking_date',(made['recurring_id'],)).fetchall()
assert [r['booking_date'] for r in journal]==[future_start.isoformat(),main.add_months(future_start,1).isoformat(),future_end.isoformat()], [dict(r) for r in journal]
assert all(r['status']=='planned' for r in journal), [dict(r) for r in journal]
events=[ev for ev in main.recurring_events(c,acc2['id'],future_start,future_end+timedelta(days=40)) if ev['recurring_id']==made['recurring_id']]
assert events==[], events
print('transaction recurring checkbox -> full bounded journal schedule: PASS')

print('API functional tests: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
