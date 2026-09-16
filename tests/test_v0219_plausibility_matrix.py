import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date as real_date

shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
if static.is_symlink() and static.resolve()!=(root/'static').resolve(): static.unlink()
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,15)
main.date=FixedDate; main.db._conn=c; main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request:None; main.require_system_admin=lambda request:None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()

# Calendar recurrence plausibility: anchored schedules return to the original day.
def occ(start,freq,end,n=1):
    return [d.isoformat() for d in main.occurrences(real_date.fromisoformat(start),freq,real_date.fromisoformat(start),real_date.fromisoformat(end),n)]
assert occ('2027-01-31','monthly','2027-05-31') == ['2027-01-31','2027-02-28','2027-03-31','2027-04-30','2027-05-31']
assert occ('2028-01-31','monthly','2028-03-31') == ['2028-01-31','2028-02-29','2028-03-31']
assert occ('2028-02-29','yearly','2032-02-29') == ['2028-02-29','2029-02-28','2030-02-28','2031-02-28','2032-02-29']
assert occ('2026-10-31','monthly','2027-10-31',3) == ['2026-10-31','2027-01-31','2027-04-30','2027-07-31','2027-10-31']
assert occ('2026-09-20','daily','2026-10-20',10) == ['2026-09-20','2026-09-30','2026-10-10','2026-10-20']
assert occ('2026-09-21','weekly','2026-11-02',2) == ['2026-09-21','2026-10-05','2026-10-19','2026-11-02']

src=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'2000','currency':'EUR','start_date':'2026-08-01'}))['id']
dst=ok(client.post('/api/accounts',json={'name':'Tagesgeld','type':'savings','opening_balance':'500','currency':'EUR','start_date':'2026-08-01'}))['id']
expense_cat=ok(client.post('/api/categories',json={'name':'Fixkosten Plausi','direction':'expense'}))['id']
income_cat=ok(client.post('/api/categories',json={'name':'Einkommen Plausi','direction':'income'}))['id']

# Historical month: documentary actuals only.
ok(client.post('/api/transactions',json={'account_id':src,'amount':'80','booking_date':'2026-08-10','category_id':expense_cat,'name':'August Ist','status':'executed','tags':[],'splits':[]}))
past=ok(client.get('/api/reports/categories?period=month&anchor=2026-08-01'))
assert past['mode']=='actual' and past['includes_planned'] is False,past
assert past['expense']==80.0,past

# Current month: executed + known future recurring entries through month end.
ok(client.post('/api/transactions',json={'account_id':src,'amount':'50','booking_date':'2026-09-10','category_id':expense_cat,'name':'Schon gebucht','status':'executed','tags':[],'splits':[]}))
exp=ok(client.post('/api/recurring',json={'account_id':src,'category_id':expense_cat,'name':'Miete Restmonat','amount':'100','next_date':'2026-09-20','frequency':'monthly','interval_count':1,'kind':'direct_debit','active':True,'valid_until':'2026-10-20','confidence':'fixed','fixed_cost':True}))
inc=ok(client.post('/api/recurring',json={'account_id':src,'category_id':income_cat,'name':'Gehalt Restmonat','amount':'1000','next_date':'2026-09-25','frequency':'monthly','interval_count':1,'kind':'income','active':True,'valid_until':'2026-10-25','confidence':'fixed','fixed_cost':False}))
current=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert current['mode']=='forecast' and current['includes_planned'] is True,current
assert current['expense']==150.0,current
assert current['income']==1000.0,current
assert current['net']==850.0,current

# Future month is also a forecast and includes materialized known recurrences.
october=ok(client.get('/api/reports/categories?period=month&anchor=2026-10-01'))
assert october['mode']=='forecast' and october['includes_planned'] is True,october
assert october['expense']==100.0 and october['income']==1000.0,october

# Year report remains actual-only and must not pull future planned rows into documentary totals.
year=ok(client.get('/api/reports/categories?period=year&anchor=2026-01-01'))
assert year['mode']=='actual' and year['includes_planned'] is False,year
assert year['expense']==130.0,year  # August 80 + September executed 50
assert year['income']==0.0,year

