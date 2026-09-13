import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
assert main.APP_VERSION.startswith(('0.8.','0.9.','0.10.','0.11.','0.21.'))
# Decimal: 0.10 and 0.20 must become exact cents, no float drift.
assert main.cents(main.Decimal('0.10'))==10
assert main.cents(main.Decimal('0.20'))==20
assert main.cents(main.Decimal('0.10')+main.Decimal('0.20'))==30
acc=ok(client.post('/api/accounts',json={'name':'C24','type':'checking','opening_balance':'1000.00','currency':'EUR','start_date':'2026-09-01'}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))['id']
exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))['id']
sav=ok(client.post('/api/categories',json={'name':'ETF','direction':'savings'}))['id']
# Planned recurring: 2000 income, 800 expense, 300 savings monthly.
for payload in [
 {'category_id':inc,'name':'Gehalt','amount':'2000.00','next_date':'2026-09-25','kind':'income','fixed_cost':False},
 {'category_id':exp,'name':'Miete','amount':'800.00','next_date':'2026-09-01','kind':'direct_debit','fixed_cost':True},
 {'category_id':sav,'name':'ETF','amount':'300.00','next_date':'2026-09-05','kind':'direct_debit','fixed_cost':False},
]:
 ok(client.post('/api/recurring',json={'account_id':acc['id'],'frequency':'monthly','active':True,'valid_until':None,'max_amount':None,'confidence':'fixed',**payload}))
# Create an actual Sep rent of 850 linked to the recurring series: plan must remain 800, Ist 850.
rent=c.execute("SELECT id FROM recurring WHERE name='Miete' LIMIT 1").fetchone()[0]
ts=main.iso(main.utcnow())
c.execute("INSERT INTO transactions(account_id,amount,direction,booking_date,payee,category_id,status,external_id,recurring_id,confidence,fixed_cost,created_at,updated_at) VALUES(?,?,?,?,?,?, 'executed',?,?,?,?,?,?)",
          (acc['id'],-85000,'expense','2026-09-01','Miete Ist',exp,'test-rent',rent,'fixed',1,ts,ts))
c.execute("INSERT OR REPLACE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,last_insert_rowid(),'executed',?)",(rent,'2026-09-01',ts)); c.commit()
var=ok(client.get('/api/planning/variance?month=2026-09'))
rentrow=next(x for x in var['rows'] if x['category_id']==exp)
assert rentrow['planned']==800.0 and rentrow['actual']==850.0 and rentrow['difference']==50.0,rentrow
# Runway uses existing capital / average fixed cost.
runway=ok(client.get('/api/planning/runway'))
assert runway['monthly_fixed_costs']>=800.0,runway
# What-if must not mutate real data and must move scenario exactly by monthly delta.
before=main.projected_account_balance(c,acc['id'],date(2026,12,31))
wi=ok(client.post('/api/planning/what-if',json={'horizon_months':3,'monthly_income_change':'-200.00','monthly_expense_change':'100.00','monthly_savings_change':'0.00','one_time_change':'-500.00','one_time_date':'2026-10-15'}))
assert len(wi['series'])==3 and wi['series'][0]['difference']==-300.0 and wi['series'][1]['difference']==-1100.0,wi
assert main.projected_account_balance(c,acc['id'],date(2026,12,31))==before
# Contract metadata only.
con=ok(client.post('/api/contracts',json={'title':'Strom','provider':'Testwerke','start_date':'2026-01-01','end_date':'2027-12-31','cancellation_deadline':'2027-09-30','notice_days':90,'notes':'nur Metadaten','active':True}))
assert any(x['id']==con['id'] for x in ok(client.get('/api/contracts')))
# Bank reconciliation + optional correction + local learning.
r=ok(client.post(f"/api/accounts/{acc['id']}/reconcile",json={'actual_balance':'1200.00','checked_at':'2026-09-11','note':'Bankstand'}))
assert 'suggestions' in r
corr=ok(client.post(f"/api/accounts/{acc['id']}/reconcile/correction",json={'actual_balance':'1200.00','checked_at':'2026-09-11','note':'Bankstand','create_correction':True,'label':'Bankabgleich'}))
assert corr['created'] is True
learned=c.execute('SELECT accepted_count FROM reconciliation_learning WHERE account_id=?',(acc['id'],)).fetchone(); assert learned and learned[0]>=1
# Attachment magic byte validation and storage limit.
fake=client.post('/api/transactions/%s/attachments'%corr['transaction_id'],files={'file':('fake.pdf',b'not a pdf','application/pdf')})
assert fake.status_code==400,fake.text
valid=ok(client.post('/api/transactions/%s/attachments'%corr['transaction_id'],files={'file':('receipt.pdf',b'%PDF-1.4\n%%EOF','application/pdf')}))
assert valid['size']>0
# Finance check includes audit chain and core checks.
check=ok(client.post('/api/finance-check'))
codes={x['code']:x for x in check['checks']}
assert codes['audit_chain']['level']=='ok',codes['audit_chain']
assert codes['split_sums']['level']=='ok'
# Variability returns 12 months.
vari=ok(client.get('/api/analysis/variability?months=12')); assert len(vari['series']['income'])==12
print('v0.8.0 hardening/features plausibility: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
