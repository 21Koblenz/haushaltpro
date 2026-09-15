import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
from decimal import Decimal

root=Path(__file__).resolve().parents[1]
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
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
# sqlite isn't SQLCipher: make finance-check's crypto integrity probe deterministic.
main.db.integrity_check=lambda: []
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()
def eq(got,exp,msg):
    assert got==exp,f'{msg}: got={got!r} expected={exp!r}'

assert main.date.today().isoformat()=='2026-09-11',main.date.today()
# Exact money rounding.
eq(main.cents(Decimal('0.10')+Decimal('0.20')),30,'decimal 0.10+0.20')
eq(main.cents(Decimal('1.005')),101,'ROUND_HALF_UP 1.005')
eq(main.cents(Decimal('-1.005')),-101,'ROUND_HALF_UP -1.005')

acc=ok(client.post('/api/accounts',json={'name':'Hauptkonto','type':'checking','opening_balance':'10000.00','currency':'EUR','start_date':'2026-01-01'}))['id']
cat={}
for name,typ in [('Gehalt','income'),('Miete','expense'),('Versicherung','expense'),('Lebensmittel','expense'),('Sparen','savings'),('Nebenkosten','expense'),('Auto','expense')]:
    cat[name]=ok(client.post('/api/categories',json={'name':name,'direction':typ}))['id']

def rec(name,catname,amount,next_date,kind='direct_debit',fixed=False,confidence='fixed'):
    return ok(client.post('/api/recurring',json={'account_id':acc,'category_id':cat[catname],'name':name,'amount':str(amount),'next_date':next_date,'frequency':'monthly','kind':kind,'max_amount':None,'active':True,'valid_until':None,'confidence':confidence,'fixed_cost':fixed}))['id']

salary=rec('Gehalt','Gehalt','3000.00','2026-01-25','income',False)
rent=rec('Miete','Miete','1200.00','2026-01-01','direct_debit',True)
insurance=rec('Versicherung','Versicherung','100.00','2026-01-05','direct_debit',True)
saving=rec('Sparplan','Sparen','500.00','2026-01-28','direct_debit',True)
# Important edge: due TODAY but not materialized yet.
utility=rec('Nebenkosten','Nebenkosten','75.00','2026-09-11','direct_debit',True)

# Materialize Jan-Aug recurring activity at plan amount. September rent differs from plan.
def exec_occ(rec_id,due,amount,category_id,direction,fixed,name):
    ts=main.iso(main.utcnow())
    cur=c.execute('''INSERT INTO transactions(account_id,amount,direction,booking_date,value_date,name,payee,note,category_id,status,external_id,recurring_id,confidence,fixed_cost,created_at,updated_at)
                     VALUES(?,?,?,?,?,?,?,?,?,'executed',?,?,?,?,?,?)''',
                  (acc,amount,direction,due,due,name,name,'Test-Ist',category_id,f'test-{rec_id}-{due}',rec_id,'fixed',int(fixed),ts,ts))
    c.execute("INSERT OR REPLACE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,'executed',?)",(rec_id,due,cur.lastrowid,ts))

for m in range(1,9):
    exec_occ(rent,f'2026-{m:02d}-01',-120000,cat['Miete'],'expense',True,'Miete')
    exec_occ(insurance,f'2026-{m:02d}-05',-10000,cat['Versicherung'],'expense',True,'Versicherung')
    exec_occ(salary,f'2026-{m:02d}-25',300000,cat['Gehalt'],'income',False,'Gehalt')
    exec_occ(saving,f'2026-{m:02d}-28',-50000,cat['Sparen'],'expense',False,'Sparplan')
# September actual: rent differs +50, insurance exact.
exec_occ(rent,'2026-09-01',-125000,cat['Miete'],'expense',True,'Miete')
exec_occ(insurance,'2026-09-05',-10000,cat['Versicherung'],'expense',True,'Versicherung')
c.commit()

