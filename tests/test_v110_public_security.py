import os,sys,types,tempfile,shutil,sqlite3
from pathlib import Path
os.environ.update({
    'HAUSHALTPRO_MODE':'public','SECURE_COOKIES':'true','TRUST_PROXY_HEADERS':'true','ENFORCE_HTTPS':'true',
    'ALLOW_SELF_REGISTRATION':'false','ALLOWED_HOSTS':'secure.example.test','PUBLIC_SETUP_TOKEN':'0123456789abcdef0123456789abcdef',
    'MAX_REQUEST_BYTES':'1024'
})
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main
base=Path(tempfile.mkdtemp(prefix='hp110-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
https=TestClient(main.app,base_url='https://secure.example.test')
# Public status is intentionally minimal but tells the UI how to behave.
st=https.get('/api/status');assert st.status_code==200,st.text;j=st.json();assert j['public_mode'] is True and j['registration_enabled'] is False and j['setup_token_required'] is True
assert 'active_sessions' not in j and 'locked' not in j
# Health endpoint does not disclose version/session state.
h=https.get('/healthz');assert h.json()=={'status':'ok'}
# First setup requires the out-of-band token.
bad=https.post('/api/setup',json={'username':'admin','password':'SehrLangesAdminPasswort123!','trusted_device':False});assert bad.status_code==403,bad.text
ok=https.post('/api/setup',json={'username':'admin','password':'SehrLangesAdminPasswort123!','trusted_device':False,'setup_token':'0123456789abcdef0123456789abcdef'});assert ok.status_code==200,ok.text
cookie=ok.headers.get('set-cookie','');assert '__Host-haushaltpro_session=' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
# HTTPS response headers.
r=https.get('/api/status');assert r.headers.get('strict-transport-security','').startswith('max-age=')
assert r.headers.get('cross-origin-opener-policy')=='same-origin' and r.headers.get('cache-control','').startswith('no-store')
# Self-registration is closed in public mode.
reg=https.post('/api/register',json={'username':'xuser','password':'SehrLangesNutzerPasswort123!'});assert reg.status_code==403,reg.text
# Host allow-list rejects an unexpected public hostname.
badhost=TestClient(main.app,base_url='https://evil.example.test');assert badhost.get('/api/status').status_code==400
# Plain HTTP is rejected except healthz.
plain=TestClient(main.app,base_url='http://secure.example.test');assert plain.get('/api/status').status_code==426
# Body-size guard fires before endpoint/form parsing.
big=https.post('/api/login',content=b'x'*2048,headers={'content-type':'application/octet-stream'});assert big.status_code==413,big.text
print('v0.11.0 public-mode runtime hardening: PASS')
shutil.rmtree(base,ignore_errors=True)
