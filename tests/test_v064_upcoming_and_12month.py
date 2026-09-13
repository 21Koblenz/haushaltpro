import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
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

# Environment date is 2026-09-11. A future October selection must show ALL
# October payments still in the real future, including October 1..11.
assert main.date.today().isoformat()=='2026-09-11',main.date.today()
acc=ok(client.post('/api/accounts',json={'name':'12M','type':'checking','opening_balance':5000,'currency':'EUR','start_date':'2025-11-01'}))
exp=ok(client.post('/api/categories',json={'name':'Miete','direction':'expense'}))
inc=ok(client.post('/api/categories',json={'name':'Gehalt','direction':'income'}))
# monthly rent on the 1st and salary on the 15th.  The rent row simulates
# an existing pre-upgrade contract created on Sep 1; startup synchronization
# should create its future journal schedule without inventing missed history.
cur=c.execute("""INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at)
                 VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)""",
              (acc['id'],exp['id'],'Miete',-80000,'2026-09-01','monthly','direct_debit',None,1,'2026-09-01','2026-09-01',None,'fixed',0,'2026-09-01T00:00:00+00:00'))
rent_id=cur.lastrowid; c.execute('UPDATE recurring SET series_id=? WHERE id=?',(rent_id,rent_id)); c.commit()
sync=ok(client.post('/api/recurring/materialize-due')); assert sync['scope']=='all'
ok(client.post('/api/recurring',json={'account_id':acc['id'],'category_id':inc['id'],'name':'Gehalt','amount':2000,'next_date':'2026-09-15','frequency':'monthly','kind':'income','active':True,'valid_until':None,'max_amount':None}))

dash=ok(client.get('/api/dashboard?month=2026-10'))
by_name={x['name']:x for x in dash['next_payments']}
assert by_name['Miete']['date']=='2026-10-01',dash['next_payments']
assert by_name['Miete']['amount']==-800.0,by_name['Miete']
assert by_name['Gehalt']['date']=='2026-10-15',dash['next_payments']
# 12 rows ending in selected October, and recurring values must populate months
months=dash['analysis']['monthly_overview']
assert len(months)==12,len(months)
assert months[-1]['month']=='2026-10',months[-1]
assert months[0]['month']=='2025-11',months[0]
october=months[-1]
assert october['income']==2000.0,october
assert october['expense']==800.0,october
# September contains the September occurrences too, showing this isn't a one-month chart.
september=[m for m in months if m['month']=='2026-09'][0]
assert september['income']==2000.0,september
assert september['expense']==800.0,september
print('v0.6.4 upcoming real-date semantics + 12-month recurring overview: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