# Manual actual groceries: 501.00 exactly.
for d,amt,name in [('2026-09-03','420.75','Wocheneinkauf'),('2026-09-10','80.25','Nachkauf')]:
    ok(client.post('/api/transactions',json={'account_id':acc,'amount':amt,'booking_date':d,'name':name,'payee':'Supermarkt','category_id':cat['Lebensmittel'],'status':'executed','tags':['haushalt'],'splits':[]}))
# Known future one-time expense in September.
ok(client.post('/api/transactions',json={'account_id':acc,'amount':'600.00','booking_date':'2026-09-20','name':'Autoreparatur','payee':'Werkstatt','category_id':cat['Auto'],'status':'executed','tags':['auto'],'splits':[]}))

# Independent household arithmetic:
# Jan-Aug: each month +3000 -1200 -100 -500 = +1200. 10000 + 8*1200 = 19600.
eq(main._month_opening_balance(c,acc,date(2026,9,1)),1960000,'Sep opening from Aug close')
eq(main.projected_account_balance(c,acc,date(2026,8,31)),1960000,'Aug projected close')
eq(main.account_balance(c,acc,date(2026,8,31)),1960000,'Aug actual close')
# Sep 11 ACTUAL excludes unmaterialized 75 due today: 19600-1250-100-501 =17749.
eq(main.account_balance(c,acc,date(2026,9,11)),1774900,'Sep11 actual balance')
# Sep 11 PROJECTED includes due-today utility: 17674.
eq(main.projected_account_balance(c,acc,date(2026,9,11)),1767400,'Sep11 projected balance')
# Sep end projected: +3000 salary -500 saving -600 car, all after Sep11 => 19574.
eq(main.projected_account_balance(c,acc,date(2026,9,30)),1957400,'Sep projected close')

metrics=main.account_month_metrics(c,acc,'2026-09')
eq(metrics['month_start_balance'],19600.0,'metrics start')
eq(metrics['balance'],17674.0,'metrics same-day projected')
eq(metrics['month_end_balance'],19574.0,'metrics end')
series=main.monthly_account_series(c,acc,'2026-09')
eq(len(series),30,'Sep daily points')
eq(series[0]['opening_balance'],19600.0,'chart opening')
eq(series[-1]['balance'],19574.0,'chart end')

# September plan should preserve original recurring rent 1200, not actual 1250.
p=ok(client.get('/api/planning/overview?month=2026-09'))
eq(p['plan_actual']['planned']['income'],3000.0,'Sep planned income')
eq(p['plan_actual']['planned']['expense'],2476.0,'Sep planned expense') # 1200+100+75+501+600
eq(p['plan_actual']['planned']['savings'],500.0,'Sep planned savings')
eq(p['plan_actual']['actual']['income'],0.0,'Sep actual income through Sep11')
eq(p['plan_actual']['actual']['expense'],1851.0,'Sep actual expense through Sep11') #1250+100+501
eq(p['plan_actual']['actual']['savings'],0.0,'Sep actual savings through Sep11')
eq(p['cashflow_warning']['consumption_cashflow'],524.0,'Sep consumption cashflow')
eq(p['cashflow_warning']['total_cashflow'],24.0,'Sep total cashflow')
eq(p['free_money'],24.0,'Sep free money')
eq(p['fixed_costs'],1375.0,'Sep planned fixed costs')
eq(p['fixed_cost_ratio_pct'],45.8,'Sep fixed cost ratio')

# Dashboard forecast/hybrid values: due-today item is part of same-day projected view, future items remain pending.
dash=ok(client.get('/api/dashboard?month=2026-09'))
eq(dash['total_balance'],17674.0,'dashboard cutoff balance')
eq(dash['month_end_balance'],19574.0,'dashboard month end')
eq(dash['pending_outflows'],1100.0,'dashboard pending outflows') # car 600 + saving 500
eq(dash['pending_inflows'],3000.0,'dashboard pending inflows')
np={(x['date'],x['name'],x['source']) for x in dash['next_payments']}
assert ('2026-09-20','Werkstatt','transaction') in np,np
assert ('2026-09-25','Gehalt','transaction') in np,np
assert ('2026-09-28','Sparplan','transaction') in np,np