# Internal transfer is balance-moving but income/expense neutral.
tr=ok(client.post('/api/transfers',json={'from_account_id':src,'to_account_id':dst,'amount':'200','booking_date':'2026-09-15','name':'Rücklage','note':'intern','recurring':True,'recurring_frequency':'monthly','recurring_interval_count':3,'recurring_until':'2027-03-15'}))
rid=tr['recurring_transfer_id']; assert rid and tr['generated_transfers']==3,tr
rows=c.execute('SELECT id,booking_date,amount,active FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date',(rid,)).fetchall()
assert [r['booking_date'] for r in rows]==['2026-09-15','2026-12-15','2027-03-15'],[dict(r) for r in rows]
for r in rows:
    tx=c.execute('SELECT transfer_side,amount,status FROM transactions WHERE transfer_id=? ORDER BY transfer_side',(r['id'],)).fetchall()
    assert len(tx)==2,tx
    assert sum(int(x['amount']) for x in tx)==0,tx
    assert sorted(x['transfer_side'] for x in tx)==['in','out'],tx
report_after_transfer=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report_after_transfer['income']==1000.0 and report_after_transfer['expense']==150.0,report_after_transfer

# Account forecast must reflect the transfer on each side exactly once.
src_m=main.account_month_metrics(c,src,'2026-09'); dst_m=main.account_month_metrics(c,dst,'2026-09')
assert src_m['month_end_balance']==2570.0,src_m  # 1920 Sep opening after Aug -80; then -50 -100 +1000 -200
assert dst_m['month_end_balance']==700.0,dst_m

# Edit series: keep executed history, rebuild future instances on the new rhythm/amount.
ok(client.put(f'/api/recurring-transfers/{rid}',json={'from_account_id':src,'to_account_id':dst,'amount':'250','booking_date':'2026-10-01','name':'Rücklage neu','note':None,'recurring':True,'recurring_frequency':'monthly','recurring_interval_count':2,'recurring_until':'2027-02-01'}))
rows=c.execute('SELECT booking_date,amount FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date',(rid,)).fetchall()
assert [(r['booking_date'],r['amount']) for r in rows]==[('2026-09-15',20000),('2026-10-01',25000),('2026-12-01',25000),('2027-02-01',25000)],[dict(r) for r in rows]

# Delete series: preserve executed transfer history, remove/cancel future schedule.
ok(client.delete(f'/api/recurring-transfers/{rid}'))
remaining=c.execute('SELECT booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date',(rid,)).fetchall()
assert [r['booking_date'] for r in remaining]==['2026-09-15'],[dict(r) for r in remaining]

# Validation guards.
same=client.post('/api/transfers',json={'from_account_id':src,'to_account_id':src,'amount':'10','booking_date':'2026-09-15','name':'Ungültig'})
assert same.status_code in (400,422),same.text
zero=client.post('/api/transfers',json={'from_account_id':src,'to_account_id':dst,'amount':'0','booking_date':'2026-09-15','name':'Null'})
assert zero.status_code in (400,422),zero.text
missing_freq=client.post('/api/transfers',json={'from_account_id':src,'to_account_id':dst,'amount':'10','booking_date':'2026-09-15','name':'Ohne Intervall','recurring':True})
assert missing_freq.status_code==400,missing_freq.text
bad_until=client.post('/api/transfers',json={'from_account_id':src,'to_account_id':dst,'amount':'10','booking_date':'2026-10-01','name':'Ende vorher','recurring':True,'recurring_frequency':'monthly','recurring_until':'2026-09-30'})
assert bad_until.status_code==400,bad_until.text

# End date is inclusive and one-off recurring transfer remains exactly one instance.
one=ok(client.post('/api/transfers',json={'from_account_id':src,'to_account_id':dst,'amount':'12','booking_date':'2026-11-30','name':'Ein Termin','recurring':True,'recurring_frequency':'monthly','recurring_interval_count':1,'recurring_until':'2026-11-30'}))
count=c.execute('SELECT COUNT(*) FROM transfers WHERE recurring_transfer_id=?',(one['recurring_transfer_id'],)).fetchone()[0]
assert count==1,count

schema=c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]
assert schema=='27',schema
print('v0.21.9 plausibility matrix: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
