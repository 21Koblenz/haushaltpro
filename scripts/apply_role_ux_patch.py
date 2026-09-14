from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
main_path = root / "app" / "main.py"
text = main_path.read_text(encoding="utf-8")


def must_replace(src: str, old: str, new: str, label: str) -> str:
    if old not in src:
        raise SystemExit(f"patch marker missing: {label}")
    return src.replace(old, new, 1)


def must_sub(src: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, src, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"patch pattern mismatch ({count}): {label}")
    return out

# 1) CSRF-authenticated self-service actions must not depend on household write role.
owner_admin_block = '''def require_system_admin(request: Request):
    session(request)
    _,rec=_session_record(request);data=_auth_load_v2();u=data.get("users",{}).get(rec["user_key"],{})
    if u.get("system_role")!="admin": raise HTTPException(403,"Nur Administratoren dürfen diese Funktion verwenden")
    return rec
'''
owner_admin_replacement = owner_admin_block + '''\n\ndef require_csrf_session(request: Request):
    """Authenticate a state-changing user-account action without requiring book write rights."""
    sess=session(request)
    sent=request.headers.get("X-CSRF-Token")
    if not sent or not hmac.compare_digest(sent,sess[2]):
        raise HTTPException(403,"CSRF-Prüfung fehlgeschlagen")
    return sess
'''
text = must_replace(text, owner_admin_block, owner_admin_replacement, "require_csrf_session")

# 2) Owner-created/reset passwords are temporary until the user changes them.
pattern = r'(@app\.post\("/api/users"\)\ndef admin_user_create\(.*?data\.setdefault\("users",\{\}\)\[user_key\]=\{)(.*?)(\}\n    book\.setdefault)'
m = re.search(pattern, text, flags=re.S)
if not m:
    raise SystemExit("patch pattern missing: admin_user_create")
body = m.group(2)
if '"must_change_password":True' not in body:
    body = body.replace('"system_role":"user",', '"system_role":"user","must_change_password":True,', 1)
text = text[:m.start()] + m.group(1) + body + m.group(3) + text[m.end():]

text = must_replace(
    text,
    'target.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob})',
    'target.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob,"must_change_password":True})',
    "temporary password reset flag",
)

# 3) Expose temporary-password state to the logged-in user.
text = must_replace(
    text,
    '"book":{"id":rec["book_id"],"name":book.get("name",rec["book_id"])},"books":_user_books(data,rec["user_key"]),"csrf":s[2],"trusted_device":bool(s[3]),"autolock_minutes":int(setting_value(db.db(),"autolock_minutes","15"))}',
    '"book":{"id":rec["book_id"],"name":book.get("name",rec["book_id"])},"books":_user_books(data,rec["user_key"]),"csrf":s[2],"trusted_device":bool(s[3]),"autolock_minutes":int(setting_value(db.db(),"autolock_minutes","15")),"must_change_password":bool(entry.get("must_change_password",False))}',
    "me must_change_password",
)

# 4) Own password change: CSRF + authentication only, never household-role gated.
text = must_replace(
    text,
    'def change_password(x: PasswordChangeIn,request: Request):\n    sess=session(request,True);th,rec=_session_record(request);data=_auth_load_v2();entry=data["users"][rec["user_key"]]',
    'def change_password(x: PasswordChangeIn,request: Request):\n    sess=require_csrf_session(request);th,rec=_session_record(request);data=_auth_load_v2();entry=data["users"][rec["user_key"]]\n    validate_new_password(x.new_password)',
    "self password auth",
)
text = must_replace(
    text,
    'entry.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob});_auth_save(data);rec["private_key"]=new_private',
    'entry.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob,"must_change_password":False});_auth_save(data);rec["private_key"]=new_private',
    "clear temporary password flag",
)

# 5) Audit and storage metadata are owner-only, including direct API calls.
text = must_replace(
    text,
    'def audit_timeline(request: Request, q: str | None = None, page: int = 1, page_size: int = 25, limit: int | None = None, offset: int | None = None):\n    session(request);can_delete=False',
    'def audit_timeline(request: Request, q: str | None = None, page: int = 1, page_size: int = 25, limit: int | None = None, offset: int | None = None):\n    require_book_owner(request);can_delete=True',
    "audit owner gate",
)
text = must_replace(
    text,
    'def admin_storage(request: Request):\n    session(request);path=db.active_path();c=db.db()',
    'def admin_storage(request: Request):\n    require_book_owner(request);path=db.active_path();c=db.db()',
    "storage owner gate",
)