# Current-month report combines actuals through today with known/planned remainder through month end.
rep=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
eq(rep['actual_through'],'2026-09-11','report actual cutoff')
eq(rep['mode'],'forecast','Sep report mode')
eq(rep['includes_planned'],True,'Sep report includes planned')
eq(rep['income'],3000.0,'Sep report forecast income')
eq(rep['expense'],2526.0,'Sep report forecast expense')
eq(rep['savings'],500.0,'Sep report forecast savings')
# Current-year report also excludes future manual/planned entries.
yrep=ok(client.get('/api/reports/categories?period=year&anchor=2026-01-01'))
eq(yrep['income'],24000.0,'YTD report income')
eq(yrep['expense'],12251.0,'YTD report expense')
eq(yrep['savings'],4000.0,'YTD report savings')
eq(yrep['net'],7749.0,'YTD report net')
eq(yrep['total_saved'],11749.0,'YTD report total saved')
eq(yrep['savings_rate_pct'],49.0,'YTD savings rate')

# Variability is historical/actual: current month excludes Sep20 future car.
vari=ok(client.get('/api/analysis/variability?months=3'))
eq([x['amount'] for x in vari['series']['income']],[3000.0,3000.0,0.0],'variability income')
eq([x['amount'] for x in vari['series']['expense']],[1300.0,1300.0,1851.0],'variability expense')
eq([x['amount'] for x in vari['series']['savings']],[500.0,500.0,0.0],'variability savings')

# Emergency runway uses planned fixed costs consistently (1375/month Sep-Nov).
runway=ok(client.get('/api/planning/runway'))
eq(runway['liquid_balance'],17674.0,'runway liquid projected today')
eq(runway['monthly_fixed_costs'],1375.0,'runway monthly fixed')
eq(runway['runway_months'],12.9,'runway months')

# What-if is pure simulation and never changes the real forecast/database.
before_dec=main.projected_account_balance(c,acc,date(2026,12,31))
wi=ok(client.post('/api/planning/what-if',json={'horizon_months':3,'monthly_income_change':'-200.00','monthly_expense_change':'100.00','monthly_savings_change':'50.00','one_time_change':'-1000.00','one_time_date':'2026-10-15'}))
eq(wi['monthly_delta'],-350.0,'what-if monthly delta')
eq([x['difference'] for x in wi['series']],[-350.0,-1700.0,-2050.0],'what-if cumulative differences')
eq(wi['series'][0]['scenario_end_balance'],19224.0,'what-if Sep end')
eq(main.projected_account_balance(c,acc,date(2026,12,31)),before_dec,'what-if does not mutate DB')

var=ok(client.get('/api/planning/variance?month=2026-09'))
rentrow=next(x for x in var['rows'] if x['category_id']==cat['Miete'])
eq(rentrow['planned'],1200.0,'rent plan original')
eq(rentrow['actual'],1250.0,'rent actual')
eq(rentrow['difference'],50.0,'rent variance')

# Annual plan independent expected:
# salary 12*3000=36000; savings 12*500=6000.
# expense rent 14400 + insurance 1200 + utility Sep-Dec 300 + groceries 501 + car 600 = 17001.
y=ok(client.get('/api/planning/year?year=2026'))
eq(y['totals']['planned_income'],36000.0,'annual planned income')
eq(y['totals']['planned_savings'],6000.0,'annual planned savings')
eq(y['totals']['planned_expense'],17001.0,'annual planned expense')
# Actual through Sep11: income Jan-Aug 24000; savings Jan-Aug 4000;
# expenses Jan-Aug rent+ins 10400 + Sep rent1250+ins100+groceries501 =12251.
eq(y['totals']['actual_income'],24000.0,'annual actual income')
eq(y['totals']['actual_savings'],4000.0,'annual actual savings')
eq(y['totals']['actual_expense'],12251.0,'annual actual expense')

