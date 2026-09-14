import sqlite3,sys,types,tempfile,shutil
from pathlib import Path
shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
from app import db
from app import main

base=Path(tempfile.mkdtemp(prefix='hp217-'))
def plain_connect(key,path=None):
    target=Path(path or db.DB_PATH);target.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(str(target),check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA busy_timeout=5000');return c

db.close();db._conn=None;db._master_key=None;db._connections=set();db.DB_PATH=base/'haushaltpro.db';db.connect=plain_connect
main.AUTH_PATH=base/'auth.json';main.BOOKS_DIR=base/'books';main.BACKUP_DIR=base/'backups';main._app_sessions.clear()
from fastapi.testclient import TestClient
admin=TestClient(main.app);editor=TestClient(main.app)

def ok(r): assert r.status_code<300,(r.status_code,r.text);return r.json()
def csrf(client): return ok(client.get('/api/me'))['csrf']
def post(client,url,j=None): return client.post(url,json=j,headers={'X-CSRF-Token':csrf(client)})
def put(client,url,j=None): return client.put(url,json=j,headers={'X-CSRF-Token':csrf(client)})
def delete(client,url,j=None): return client.request('DELETE',url,json=j,headers={'X-CSRF-Token':csrf(client)})

ok(admin.post('/api/setup',json={'username':'admin','password':'AdminPasswort123!','trusted_device':False}))
ok(post(admin,'/api/users',{'username':'editor','password':'TempPasswort123!','role':'editor'}))
ok(editor.post('/api/login',json={'username':'editor','password':'TempPasswort123!','trusted_device':False}))
eme=ok(editor.get('/api/me'));assert eme['role']=='editor' and eme['must_change_password'] is True,eme

# Self-service password change is independent of household admin rights.
ok(post(editor,'/api/password',{'current_password':'TempPasswort123!','new_password':'EigenesPasswort456!'}))
eme=ok(editor.get('/api/me'));assert eme['must_change_password'] is False,eme

# Sensitive owner/admin areas are inaccessible even through direct HTTP calls.
assert editor.get('/api/audit/timeline').status_code==403
assert editor.get('/api/admin/storage').status_code==403
assert editor.get('/api/users').status_code==403
assert put(editor,'/api/books/default',{'name':'Nicht erlaubt'}).status_code==403

# Editor may request a new book, but cannot create/own/delete it directly.
req=ok(post(editor,'/api/books',{'name':'Editor Projekt'}));assert req['pending'] is True,req
own_requests=ok(editor.get('/api/book-requests'));assert len(own_requests)==1 and own_requests[0]['id']==req['id']
admin_requests=ok(admin.get('/api/book-requests'));assert len(admin_requests)==1 and admin_requests[0]['requested_by_username']=='editor'
approved=ok(post(admin,f"/api/book-requests/{req['id']}/approve"));book_id=approved['id']
assert ok(admin.get('/api/book-requests'))==[]
editor_books=ok(editor.get('/api/books'));created=next(x for x in editor_books if x['id']==book_id);assert created['role']=='editor',created
admin_books=ok(admin.get('/api/books'));created_admin=next(x for x in admin_books if x['id']==book_id);assert created_admin['role']=='owner',created_admin
assert delete(editor,f'/api/books/{book_id}',{'confirmation':'Editor Projekt'}).status_code==403
assert put(editor,f'/api/books/{book_id}',{'name':'Nicht erlaubt'}).status_code==403

# Owner still retains the owner-only views.
assert admin.get('/api/audit/timeline').status_code==200
assert admin.get('/api/admin/storage').status_code==200

# UI regression: owner-only cards are role-gated and transaction table is responsive.
js=(root/'static/ui-enhancements.js').read_text(encoding='utf-8');css=(root/'static/ui-enhancements.css').read_text(encoding='utf-8')
for needle in ('.user-management-card','.data-maintenance-card','.settings-audit-card','must_change_password','/api/book-requests','newPasswordConfirm'):
    assert needle in js,needle
for needle in ('#txAllView tbody{display:grid','content:attr(data-label)','overflow-x:visible','@media(max-width:1100px)'):
    assert needle in css,needle
print('v0.21.7 role/password/book-request/responsive-table regression: PASS')
shutil.rmtree(base,ignore_errors=True)