# 6) Book creation requests: editors may request a book, an owner of the source
# household must approve it. The approver owns the new book; requester remains editor.
book_block_pattern = r'@app\.post\("/api/books"\)\ndef book_create\(x: BookIn,request: Request\):.*?(?=@app\.post\("/api/books/\{book_id\}/switch"\))'
book_replacement = r'''def _create_book_record(data: dict, owner_key: str, name: str, editor_key: str | None = None) -> dict:
    uid=secrets.token_hex(8);BOOKS_DIR.mkdir(parents=True,exist_ok=True);path=BOOKS_DIR/f"{uid}.db";master=secrets.token_urlsafe(48)
    owner=data.get("users",{}).get(owner_key)
    if not owner: raise HTTPException(404,"Eigentümer nicht gefunden")
    clean_name=clean_text(name,80) or "Haushalt"
    members={owner_key:{"role":"owner","wrapped_master":_wrap_master(owner["public_key"],master)}}
    editor=None
    if editor_key and editor_key!=owner_key:
        editor=data.get("users",{}).get(editor_key)
        if not editor: raise HTTPException(409,"Anfragender Benutzer existiert nicht mehr")
        members[editor_key]={"role":"editor","wrapped_master":_wrap_master(editor["public_key"],master)}
    db.activate(path,master);c=db.unlock(master,initialize=True,path=path,set_default=False)
    owner_uid=_ensure_book_user(c,owner["username"],owner["password_hash"])
    if editor:_ensure_book_user(c,editor["username"],editor["password_hash"])
    data.setdefault("books",{})[uid]={"id":uid,"name":clean_name,"path":str(path),"created_at":iso(utcnow()),"members":members}
    audit_append(c,owner_uid,"book.create","book",uid,{"name":clean_name,"requested_by":editor["username"] if editor else None});c.commit()
    return {"id":uid,"name":clean_name,"path":str(path),"master":master}


@app.post("/api/books")
def book_create(x: BookIn,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();user=data.get("users",{}).get(rec["user_key"],{})
    source=data.get("books",{}).get(rec["book_id"],{});role=source.get("members",{}).get(rec["user_key"],{}).get("role","viewer")
    if user.get("system_role")=="admin" or role=="owner":
        result=_create_book_record(data,rec["user_key"],x.name);_auth_save(data)
        db.activate(_book_path(source),rec["book_master"])
        return {"id":result["id"],"name":result["name"],"pending":False}
    if role!="editor": raise HTTPException(403,"Nur Bearbeiter oder Eigentümer dürfen ein neues Haushaltsbuch beantragen")
    clean_name=clean_text(x.name,80) or "Haushalt";requests=data.setdefault("book_requests",{})
    for existing in requests.values():
        if existing.get("status","pending")=="pending" and existing.get("requested_by")==rec["user_key"] and existing.get("source_book_id")==rec["book_id"] and str(existing.get("name","")).casefold()==clean_name.casefold():
            return {"id":existing["id"],"name":existing["name"],"pending":True}
    rid=secrets.token_hex(8);req={"id":rid,"name":clean_name,"requested_by":rec["user_key"],"source_book_id":rec["book_id"],"created_at":iso(utcnow()),"status":"pending"};requests[rid]=req;_auth_save(data)
    c=db.db();audit_append(c,sess[1],"book.request","book",rid,{"name":clean_name,"requested_by":user.get("username")});c.commit()
    return {"id":rid,"name":clean_name,"pending":True}


@app.get("/api/book-requests")
def book_requests(request: Request):
    session(request);_,rec=_session_record(request);data=_auth_load_v2();user=data.get("users",{}).get(rec["user_key"],{});source=data.get("books",{}).get(rec["book_id"],{})
    role=source.get("members",{}).get(rec["user_key"],{}).get("role","viewer");can_approve=user.get("system_role")=="admin" or role=="owner"
    out=[]
    for req in data.get("book_requests",{}).values():
        if req.get("status","pending")!="pending": continue
        if can_approve:
            if req.get("source_book_id")!=rec["book_id"]: continue
        elif role=="editor":
            if req.get("requested_by")!=rec["user_key"]: continue
        else:
            continue
        row=dict(req);target=data.get("users",{}).get(req.get("requested_by"),{});row["requested_by_username"]=target.get("username",req.get("requested_by"));row["can_approve"]=can_approve;out.append(row)
    return sorted(out,key=lambda r:r.get("created_at","") or "")


@app.post("/api/book-requests/{request_id}/approve")
def book_request_approve(request_id: str,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();req=data.get("book_requests",{}).get(request_id)
    if not req or req.get("status","pending")!="pending": raise HTTPException(404,"Haushaltsbuch-Anfrage nicht gefunden")
    if req.get("source_book_id")!=rec["book_id"] or not _can_manage_book(data,rec["book_id"],rec["user_key"]): raise HTTPException(403,"Nur ein Eigentümer des freigebenden Haushaltsbuchs darf diese Anfrage bestätigen")
    source=data["books"][rec["book_id"]];result=_create_book_record(data,rec["user_key"],req["name"],req.get("requested_by"));data.get("book_requests",{}).pop(request_id,None);_auth_save(data)
    db.activate(_book_path(source),rec["book_master"]);c=db.db();audit_append(c,sess[1],"book.request.approve","book",result["id"],{"name":result["name"],"request_id":request_id});c.commit()
    return {"ok":True,"id":result["id"],"name":result["name"]}


@app.delete("/api/book-requests/{request_id}")
def book_request_reject(request_id: str,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();req=data.get("book_requests",{}).get(request_id)
    if not req or req.get("status","pending")!="pending": raise HTTPException(404,"Haushaltsbuch-Anfrage nicht gefunden")
    if req.get("source_book_id")!=rec["book_id"] or not _can_manage_book(data,rec["book_id"],rec["user_key"]): raise HTTPException(403,"Nur ein Eigentümer des freigebenden Haushaltsbuchs darf diese Anfrage ablehnen")
    data.get("book_requests",{}).pop(request_id,None);_auth_save(data);c=db.db();audit_append(c,sess[1],"book.request.reject","book",request_id,{"name":req.get("name")});c.commit();return {"ok":True}


'''
text = must_sub(text, book_block_pattern, book_replacement, "book request workflow")

main_path.write_text(text, encoding="utf-8")

# Add a focused integration/regression test.
test = r'''import sqlite3,sys,types,tempfile,shutil
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
'''
(root / 'tests' / 'test_v0217_role_boundaries.py').write_text(test, encoding='utf-8')

print('role/password/book request patch applied')