# Long forecast must start from projected current position INCLUDING a due-today unmaterialized recurring item.
# Sep end therefore must equal 19574.
eq(p['forecast']['3'][0]['month'],'2026-09','forecast starts current month')
eq(p['forecast']['3'][0]['end_balance'],19574.0,'3m forecast Sep close includes due-today item')

# Bank reconciliation is ACTUAL-data reconciliation, not forecast reconciliation.
# Expected bank ledger balance on Sep11 is 17749, because utility is only planned/unmaterialized.
rec_check=ok(client.get(f'/api/accounts/{acc}/reconcile/suggestions?actual_balance=17749.00&checked_at=2026-09-11'))
eq(rec_check['expected'],17749.0,'bank reconciliation expected actual ledger')
eq(rec_check['difference'],0.0,'bank reconciliation zero difference')

# Closed historical month with no snapshot made before close must NOT invent a forecast today.
past=ok(client.get('/api/planning/overview?month=2026-08'))
assert past['forecast_deviation'] is None,f"historical forecast was invented after close: {past['forecast_deviation']}"
# But a genuine snapshot captured before month end must produce a real deviation.
c.execute("INSERT INTO forecast_snapshots(month,captured_on,projected_end_balance) VALUES(?,?,?)",('2026-07','2026-07-10',1800000)); c.commit()
jul=ok(client.get('/api/planning/overview?month=2026-07'))
eq(jul['forecast_deviation']['forecast'],18000.0,'July historical forecast')
eq(jul['forecast_deviation']['actual'],18400.0,'July actual close')
eq(jul['forecast_deviation']['difference'],400.0,'July forecast deviation')
eq(jul['forecast_deviation']['captured_on'],'2026-07-10','July snapshot date')

# 31st and leap anchors.
eq([d.isoformat() for d in main.occurrences(date(2026,1,31),'monthly',date(2026,1,1),date(2026,4,30))],['2026-01-31','2026-02-28','2026-03-31','2026-04-30'],'31st anchor')
eq([d.isoformat() for d in main.occurrences(date(2024,2,29),'yearly',date(2024,1,1),date(2028,12,31))],['2024-02-29','2025-02-28','2026-02-28','2027-02-28','2028-02-29'],'leap yearly anchor')

# Monthly correction is a hard future baseline, day-1 movements happen afterwards.
ok(client.put(f'/api/accounts/{acc}/month-opening',json={'month':'2026-10','opening_balance':'5000.00','note':'Bankabgleich'}))
eq(main._month_opening_balance(c,acc,date(2026,10,1)),500000,'Oct overridden opening')
# Oct1 rent -1200, so day1 projected 3800.
eq(main.projected_account_balance(c,acc,date(2026,10,1)),380000,'Oct1 after opening override and rent')

# Pagination/search exactness.
all_rows=ok(client.get('/api/transactions/paged?period=all&page=1&page_size=0'))
assert all_rows['total']>=37 and len(all_rows['items'])==all_rows['total']
search=ok(client.get('/api/transactions/paged?period=all&q=Autoreparatur&page=1&page_size=10'))
eq(search['total'],1,'name search')

