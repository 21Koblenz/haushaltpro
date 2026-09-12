import sqlite3,sys,types,tempfile,shutil
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root));Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists():static.symlink_to(root/'static',target_is_directory=True)
from app import db,main
base=Path(tempfile.mkdtemp(prefix='hp100mig-'));db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main._app_sessions.clear()
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True);c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
db.connect=plain_connect
# Emulate v0.9.0 single-DB state.
c=plain_connect('legacy',db.DB_PATH);db._conn=c;db.init_schema(c)
legacy=main._make_auth_user('AltAdmin','AltesPasswort123!',True,'owner','legacy-master')
c.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",('AltAdmin',legacy['password_hash'],main.iso(main.utcnow())))
c.execute("INSERT INTO accounts(name,type,opening_balance,currency,active,start_date,created_at) VALUES('Altes Giro','checking',12345,'EUR',1,'2025-01-01',?)",(main.iso(main.utcnow()),));c.commit();db._conn=None;c.close()
main._auth_save({'version':1,'users':{'altadmin':legacy}})
from fastapi.testclient import TestClient
cl=TestClient(main.app)
r=cl.post('/api/login',json={'username':'AltAdmin','password':'AltesPasswort123!','trusted_device':False});assert r.status_code==200,r.text
me=cl.get('/api/me').json();assert me['book']['id']=='default' and me['book']['name']=='Haushalt' and me['role']=='owner',me
accounts=cl.get('/api/accounts').json();assert any(a['name']=='Altes Giro' for a in accounts),accounts
auth=main._auth_load();assert auth['version']==2 and 'default' in auth['books'];assert auth['books']['default']['path']==str(db.DB_PATH);assert auth['books']['default']['members']['altadmin']['role']=='owner'
assert db.DB_PATH.exists() and not (base/'books'/'default.db').exists()
print('v0.9.0 -> v0.10.0 auth/database migration: PASS')
shutil.rmtree(base,ignore_errors=True)
