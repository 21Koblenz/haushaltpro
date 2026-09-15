import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date as real_date

shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if static.is_symlink() and static.resolve()!=(root/'static').resolve(): static.unlink()
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db');Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
db._conn=c;db.DB_PATH=Path(tmp);db.init_schema(c);db.migrate_schema(c)
from app import main
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,15)
main.date=FixedDate;main.db._conn=c;main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request:None;main.require_system_admin=lambda request:None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()

src=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}))['id']
dst=ok(client.post('/api/accounts',json={'name':'Tagesgeld','type':'savings','opening_balance':'0','currency':'EUR','start_date':'2026-09-01'}))['id']
cat=ok(client.post('/api/categories',json={'name':'Versicherung','direction':'expense'}))['id']

ok(client.post('/api/transactions',json={'account_id':src,'amount':'50','booking_date':'2026-09-10','category_id':cat,'name':'Gebucht','status':'executed','tags':[],'splits':[]}))
ok(client.post('/api/recurring',json={'account_id':src,'category_id':cat,'name':'Versicherung','amount':'100','next_date':'2026-09-20','frequency':'monthly','interval_count':1,'kind':'direct_debit','active':True,'valid_until':'2026-09-20','confidence':'fixed','fixed_cost':True}))
report=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report['mode']=='forecast',report
assert report['expense']==150.0,report
assert report['includes_planned'] is True,report

tr=ok(client.post('/api/transfers',json={
    'from_account_id':src,'to_account_id':dst,'amount':'200','booking_date':'2026-09-15',
    'name':'Rücklage','note':'intern','recurring':True,'recurring_frequency':'monthly',
    'recurring_interval_count':3,'recurring_until':'2027-03-15'
}))
rid=tr['recurring_transfer_id'];assert rid
trs=c.execute("SELECT id,booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()
assert [r['booking_date'] for r in trs]==['2026-09-15','2026-12-15','2027-03-15'],[dict(r) for r in trs]
statuses=[]
for r in trs:
    statuses.append(sorted(x['status'] for x in c.execute("SELECT status FROM transactions WHERE transfer_id=?",(r['id'],)).fetchall()))
assert statuses==[['executed','executed'],['planned','planned'],['planned','planned']],statuses

series=ok(client.get('/api/recurring-transfers'))
rt=next(x for x in series if x['id']==rid)
assert rt['next_date']=='2026-12-15',rt
assert rt['frequency']=='monthly' and rt['interval_count']==3,rt

report2=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report2['expense']==150.0 and report2['income']==0.0,report2
sept_src=main.account_month_metrics(c,src,'2026-09')
sept_dst=main.account_month_metrics(c,dst,'2026-09')
assert sept_src['month_end_balance']==650.0,sept_src
assert sept_dst['month_end_balance']==200.0,sept_dst

ok(client.put(f'/api/recurring-transfers/{rid}',json={
    'from_account_id':src,'to_account_id':dst,'amount':'250','booking_date':'2026-10-01',
    'name':'Rücklage neu','note':None,'recurring':True,'recurring_frequency':'monthly',
    'recurring_interval_count':2,'recurring_until':'2027-02-01'
}))
dates=[r['booking_date'] for r in c.execute("SELECT booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()]
assert dates==['2026-09-15','2026-10-01','2026-12-01','2027-02-01'],dates
first=c.execute("SELECT amount FROM transfers WHERE recurring_transfer_id=? AND booking_date='2026-09-15'",(rid,)).fetchone()
assert first['amount']==20000,first

ok(client.delete(f'/api/recurring-transfers/{rid}'))
remaining=c.execute("SELECT booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()
assert [r['booking_date'] for r in remaining]==['2026-09-15'],[dict(r) for r in remaining]

past=ok(client.get('/api/reports/categories?period=month&anchor=2026-08-01'))
assert past['mode']=='actual' and past['includes_planned'] is False,past

print('recurring transfers + current-month report forecast: PASS')
c.close();Path(tmp).unlink(missing_ok=True)