# Bank correction: actual ledger should be corrected by exactly the confirmed difference and learning updated.
rec2=ok(client.post(f'/api/accounts/{acc}/reconcile',json={'actual_balance':'17699.00','checked_at':'2026-09-11','note':'Testauszug'}))
eq(rec2['expected'],17749.0,'reconcile post expected')
eq(rec2['difference'],-50.0,'reconcile post difference')
corr=ok(client.post(f'/api/accounts/{acc}/reconcile/correction',json={'actual_balance':'17699.00','checked_at':'2026-09-11','note':'Testauszug','create_correction':True,'label':'Bankabgleich Test'}))
eq(corr['difference'],-50.0,'correction amount')
eq(main.account_balance(c,acc,date(2026,9,11)),1769900,'actual ledger after correction')
learn=c.execute("SELECT accepted_count FROM reconciliation_learning WHERE account_id=? AND amount_cents=5000",(acc,)).fetchone(); assert learn and learn[0]>=1

# Attachment validation + limits. Reuse correction transaction without polluting core arithmetic checks above.
txid=corr['transaction_id']
fake=client.post(f'/api/transactions/{txid}/attachments',files={'file':('fake.pdf',b'not a pdf','application/pdf')})
eq(fake.status_code,400,'fake PDF rejected')
old_total,old_per=main.MAX_ATTACHMENT_TOTAL_BYTES,main.MAX_ATTACHMENTS_PER_TX
main.MAX_ATTACHMENT_TOTAL_BYTES=30; main.MAX_ATTACHMENTS_PER_TX=2
pdf1=b'%PDF-1.4\n1234567890\n%%EOF'
a1=ok(client.post(f'/api/transactions/{txid}/attachments',files={'file':('a.pdf',pdf1,'application/pdf')}))
# second upload would exceed 30 byte total -> 507, existing first attachment remains.
over=client.post(f'/api/transactions/{txid}/attachments',files={'file':('b.pdf',pdf1,'application/pdf')})
eq(over.status_code,507,'attachment total limit')
eq(len(ok(client.get(f'/api/transactions/{txid}/attachments'))),1,'existing attachment preserved after limit')
main.MAX_ATTACHMENT_TOTAL_BYTES=old_total; main.MAX_ATTACHMENTS_PER_TX=old_per

# CSV import: exact decimal parsing + deterministic duplicate detection; uploaded CSV itself is not attached/stored.
imp=ok(client.post('/api/accounts',json={'name':'Importkonto','type':'checking','iban':'DE02120300000000202051','opening_balance':'0.00','currency':'EUR','start_date':'2026-09-01'}))['id']
csvdata='Datum;Betrag;Empfänger;Verwendungszweck;Transaktions-ID\n11.09.2026;1234,56;Arbeitgeber;Bonus;abc1\n11.09.2026;-12,34;Bäcker;Frühstück;abc2\n'.encode()
ri=ok(client.post('/api/import/csv',data={'account_id':str(imp)},files={'file':('bank.csv',csvdata,'text/csv')}))
eq(ri,{'imported':2,'duplicates':0,'skipped':0},'CSV first import')
ri2=ok(client.post('/api/import/csv',data={'account_id':str(imp)},files={'file':('bank.csv',csvdata,'text/csv')}))
eq(ri2,{'imported':0,'duplicates':2,'skipped':0},'CSV duplicate import')
eq(main.account_balance(c,imp,date(2026,9,11)),122222,'CSV exact balance')
eq(c.execute('SELECT COUNT(*) FROM attachments').fetchone()[0],1,'CSV file is not stored as attachment')

# Finance check must report no mathematical/integrity errors. A reconciliation warning is allowed only if a deliberately open difference remains.
check=ok(client.post('/api/finance-check'))
assert check['ok'],check
codes={x['code']:x for x in check['checks']}
eq(codes['audit_chain']['level'],'ok','finance-check audit chain')
eq(codes['split_sums']['level'],'ok','finance-check split sums')
eq(codes['month_continuity']['level'],'ok','finance-check month continuity')

# Audit chain must remain valid after all operations.
au=ok(client.get('/api/audit/timeline?limit=200&offset=0'))
assert au['chain_ok'],au['chain_errors']

print('DEEP V0.8.6 PLAUSIBILITY: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
