import sqlite3
import sys
import tempfile
import types
from datetime import date as real_date
from pathlib import Path

shim = types.ModuleType('sqlcipher3')
shim.dbapi2 = sqlite3
sys.modules['sqlcipher3'] = shim
root = Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True)
static_mount = Path('/app/static')
if static_mount.is_symlink() and static_mount.resolve() != (root / 'static').resolve():
    static_mount.unlink()
if not static_mount.exists():
    static_mount.symlink_to(root / 'static', target_is_directory=True)
sys.path.insert(0, str(root))

from app import db
fd, tmp = tempfile.mkstemp(suffix='.db')
Path(tmp).unlink(missing_ok=True)
c = sqlite3.connect(tmp, check_same_thread=False)
c.row_factory = sqlite3.Row
c.execute('PRAGMA foreign_keys=ON')
db._conn = c
db.DB_PATH = Path(tmp)
db.init_schema(c)

from app import main
main.db._conn = c
main.session = lambda request, write=False: ('test', 1, 'csrf', 0)

class FixedDate(real_date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 15)
main.date = FixedDate

from fastapi.testclient import TestClient
client = TestClient(main.app)


def ok(r):
    assert r.status_code==200,(r.status_code,r.text)
    return r.json()
aid=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','start_date':'2025-01-01'}))['id']
def series(start,end,amount='100'):
    payload={'account_id':aid,'category_id':1,'name':'Miete','amount':amount,'next_date':start,'frequency':'monthly','kind':'direct_debit','active':True,'valid_until':end,'confidence':'fixed','fixed_cost':True}
    return ok(client.post('/api/recurring',json=payload))['id'],payload
rid,payload=series('2026-09-20','2026-11-20')
def move(rid,due,booked,amount='100',note='Einzeltermin'):
    return ok(client.put(f'/api/recurring/{rid}/override',json={'due_date':due,'booking_date':booked,'amount':amount,'note':note}))
def tx(rid,due):
    return c.execute("SELECT t.* FROM transactions t JOIN recurring_occurrences o ON o.transaction_id=t.id JOIN recurring r ON r.id=o.recurring_id WHERE COALESCE(r.series_id,r.id)=? AND o.due_date=?",(rid,due)).fetchone()
def plan(month):
    start,end=main.month_bounds(month)
    return sum(r['amount'] for r in main.planned_month_category_totals(c,start,end).values())
