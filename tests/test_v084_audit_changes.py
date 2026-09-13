import sqlite3,sys,types,tempfile
from pathlib import Path
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
main.db._conn=c
# Create the audit user used by the mocked session.
c.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'admin','x','2026-09-11T00:00:00+00:00')")
c.commit()
main.session=lambda request,write=False:('sid',1,'csrf',0)
main.require_book_owner=lambda request: None; main.require_system_admin=lambda request: None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r): assert r.status_code<300,(r.status_code,r.text); return r.json()
acc=ok(client.post('/api/accounts',json={'name':'C24','type':'checking','opening_balance':'1000.00','currency':'EUR','start_date':'2026-09-01'}))['id']
cat=ok(client.post('/api/categories',json={'name':'Versicherung','direction':'expense'}))['id']
tx=ok(client.post('/api/transactions',json={'account_id':acc,'amount':'80.00','booking_date':'2026-09-11','name':'KFZ-Versicherung','payee':'HUK','category_id':cat,'note':'Monatsbeitrag','status':'executed','tags':['Auto'],'splits':[],'confidence':'fixed','fixed_cost':True}))['id']
# Change only the amount.
ok(client.put(f'/api/transactions/{tx}',json={'account_id':acc,'amount':'93.00','booking_date':'2026-09-11','name':'KFZ-Versicherung','payee':'HUK','category_id':cat,'note':'Monatsbeitrag','status':'executed','tags':['Auto'],'splits':[],'confidence':'fixed','fixed_cost':True,'recurring':False}))
row=c.execute("SELECT details_json,user_id FROM audit_log WHERE action='transaction.update' ORDER BY id DESC LIMIT 1").fetchone()
import json
d=json.loads(row['details_json'])
assert row['user_id']==1,d
assert d['name']=='KFZ-Versicherung',d
assert list(d['changes'])==['amount'],d['changes']
assert d['changes']['amount']=={'old':-8000,'new':-9300},d
# Create entry should contain useful added values.
created=json.loads(c.execute("SELECT details_json FROM audit_log WHERE action='transaction.create' ORDER BY id DESC LIMIT 1").fetchone()[0])
assert created['added']['name']=='KFZ-Versicherung'
assert created['added']['amount']==-8000
assert created['added']['category_name']=='Versicherung'
assert main.APP_VERSION in {'0.8.4','0.8.5','0.8.6','0.8.7','0.9.0','0.10.0','0.10.1','0.10.2','0.10.3','0.10.4','0.10.5','0.11.0','0.11.1','0.11.2','0.21.0','0.21.2','0.21.3'}
print('v0.8.4 detailed audit diff: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
