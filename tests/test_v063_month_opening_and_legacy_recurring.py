import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date,timedelta
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
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

today=date.today(); first=today.replace(day=1); prev_end=first-timedelta(days=1); prev_start=prev_end.replace(day=1)
acc=ok(client.post('/api/accounts',json={'name':'Monatslogik','type':'checking','opening_balance':500,'currency':'EUR','start_date':prev_start.isoformat()}))
exp=ok(client.post('/api/categories',json={'name':'Legacy Ausgabe','direction':'expense'}))
# Simulate an OLD recurring row that wrongly stored an expense as positive 250 EUR.
ts=first.isoformat()+'T00:00:00+00:00'
with main.db.transaction() as tc:
    cur=tc.execute("""INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,created_at)
                      VALUES(?,?,?,?,?,'monthly','direct_debit',NULL,1,NULL,?,?,NULL,?)""",
                   (acc['id'],exp['id'],'Alt-Miete',25000,first.isoformat(),first.isoformat(),first.isoformat(),ts))
    rid=cur.lastrowid; tc.execute('UPDATE recurring SET series_id=? WHERE id=?',(rid,rid))
# Previous-month close and this-month opening are exactly the same value: 500 EUR.
metrics=main.account_month_metrics(c,acc['id'],first.strftime('%Y-%m'))
assert metrics['month_start_balance']==500.0,metrics
# Day 1 applies -250, never +250; all later days start from 250 unless another event occurs.
series=main.monthly_account_series(c,acc['id'],first.strftime('%Y-%m'))
assert series[0]['opening_balance']==500.0,series[0]
assert series[0]['balance']==250.0,series[0]
if len(series)>1: assert series[1]['balance']==250.0,series[1]
assert metrics['month_end_balance']<=250.0,metrics
# Marking the due item as booked must preserve the same economic balance, not flip it upward.
before=metrics['balance']
exec_result=ok(client.post(f'/api/recurring/{rid}/execute'))
metrics2=main.account_month_metrics(c,acc['id'],first.strftime('%Y-%m'))
assert metrics2['balance']==before,(before,metrics2,exec_result)
tx=c.execute('SELECT amount,direction FROM transactions WHERE id=?',(exec_result['transaction_id'],)).fetchone()
assert tx['direction']=='expense' and tx['amount']==-25000,dict(tx)
assert tuple(map(int,main.APP_VERSION.split('.'))) >= (0,6,3)
print('v0.6.3 month opening + legacy recurring sign + execute invariance: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
