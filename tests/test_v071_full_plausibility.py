import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
# /app/static is already available in the test runtime from the previous package tests.
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
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
assert main.date.today().isoformat()=='2026-09-11'
acc=ok(client.post('/api/accounts',json={'name':'C24 Test','type':'checking','opening_balance':5000,'currency':'EUR','start_date':'2026-09-01'}))
cats={}
for name,direction in [('Gehalt','income'),('Miete','expense'),('Versicherung','expense'),('Lebensmittel','expense'),('Sparen','savings')]:
    cats[name]=ok(client.post('/api/categories',json={'name':name,'direction':direction}))['id']
# Real September transactions: opening 5000; rent on 1st -> 4200; insurance 5th -> 4100; food 8th -> 4000.
for day,cat,amount,payee,fixed in [
 ('2026-09-01','Miete',800,'Miete',True),('2026-09-05','Versicherung',100,'Versicherung',True),('2026-09-08','Lebensmittel',100,'Lebensmittel',False)]:
    ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':amount,'booking_date':day,'category_id':cats[cat],'payee':payee,'status':'executed','tags':[],'splits':[],'fixed_cost':fixed}))
# Future income/savings in September.
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':2000,'booking_date':'2026-09-25','category_id':cats['Gehalt'],'payee':'Gehalt Sep','status':'executed','tags':[],'splits':[],'confidence':'likely'}))
ok(client.post('/api/transactions',json={'account_id':acc['id'],'amount':500,'booking_date':'2026-09-28','category_id':cats['Sparen'],'payee':'Sparen Sep','status':'executed','tags':[],'splits':[]}))
# Monthly recurring future series starts October 1/5/25/28.
for payload in [
 {'category_id':cats['Miete'],'name':'Miete','amount':800,'next_date':'2026-10-01','kind':'direct_debit','confidence':'fixed','fixed_cost':True},
 {'category_id':cats['Versicherung'],'name':'Versicherung','amount':100,'next_date':'2026-10-05','kind':'direct_debit','confidence':'fixed','fixed_cost':True},
 {'category_id':cats['Gehalt'],'name':'Gehalt','amount':2000,'next_date':'2026-10-25','kind':'income','confidence':'likely','fixed_cost':False},
 {'category_id':cats['Sparen'],'name':'Sparen','amount':500,'next_date':'2026-10-28','kind':'direct_debit','confidence':'fixed','fixed_cost':False},
]:
    ok(client.post('/api/recurring',json={'account_id':acc['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,**payload}))
# Core balance semantics.
assert main._month_opening_balance(c,acc['id'],date(2026,9,1))==500000
assert main.projected_account_balance(c,acc['id'],date(2026,9,1))==420000 # opening stays 5000, day-1 rent then applies
assert main.projected_account_balance(c,acc['id'],date(2026,9,11))==400000
assert main.projected_account_balance(c,acc['id'],date(2026,9,30))==550000 # +2000 income -500 saving
assert main._month_opening_balance(c,acc['id'],date(2026,10,1))==550000
assert main.projected_account_balance(c,acc['id'],date(2026,10,1))==470000
assert main.projected_account_balance(c,acc['id'],date(2026,10,5))==460000
assert main.projected_account_balance(c,acc['id'],date(2026,10,31))==610000 # +2000 -800 -100 -500
assert main._month_opening_balance(c,acc['id'],date(2026,11,1))==610000
assert main.projected_account_balance(c,acc['id'],date(2026,11,30))==670000

# Dashboard consistency for selected months.
sep=ok(client.get('/api/dashboard?month=2026-09'))
assert sep['accounts'][0]['month_start_balance']==5000.0,sep['accounts'][0]
assert sep['accounts'][0]['balance']==4000.0,sep['accounts'][0]  # selected-month cutoff = Sep 11
assert sep['accounts'][0]['month_end_balance']==5500.0,sep['accounts'][0]
assert len(sep['total_forecast'])==30, len(sep['total_forecast'])
assert sep['total_forecast'][0]['date']=='2026-09-01' and sep['total_forecast'][-1]['date']=='2026-09-30'
octo=ok(client.get('/api/dashboard?month=2026-10'))
assert octo['accounts'][0]['month_start_balance']==5500.0,octo['accounts'][0]
assert octo['accounts'][0]['balance']==4600.0,octo['accounts'][0] # synthetic Oct 11 cutoff
assert octo['accounts'][0]['month_end_balance']==6100.0,octo['accounts'][0]
assert len(octo['total_forecast'])==31 and octo['total_forecast'][0]['date']=='2026-10-01' and octo['total_forecast'][-1]['date']=='2026-10-31'
np={(x['date'],x['name'],x['source']) for x in octo['next_payments']}
assert ('2026-10-01','Miete','recurring') in np and ('2026-10-25','Gehalt','recurring') in np,np
# Category reports: September real/manual bookings and savings semantics.
rep=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert rep['actual_through']=='2026-09-11',rep
assert rep['income']==0.0 and rep['expense']==1000.0 and rep['savings']==0.0,rep
assert rep['net']==-1000.0 and rep['total_saved']==0.0 and rep['savings_rate_pct']==0.0,rep

# Planning page plausibility.
p=ok(client.get('/api/planning/overview?month=2026-10'))
assert p['plan_actual']['planned']=={'income':2000.0,'expense':900.0,'savings':500.0},p['plan_actual']
assert p['fixed_costs']==900.0 and p['fixed_cost_ratio_pct']==45.0,p
assert p['free_money']==600.0,p
assert len(p['forecast']['3'])==3 and len(p['forecast']['6'])==6 and len(p['forecast']['12'])==12
# Expected forecast from today includes future Sep + monthly Oct onward.
assert p['forecast']['3'][0]['month']=='2026-09'
assert p['forecast']['3'][0]['end_balance']==5500.0,p['forecast']['3']
assert p['forecast']['3'][1]['end_balance']==6100.0,p['forecast']['3']
assert p['forecast']['3'][2]['end_balance']==6700.0,p['forecast']['3']
# Conservative excludes likely future salary, so must be below expected; optimistic includes likely salary.
assert p['forecast']['conservative'][-1]['end_balance'] < p['forecast']['12'][-1]['end_balance']
assert p['forecast']['optimistic'][-1]['end_balance'] >= p['forecast']['12'][-1]['end_balance']
# Next payment events in Oct exist and are correctly dated/signed.
ev=main.recurring_events(c,acc['id'],date(2026,10,1),date(2026,10,31))
got={(e['date'].isoformat(),e['name'],e['amount']) for e in ev}
assert ('2026-10-01','Miete',-80000) in got and ('2026-10-25','Gehalt',200000) in got and ('2026-10-28','Sparen',-50000) in got,got
print('v0.7.1 full household plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