initial=tx(rid,'2026-09-20')['id']
move(rid,'2026-09-20','2026-09-18')
assert tx(rid,'2026-09-20')['booking_date']=='2026-09-18'
move(rid,'2026-09-20','2026-10-01','120','Abweichende Abbuchung')
assert plan('2026-09')==0
assert plan('2026-10')==22000
assert main.planned_fixed_costs(c,*main.month_bounds('2026-10'))==22000
assert main.projected_account_balance(c,aid,real_date(2026,9,30))==100000
assert main.projected_account_balance(c,aid,real_date(2026,10,1))==88000
assert main.projected_account_balance(c,aid,real_date(2026,10,31))==78000
items=ok(client.get('/api/transactions?month=2026-10'))
item=next(x for x in items if x['id']==initial)
assert item['recurring_due_date']=='2026-09-20' and item['booking_date']=='2026-10-01'
assert item['note']=='Abweichende Abbuchung'
# Second edit uses original identity. Legacy amount-only edits retain the move.
ok(client.put(f'/api/recurring/{rid}/override',json={'due_date':item['recurring_due_date'],'amount':'125'}))
assert tx(rid,'2026-09-20')['booking_date']=='2026-10-01'
move(rid,'2026-09-20','2026-10-01')
for _ in range(2):ok(client.post('/api/recurring/materialize-due?month=2026-10'))
assert tx(rid,'2026-09-20')['id']==initial
assert c.execute('SELECT COUNT(*) FROM transactions WHERE recurring_id=?',(rid,)).fetchone()[0]==3
# Original September occurrence must survive a series change beginning October.
ok(client.put(f'/api/recurring/{rid}',json={**payload,'amount':'200','next_date':'2026-10-20','effective_from':'2026-10-01'}))
assert tx(rid,'2026-09-20')['id']==initial
assert plan('2026-10')==30000 and plan('2026-11')==20000
# Returning to the original schedule restores date, amount and identity.
ok(client.delete(f'/api/recurring/{rid}/override?due_date=2026-09-20'))
assert tx(rid,'2026-09-20')['booking_date']=='2026-09-20'
assert plan('2026-09')==10000 and plan('2026-10')==20000
# A moved occurrence outside a finite contract still belongs to the target year.
yrid,_=series('2026-12-20','2026-12-20','77.77')
move(yrid,'2026-12-20','2027-01-01','77.77')
assert plan('2026-12')==0 and plan('2027-01')==7777
assert main.planned_fixed_costs(c,*main.month_bounds('2027-01'))==7777
# Rebuild/materialize at the shifted date; no duplicate at the original due date.
ytx=tx(yrid,'2026-12-20')['id']
c.execute('DELETE FROM recurring_occurrences WHERE transaction_id=?',(ytx,));c.execute('DELETE FROM transactions WHERE id=?',(ytx,));c.commit()
events=main.recurring_events(c,aid,real_date(2027,1,1),real_date(2027,1,31))
assert len(events)==1 and events[0]['due_date'].isoformat()=='2026-12-20' and events[0]['date'].isoformat()=='2027-01-01'
assert not main.recurring_events(c,aid,real_date(2026,12,1),real_date(2026,12,31))
ok(client.post('/api/recurring/materialize-due?month=2027-01'))
assert tx(yrid,'2026-12-20')['booking_date']=='2027-01-01'
assert not main.recurring_events(c,aid,real_date(2027,1,1),real_date(2027,1,31))
# Move a future contractual date earlier, even before the contract's first month.
rid2,_=series('2027-03-20','2027-03-20','50')
move(rid2,'2027-03-20','2027-02-28','50')
assert plan('2027-02')==5000 and plan('2027-03')==0
assert tx(rid2,'2027-03-20')['booking_date']=='2027-02-28'
assert client.put(f'/api/recurring/{rid2}/override',json={'due_date':'2027-03-21','booking_date':'2027-02-28','amount':'50'}).status_code==400
# Rebuilding a new series version retains a future occurrence moved before its cutoff.
rid3,pl3=series('2027-05-20','2027-05-20','80')
move(rid3,'2027-05-20','2027-04-28','85')
ok(client.put(f'/api/recurring/{rid3}',json={**pl3,'amount':'90','effective_from':'2027-05-01'}))
assert tx(rid3,'2027-05-20')['booking_date']=='2027-04-28'
assert tx(rid3,'2027-05-20')['amount']==-8500
assert plan('2027-04')==8500 and plan('2027-05')==0
# API caches end with the request: a subsequent write is reflected immediately.
d1=ok(client.get('/api/dashboard?month=2027-04'))
move(rid3,'2027-05-20','2027-05-02','85')
d2=ok(client.get('/api/dashboard?month=2027-04'))
assert d1['month_end_balance']!=d2['month_end_balance'],(d1.keys(),d2.keys())
# Migration remains repeatable and preserves amounts from schema 26.
c.execute('ALTER TABLE recurring_overrides DROP COLUMN booking_date');c.commit()
db.migrate_schema(c);db.migrate_schema(c)
assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]=='27'
assert c.execute('SELECT amount FROM recurring_overrides WHERE series_id=?',(rid2,)).fetchone()[0]==-5000
print('recurring dates: same month, month/year boundaries, repeat edits, version cutoff, forecasts, rebuild, reset and migration: PASS')
c.close();Path(tmp).unlink(missing_ok=True)
