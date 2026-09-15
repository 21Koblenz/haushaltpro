import base64
import calendar
import csv
import hashlib
import hmac
import ipaddress
import io
import json
import os
import re
import secrets
import shutil
import statistics
import threading
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from . import db

APP_VERSION = "0.21.9-dev"

PUBLIC_MODE = os.getenv("HAUSHALTPRO_MODE", "lan").strip().lower() == "public"
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "true" if PUBLIC_MODE else "false").lower() == "true"
TRUST_PROXY_HEADERS = os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true"
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "true" if PUBLIC_MODE else "false").lower() == "true"
ALLOW_SELF_REGISTRATION = os.getenv("ALLOW_SELF_REGISTRATION", "false" if PUBLIC_MODE else "true").lower() == "true"
PUBLIC_SETUP_TOKEN = os.getenv("PUBLIC_SETUP_TOKEN", "")
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "").split(",") if x.strip()]
MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", str(25 * 1024 * 1024)))
HSTS_INCLUDE_SUBDOMAINS = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"

if PUBLIC_MODE:
    if not SECURE_COOKIES:
        raise RuntimeError("Public-Modus erfordert SECURE_COOKIES=true")
    if not ALLOWED_HOSTS or any(x == "*" for x in ALLOWED_HOSTS):
        raise RuntimeError("Public-Modus erfordert konkrete ALLOWED_HOSTS, z. B. haushalt.example.de")

class RequestBodyLimitMiddleware:
    """Reject oversized request bodies before multipart/form parsing can consume them."""
    def __init__(self, app, max_bytes: int):
        self.app=app; self.max_bytes=max_bytes
    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        headers={k.lower():v for k,v in scope.get("headers",[])}
        raw=headers.get(b"content-length")
        if raw:
            try:
                if int(raw) > self.max_bytes:
                    return await JSONResponse({"detail":"Request zu groß"}, status_code=413)(scope, receive, send)
            except ValueError:
                return await JSONResponse({"detail":"Ungültige Content-Length"}, status_code=400)(scope, receive, send)
        seen=0
        async def limited_receive():
            nonlocal seen
            message=await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body",b""))
                if seen > self.max_bytes:
                    raise HTTPException(413,"Request zu groß")
            return message
        try:
            return await self.app(scope, limited_receive, send)
        except HTTPException as exc:
            if exc.status_code == 413:
                return await JSONResponse({"detail":"Request zu groß"}, status_code=413)(scope, receive, send)
            raise

app = FastAPI(title="HaushaltPro", version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=700)
app.add_middleware(RequestBodyLimitMiddleware, max_bytes=MAX_REQUEST_BYTES)
if PUBLIC_MODE:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS, www_redirect=False)
app.mount("/assets", StaticFiles(directory="/app/static"), name="assets")
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MINUTES", "120" if PUBLIC_MODE else "720"))
TRUSTED_TTL_DAYS = int(os.getenv("TRUSTED_SESSION_TTL_DAYS", "7" if PUBLIC_MODE else "30"))
COOKIE_NAME = "__Host-haushaltpro_session" if SECURE_COOKIES else "haushaltpro_session"
MAX_UPLOAD = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(5 * 1024 * 1024)))
MAX_ATTACHMENT_TOTAL_BYTES = int(os.getenv("MAX_ATTACHMENT_TOTAL_BYTES", str(100 * 1024 * 1024)))
MAX_ATTACHMENTS_PER_TX = int(os.getenv("MAX_ATTACHMENTS_PER_TX", "10"))
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/data/backups"))
BOOKS_DIR = Path(os.getenv("BOOKS_DIR", "/data/books"))
MAX_BACKUP_STORAGE_BYTES = int(os.getenv("MAX_BACKUP_STORAGE_BYTES", str(2 * 1024 * 1024 * 1024)))
LOGIN_WINDOW_SECONDS = 300
LOGIN_MAX_FAILURES = 5
LOGIN_BLOCK_SECONDS = 900
_login_lock = threading.Lock()
_login_failures: dict[str, deque] = defaultdict(deque)
_login_blocked_until: dict[str, datetime] = {}
_request_rate_lock = threading.Lock()
_request_rate: dict[str, deque] = defaultdict(deque)
_setup_lock = threading.Lock()

def client_ip(request: Request) -> str:
    raw = request.client.host if request.client else "unknown"
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "").split(",",1)[0].strip()
        if forwarded:
            try:
                raw=str(ipaddress.ip_address(forwarded))
            except ValueError:
                pass
    return raw

def rate_limit(request: Request, bucket: str, limit: int, window_seconds: int) -> None:
    key=f"{bucket}|{client_ip(request)}"
    now=time.monotonic()
    with _request_rate_lock:
        dq=_request_rate[key]
        while dq and dq[0] <= now-window_seconds:
            dq.popleft()
        if len(dq) >= limit:
            raise HTTPException(429,"Zu viele Anfragen. Bitte später erneut versuchen.",headers={"Retry-After":str(window_seconds)})
        dq.append(now)


_view_cache_lock = threading.RLock()
_view_cache: dict[tuple, tuple[float, object]] = {}
_view_cache_generation: dict[str, int] = defaultdict(int)

def _cache_path_key() -> str:
    try:
        return str(db.active_path())
    except Exception:
        return "default"

def _cache_invalidate_active() -> None:
    if db._conn is not None:
        return
    path=_cache_path_key()
    with _view_cache_lock:
        _view_cache_generation[path]+=1
        for key in list(_view_cache):
            if key and key[0]==path:
                _view_cache.pop(key,None)

def _cache_get(scope: str, *parts, ttl: float = 20.0):
    if db._conn is not None:
        return None
    path=_cache_path_key()
    with _view_cache_lock:
        key=(path,_view_cache_generation[path],scope,*parts)
        hit=_view_cache.get(key)
        if not hit:
            return None
        expires,value=hit
        if expires < time.monotonic():
            _view_cache.pop(key,None)
            return None
        return value

def _cache_set(scope: str, value, *parts, ttl: float = 20.0):
    if db._conn is not None:
        return value
    path=_cache_path_key()
    with _view_cache_lock:
        key=(path,_view_cache_generation[path],scope,*parts)
        _view_cache[key]=(time.monotonic()+ttl,value)
        if len(_view_cache)>160:
            now=time.monotonic()
            for k,(exp,_) in list(_view_cache.items()):
                if exp<now:
                    _view_cache.pop(k,None)
    return value


AUTH_PATH = Path(os.getenv("AUTH_PATH", "/data/auth.json"))
_auth_lock = threading.RLock()
_master_key: str | None = None
AUTH_KDF_ITER = 600000

def _auth_load() -> dict:
    if not AUTH_PATH.exists():
        return {"version": 1, "users": {}}
    with _auth_lock:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))

def _auth_save(data: dict) -> None:
    with _auth_lock:
        AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = AUTH_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(AUTH_PATH)


_app_session_lock = threading.RLock()
_app_sessions: dict[str, dict] = {}

def _auth_v2(data: dict) -> dict:
    """Migrate the old one-database auth document to multi-book auth metadata."""
    if int(data.get("version",1)) >= 2 and "books" in data:
        return data
    users=data.setdefault("users",{})
    members={}
    for key,u in users.items():
        if u.get("approved") and u.get("wrapped_master"):
            members[key]={"role":"owner" if u.get("role")=="owner" else "editor","wrapped_master":u.get("wrapped_master")}
        u["system_role"]="admin" if u.get("role")=="owner" else "user"
        u.pop("approved",None);u.pop("role",None);u.pop("wrapped_master",None)
    data["version"]=2
    data.setdefault("books",{})["default"]={
        "id":"default","name":"Haushalt","path":str(db.DB_PATH),"created_at":iso(utcnow()),"members":members
    }
    return data

def _auth_load_v2(save_migration: bool=True) -> dict:
    data=_auth_load(); before=int(data.get("version",1)); data=_auth_v2(data)
    if save_migration and before < 2 and data.get("users"):
        _auth_save(data)
    return data

def _book_path(book: dict) -> Path:
    return Path(book.get("path") or (BOOKS_DIR / (str(book.get("id"))+".db")))

def _user_books(data: dict, user_key: str) -> list[dict]:
    out=[]
    for bid,b in data.get("books",{}).items():
        m=b.get("members",{}).get(user_key)
        if m:
            out.append({"id":bid,"name":b.get("name",bid),"role":m.get("role","viewer"),"path":str(_book_path(b))})
    return sorted(out,key=lambda x:x["name"].casefold())

def _unwrap_book_master(data: dict, book_id: str, user_key: str, private) -> str:
    book=data.get("books",{}).get(book_id)
    if not book: raise HTTPException(404,"Haushaltsbuch nicht gefunden")
    member=book.get("members",{}).get(user_key)
    if not member or not member.get("wrapped_master"):
        raise HTTPException(403,"Kein Zugriff auf dieses Haushaltsbuch")
    return _unwrap_master(private,member["wrapped_master"])

def _ensure_book_user(c, username: str, password_hash: str) -> int:
    row=c.execute("SELECT id FROM users WHERE username=?",(username,)).fetchone()
    if row: return int(row[0])
    cur=c.execute("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",(username,password_hash,iso(utcnow())))
    c.commit(); return int(cur.lastrowid)

def _session_record(request: Request) -> tuple[str,dict]:
    raw=request.cookies.get(COOKIE_NAME)
    if not raw: raise HTTPException(401,"Nicht angemeldet")
    th=token_hash(raw)
    with _app_session_lock:
        rec=_app_sessions.get(th)
    if not rec: raise HTTPException(401,"Nicht angemeldet")
    return th,rec

def _activate_session_book(rec: dict) -> tuple[dict,dict,int]:
    data=_auth_load_v2()
    book=data.get("books",{}).get(rec["book_id"])
    if not book: raise HTTPException(401,"Haushaltsbuch nicht mehr verfügbar")
    member=book.get("members",{}).get(rec["user_key"])
    if not member: raise HTTPException(403,"Zugriff auf Haushaltsbuch entzogen")
    master=rec.get("book_master")
    if not master:
        master=_unwrap_book_master(data,rec["book_id"],rec["user_key"],rec["private_key"]);rec["book_master"]=master
    db.activate(_book_path(book),master)
    if not db.is_initialized(_book_path(book)):
        raise HTTPException(500,"Haushaltsbuch-Datenbank fehlt")
    try: c=db.db()
    except Exception:
        c=db.unlock(master,path=_book_path(book),set_default=False)
    entry=data.get("users",{}).get(rec["user_key"],{})
    uid=_ensure_book_user(c,entry.get("username",rec["username"]),entry.get("password_hash","!"))
    return data,member,uid

def _permission_set(role: str) -> list[str]:
    if role=="owner": return ["read","write","delete","manage_users","backup","settings"]
    if role=="editor": return ["read","write"]
    return ["read"]

def require_book_owner(request: Request):
    session(request)
    _,rec=_session_record(request)
    data=_auth_load_v2();book=data.get("books",{}).get(rec["book_id"],{});member=book.get("members",{}).get(rec["user_key"],{})
    if member.get("role")!="owner" and data.get("users",{}).get(rec["user_key"],{}).get("system_role")!="admin":
        raise HTTPException(403,"Nur Eigentümer dürfen diese Funktion verwenden")
    return rec

def require_system_admin(request: Request):
    session(request)
    _,rec=_session_record(request);data=_auth_load_v2();u=data.get("users",{}).get(rec["user_key"],{})
    if u.get("system_role")!="admin": raise HTTPException(403,"Nur Administratoren dürfen diese Funktion verwenden")
    return rec


def require_csrf_session(request: Request):
    """Authenticate a state-changing user-account action without requiring book write rights."""
    sess=session(request)
    sent=request.headers.get("X-CSRF-Token")
    if not sent or not hmac.compare_digest(sent,sess[2]):
        raise HTTPException(403,"CSRF-Prüfung fehlgeschlagen")
    return sess

def _password_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA512(), length=32, salt=salt, iterations=AUTH_KDF_ITER).derive(password.encode())

def _new_user_crypto(password: str) -> tuple[str,str,dict]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public = private.public_key()
    public_pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    private_pem = private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    salt, nonce = os.urandom(16), os.urandom(12)
    cipher = AESGCM(_password_key(password, salt)).encrypt(nonce, private_pem, b"HaushaltPro user key v1")
    blob = {"salt": salt.hex(), "nonce": nonce.hex(), "ciphertext": cipher.hex()}
    return ph.hash(password), public_pem, blob

def _unlock_private(password: str, blob: dict):
    salt, nonce, ct = bytes.fromhex(blob["salt"]), bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"])
    pem = AESGCM(_password_key(password, salt)).decrypt(nonce, ct, b"HaushaltPro user key v1")
    return load_pem_private_key(pem, password=None)

def _wrap_master(public_pem: str, master: str) -> str:
    pub = load_pem_public_key(public_pem.encode())
    return pub.encrypt(master.encode(), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=b"HaushaltPro DB master v1")).hex()

def _unwrap_master(private, wrapped_hex: str) -> str:
    return private.decrypt(bytes.fromhex(wrapped_hex), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=b"HaushaltPro DB master v1")).decode()

def _make_auth_user(username: str, password: str, approved: bool, role: str, master: str | None = None) -> dict:
    password_hash, public_pem, private_blob = _new_user_crypto(password)
    return {"username": username, "password_hash": password_hash, "public_key": public_pem, "private_key": private_blob, "approved": approved, "role": role, "wrapped_master": _wrap_master(public_pem, master) if approved and master else None, "created_at": iso(utcnow())}

def _auth_entry(username: str):
    data = _auth_load()
    return data, data.get("users", {}).get(username.casefold())

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def money_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value))
    if not d.is_finite():
        raise ValueError("Ungültiger Geldbetrag")
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def cents(value) -> int:
    return int((money_decimal(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def euros(value: int) -> float:
    return round(value / 100, 2)


def audit_append(c, user_id: int | None, action: str, entity_type: str, entity_id, details: dict | None = None) -> str:
    created = iso(utcnow())
    payload_details = dict(details or {})
    if user_id:
        u = c.execute("SELECT username FROM users WHERE id=?",(user_id,)).fetchone()
        if u and "_actor_username" not in payload_details:
            payload_details["_actor_username"] = u[0]
    details_json = json.dumps(payload_details, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    prev = c.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = str(prev[0]) if prev else "GENESIS"
    audit_user_id=user_id if user_id and c.execute("SELECT 1 FROM users WHERE id=?",(user_id,)).fetchone() else None
    payload = "|".join([prev_hash, str(audit_user_id or ""), action, entity_type, str(entity_id or ""), details_json, created])
    entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    c.execute("""INSERT INTO audit_log(user_id,action,entity_type,entity_id,details_json,prev_hash,entry_hash,created_at)
                 VALUES(?,?,?,?,?,?,?,?)""",
              (audit_user_id, action, entity_type, str(entity_id) if entity_id is not None else None, details_json, prev_hash, entry_hash, created))
    return entry_hash


def audit_verify(c) -> tuple[bool, list[str]]:
    errors=[]; expected_prev="GENESIS"
    for r in c.execute("SELECT id,user_id,action,entity_type,entity_id,details_json,prev_hash,entry_hash,created_at FROM audit_log ORDER BY id").fetchall():
        if r["prev_hash"] != expected_prev:
            errors.append(f"Audit #{r['id']}: Vorgänger-Hash stimmt nicht")
        payload = "|".join([r["prev_hash"], str(r["user_id"] or ""), r["action"], r["entity_type"], str(r["entity_id"] or ""), r["details_json"], r["created_at"]])
        calculated=hashlib.sha256(payload.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(calculated, r["entry_hash"]):
            errors.append(f"Audit #{r['id']}: Eintrag wurde verändert")
        expected_prev=r["entry_hash"]
    return not errors, errors


def audit_rebuild_chain(c) -> None:
    """Rebuild the chain after an explicitly authorized audit-maintenance action."""
    expected_prev="GENESIS"
    rows=c.execute("SELECT id,user_id,action,entity_type,entity_id,details_json,created_at FROM audit_log ORDER BY id").fetchall()
    for r in rows:
        payload="|".join([expected_prev,str(r["user_id"] or ""),r["action"],r["entity_type"],str(r["entity_id"] or ""),r["details_json"],r["created_at"]])
        entry_hash=hashlib.sha256(payload.encode("utf-8")).hexdigest()
        c.execute("UPDATE audit_log SET prev_hash=?,entry_hash=? WHERE id=?",(expected_prev,entry_hash,r["id"]))
        expected_prev=entry_hash


def audit_pick(data: dict, fields: tuple[str, ...] | list[str]) -> dict:
    return {key: data.get(key) for key in fields if key in data}


def audit_changes(before: dict, after: dict, fields: tuple[str, ...] | list[str]) -> dict:
    changes = {}
    for key in fields:
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes[key] = {"old": old, "new": new}
    return changes


def recurring_snapshot(c, recurring_id: int) -> dict:
    r = c.execute("""SELECT r.*,a.name account_name,cat.name category_name
                     FROM recurring r
                     LEFT JOIN accounts a ON a.id=r.account_id
                     LEFT JOIN categories cat ON cat.id=r.category_id
                     WHERE r.id=?""", (recurring_id,)).fetchone()
    return dict(r) if r else {}


def normalize_iban(value: str | None) -> str | None:
    if value is None:
        return None
    value = "".join(value.upper().split())
    return value or None


def clean_text(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:max_len] if value else None


def remember_payee(c, payee: str | None) -> None:
    name = clean_text(payee, 200)
    if not name:
        return
    ts = iso(utcnow())
    c.execute("""INSERT INTO payee_presets(name,usage_count,created_at,last_used_at) VALUES(?,1,?,?)
                 ON CONFLICT(name) DO UPDATE SET usage_count=payee_presets.usage_count+1,last_used_at=excluded.last_used_at""",
              (name, ts, ts))


def transfer_snapshot(c, transfer_id: int) -> dict:
    r = c.execute("""SELECT tr.*,fa.name from_account_name,ta.name to_account_name
                     FROM transfers tr JOIN accounts fa ON fa.id=tr.from_account_id
                     JOIN accounts ta ON ta.id=tr.to_account_id WHERE tr.id=?""", (transfer_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Transfer nicht gefunden")
    return dict(r)


def client_key(request: Request, username: str) -> str:
    ip = client_ip(request)
    return hashlib.sha256(f"{ip}|{username.casefold()}".encode()).hexdigest()


def login_allowed(key: str) -> int:
    now = utcnow()
    with _login_lock:
        blocked = _login_blocked_until.get(key)
        if blocked and blocked > now:
            return max(1, int((blocked - now).total_seconds()))
        dq = _login_failures[key]
        cutoff = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
        while dq and dq[0] < cutoff:
            dq.popleft()
        return 0


def login_failed(key: str) -> None:
    now = utcnow()
    with _login_lock:
        dq = _login_failures[key]
        dq.append(now)
        cutoff = now - timedelta(seconds=LOGIN_WINDOW_SECONDS)
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= LOGIN_MAX_FAILURES:
            _login_blocked_until[key] = now + timedelta(seconds=LOGIN_BLOCK_SECONDS)
            dq.clear()


def login_succeeded(key: str) -> None:
    with _login_lock:
        _login_failures.pop(key, None)
        _login_blocked_until.pop(key, None)


def request_is_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    if TRUST_PROXY_HEADERS:
        proto=request.headers.get("x-forwarded-proto","").split(",",1)[0].strip().lower()
        return proto == "https"
    return False

def validate_new_password(password: str) -> None:
    minimum=14 if PUBLIC_MODE else 10
    if len(password) < minimum:
        raise HTTPException(400,f"Passwort muss mindestens {minimum} Zeichen lang sein")

def same_origin_or_no_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    host = request.headers.get("host", "")
    if origin.rstrip("/").split("://", 1)[-1] != host:
        raise HTTPException(403, "Ungültiger Origin")


def setting_value(c, key: str, default: str) -> str:
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def session(request: Request, write: bool = False):
    th,rec=_session_record(request)
    now=utcnow()
    if rec["expires_at"] <= now:
        with _app_session_lock: _app_sessions.pop(th,None)
        raise HTTPException(401,"Sitzung abgelaufen")
    idle_minutes=int(rec.get("autolock_minutes",15))
    idle_expired=not rec.get("trusted") and idle_minutes>0 and rec["last_seen"]+timedelta(minutes=idle_minutes)<=now
    if idle_expired:
        with _app_session_lock: _app_sessions.pop(th,None)
        raise HTTPException(401,"Sitzung gesperrt. Passwort erneut eingeben.")
    data,member,uid=_activate_session_book(rec)
    if write:
        sent=request.headers.get("X-CSRF-Token")
        if not sent or not hmac.compare_digest(sent,rec["csrf"]): raise HTTPException(403,"CSRF-Prüfung fehlgeschlagen")
        if member.get("role","viewer")=="viewer": raise HTTPException(403,"Dieses Haushaltsbuch ist nur lesbar")
        _cache_invalidate_active()
    rec["last_seen"]=now
    try: rec["autolock_minutes"]=int(setting_value(db.db(),"autolock_minutes","15"))
    except Exception: pass
    return (th,uid,rec["csrf"],int(bool(rec.get("trusted"))))

def create_session(username_key: str, private_key, book_id: str, master: str, trusted: bool, response: Response) -> str:
    data=_auth_load_v2();entry=data.get("users",{}).get(username_key)
    if not entry: raise HTTPException(401,"Benutzer nicht gefunden")
    book=data.get("books",{}).get(book_id)
    if not book or username_key not in book.get("members",{}): raise HTTPException(403,"Kein Haushaltsbuch freigegeben")
    db.activate(_book_path(book),master)
    try: c=db.db()
    except Exception: c=db.unlock(master,path=_book_path(book),set_default=False)
    uid=_ensure_book_user(c,entry["username"],entry["password_hash"])
    raw=secrets.token_urlsafe(48);th=token_hash(raw);csrf_token=secrets.token_urlsafe(32);created=utcnow();ttl=timedelta(days=TRUSTED_TTL_DAYS) if trusted else timedelta(minutes=SESSION_TTL_MIN)
    try: autolock=int(setting_value(c,"autolock_minutes","15"))
    except Exception: autolock=15
    rec={"username":entry["username"],"user_key":username_key,"private_key":private_key,"book_id":book_id,"book_master":master,"csrf":csrf_token,"trusted":bool(trusted),"created_at":created,"last_seen":created,"expires_at":created+ttl,"autolock_minutes":autolock}
    with _app_session_lock: _app_sessions[th]=rec
    response.set_cookie(COOKIE_NAME,raw,httponly=True,secure=SECURE_COOKIES,samesite="strict",path="/",max_age=int(ttl.total_seconds()))
    return csrf_token

def delete_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    try:
        if PUBLIC_MODE and ENFORCE_HTTPS and request.url.path != "/healthz" and not request_is_https(request):
            return JSONResponse({"detail":"HTTPS erforderlich"},status_code=426,headers={"Upgrade":"TLS/1.2, HTTP/1.1"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        csp=("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
             "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if PUBLIC_MODE:
            csp += "; upgrade-insecure-requests"
        response.headers["Content-Security-Policy"] = csp
        if request.url.path == "/" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        if PUBLIC_MODE and request_is_https(request):
            hsts="max-age=31536000"
            if HSTS_INCLUDE_SUBDOMAINS: hsts += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = hsts
        return response
    finally:
        db.clear_context()


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=256)
    trusted_device: bool = False


class SetupIn(LoginIn):
    setup_token: str | None = Field(default=None,max_length=256)

class RegisterIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=10, max_length=256)

class UserApprovalIn(BaseModel):
    approved: bool = True

class BookIn(BaseModel):
    name: str = Field(min_length=1,max_length=80)

class BookDeleteIn(BaseModel):
    confirmation: str = Field(min_length=1,max_length=120)

class AuditDeleteIn(BaseModel):
    confirmation: str = Field(min_length=1,max_length=64)

class MembershipIn(BaseModel):
    role: str | None = None
    book_id: str | None = None
    @field_validator("role")
    @classmethod
    def role_ok(cls,v):
        if v is not None and v not in {"owner","editor","viewer"}: raise ValueError("Ungültige Rolle")
        return v

class AdminPasswordResetIn(BaseModel):
    new_password: str = Field(min_length=12,max_length=256)

class AdminUserCreateIn(BaseModel):
    username: str = Field(min_length=1,max_length=64)
    password: str = Field(min_length=12,max_length=256)
    role: str = "editor"
    book_id: str | None = None
    @field_validator("role")
    @classmethod
    def admin_user_role_ok(cls,v):
        if v not in {"owner","editor","viewer"}: raise ValueError("Ungültige Rolle")
        return v

class BulkDeleteIn(BaseModel):
    mode: str = "range"
    from_date: date | None = None
    to_date: date | None = None
    confirmation: str = Field(min_length=1,max_length=64)

    @field_validator("mode")
    @classmethod
    def mode_ok(cls,v):
        if v not in {"all","from","range"}: raise ValueError("Ungültiger Löschbereich")
        return v


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(default="checking", max_length=32)
    iban: str | None = Field(default=None, max_length=34)
    opening_balance: Decimal = Decimal("0.00")
    start_date: date = Field(default_factory=date.today)
    currency: str = Field(default="EUR", min_length=3, max_length=3)

    @field_validator("iban")
    @classmethod
    def iban_normalizer(cls, value):
        return normalize_iban(value)


class SplitIn(BaseModel):
    category_id: int | None = None
    amount: Decimal
    note: str | None = Field(default=None, max_length=300)


class TransactionIn(BaseModel):
    account_id: int
    amount: Decimal
    direction: str | None = None
    booking_date: date
    value_date: date | None = None
    name: str | None = Field(default=None, max_length=160)
    payee: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=1000)
    category_id: int | None = None
    status: str = "executed"
    tags: list[str] = Field(default_factory=list, max_length=30)
    splits: list[SplitIn] = Field(default_factory=list, max_length=50)
    recurring: bool = False
    recurring_frequency: str | None = None
    recurring_interval_count: int = Field(default=1, ge=1, le=1000)
    recurring_until: date | None = None
    recurring_effective_from: date | None = None
    confidence: str = "fixed"
    fixed_cost: bool = False
    remember_payee: bool = False

    @field_validator("confidence")
    @classmethod
    def transaction_confidence_ok(cls, value):
        if value not in {"fixed","likely","estimated"}:
            raise ValueError("Ungültige Prognose-Sicherheit")
        return value

    @field_validator("recurring_frequency")
    @classmethod
    def recurring_frequency_ok(cls, value):
        if value is not None and value not in {"daily", "weekly", "monthly", "yearly"}:
            raise ValueError("Ungültige Wiederholung")
        return value

    @field_validator("direction")
    @classmethod
    def direction_ok(cls, value):
        if value is not None and value not in {"expense", "income"}:
            raise ValueError("Ungültige Buchungsart")
        return value


class PayeePresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0)
    booking_date: date
    name: str = Field(default="Transfer", min_length=1, max_length=160)
    note: str | None = Field(default=None, max_length=1000)
    recurring: bool = False
    recurring_frequency: str | None = None
    recurring_interval_count: int = Field(default=1, ge=1, le=1000)
    recurring_until: date | None = None

    @field_validator("to_account_id")
    @classmethod
    def transfer_accounts_valid(cls, value):
        return value

    @field_validator("recurring_frequency")
    @classmethod
    def transfer_recurring_frequency_ok(cls, value):
        if value is not None and value not in {"daily","weekly","monthly","yearly"}:
            raise ValueError("Ungültige Wiederholung")
        return value


class RecurringIn(BaseModel):
    account_id: int
    category_id: int | None = None
    name: str = Field(min_length=1, max_length=150)
    payee: str | None = Field(default=None, max_length=200)
    amount: Decimal
    next_date: date
    frequency: str = "monthly"
    interval_count: int = Field(default=1, ge=1, le=1000)
    kind: str = "direct_debit"
    max_amount: Decimal | None = None
    active: bool = True
    valid_until: date | None = None
    confidence: str = "fixed"
    fixed_cost: bool = False

    @field_validator("confidence")
    @classmethod
    def confidence_ok(cls, value):
        if value not in {"fixed","likely","estimated"}:
            raise ValueError("Ungültige Prognose-Sicherheit")
        return value

    @field_validator("frequency")
    @classmethod
    def freq_ok(cls, value):
        if value not in {"daily", "weekly", "monthly", "yearly"}:
            raise ValueError("Ungültige Frequenz")
        return value

    @field_validator("kind")
    @classmethod
    def kind_ok(cls, value):
        if value not in {"direct_debit", "standing_order", "income"}:
            raise ValueError("Ungültige Art")
        return value


class RecurringUpdateIn(RecurringIn):
    effective_from: date


class RecurringOverrideIn(BaseModel):
    due_date: date
    amount: Decimal
    note: str | None = Field(default=None, max_length=300)


class BudgetIn(BaseModel):
    category_id: int | None = None
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    amount: Decimal
    strategy: str
    bucket: str = "free"
    note: str | None = Field(default=None, max_length=300)

    @field_validator("strategy")
    @classmethod
    def strategy_ok(cls, value):
        allowed = {"zero_based", "envelope", "50_30_20", "pay_yourself_first", "hybrid"}
        if value not in allowed:
            raise ValueError("Ungültige Budgetstrategie")
        return value

    @field_validator("bucket")
    @classmethod
    def bucket_ok(cls, value):
        if value not in {"free", "needs", "wants", "savings"}:
            raise ValueError("Ungültiger Budgetbereich")
        return value


class BackupIn(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class SettingsIn(BaseModel):
    value: str = Field(max_length=100)



class ReconcileIn(BaseModel):
    actual_balance: Decimal
    checked_at: date = Field(default_factory=date.today)
    note: str | None = Field(default=None, max_length=500)


class ReconcileCorrectionIn(ReconcileIn):
    create_correction: bool = True
    label: str = Field(default="Kontokorrektur", max_length=120)


def reconciliation_suggestions_for(c, account_id: int, actual_cents: int, checked_at: date) -> dict:
    expected = account_balance(c, account_id, checked_at)
    diff = actual_cents - expected
    direction = "income" if diff > 0 else "expense"
    magnitude = abs(diff)
    suggestions=[]
    if magnitude:
        learned=c.execute("""SELECT amount_cents,label,accepted_count,last_used_at FROM reconciliation_learning
                              WHERE account_id=? AND direction=?
                              ORDER BY accepted_count DESC,last_used_at DESC LIMIT 20""",(account_id,direction)).fetchall()
        for r in learned:
            tolerance=max(100,int(magnitude*Decimal('0.05')))
            if abs(int(r["amount_cents"])-magnitude)<=tolerance:
                suggestions.append({"type":"learned","label":r["label"],"amount":euros(magnitude),"confidence":min(0.95,0.55+0.08*int(r["accepted_count"])),"reason":f"Ähnliche bestätigte Korrektur bereits {r['accepted_count']}×"})
        start=(checked_at-timedelta(days=31)).isoformat(); end=(checked_at+timedelta(days=3)).isoformat()
        candidates=c.execute("""SELECT id,booking_date,payee,note,amount,direction FROM transactions
                                WHERE account_id=? AND status<>'cancelled' AND booking_date BETWEEN ? AND ?
                                ORDER BY booking_date DESC LIMIT 200""",(account_id,start,end)).fetchall()
        for r in candidates:
            val=abs(int(r["amount"]))
            if abs(val-magnitude)<=1:
                suggestions.append({"type":"amount_match","transaction_id":r["id"],"label":r["payee"] or r["note"] or "Buchung","date":r["booking_date"],"amount":euros(val),"confidence":0.7,"reason":"Betrag entspricht exakt der Abweichung; auf doppelte/fehlende Buchung prüfen"})
        suggestions.append({"type":"correction","label":"Korrekturbuchung erzeugen","amount":euros(magnitude),"direction":direction,"confidence":1.0,"reason":"Gleicht Soll- und Ist-Kontostand exakt ab"})
    return {"expected":euros(expected),"actual":euros(actual_cents),"difference":euros(diff),"direction":direction if diff else None,"suggestions":suggestions[:10]}


@app.get("/api/accounts/{account_id}/reconcile/suggestions")
def reconcile_suggestions(account_id: int, actual_balance: Decimal, checked_at: date, request: Request):
    session(request)
    return reconciliation_suggestions_for(db.db(),account_id,cents(actual_balance),checked_at)


@app.post("/api/accounts/{account_id}/reconcile")
def reconcile_account(account_id: int, x: ReconcileIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        expected = account_balance(c, account_id, x.checked_at)
        actual = cents(x.actual_balance)
        diff = actual - expected
        c.execute("""INSERT INTO account_reconciliations(account_id,checked_at,expected_balance,actual_balance,difference,note,created_at)
                     VALUES(?,?,?,?,?,?,?)""",
                  (account_id,x.checked_at.isoformat(),expected,actual,diff,x.note,iso(utcnow())))
        audit_append(c,sess[1],"account.reconcile","account",account_id,{"checked_at":x.checked_at.isoformat(),"expected":expected,"actual":actual,"difference":diff})
        result=reconciliation_suggestions_for(c,account_id,actual,x.checked_at)
        return result


@app.post("/api/accounts/{account_id}/reconcile/correction")
def reconcile_correction(account_id: int, x: ReconcileCorrectionIn, request: Request):
    sess=session(request,True)
    with db.transaction() as c:
        account=c.execute("SELECT id,name FROM accounts WHERE id=? AND active=1",(account_id,)).fetchone()
        if not account: raise HTTPException(404,"Konto nicht gefunden")
        expected=account_balance(c,account_id,x.checked_at); actual=cents(x.actual_balance); diff=actual-expected
        if diff==0: return {"ok":True,"created":False,"difference":0.0}
        direction="income" if diff>0 else "expense"
        cat_name="Kontokorrektur Einnahme" if diff>0 else "Kontokorrektur Ausgabe"
        cat=c.execute("SELECT id FROM categories WHERE name=? AND direction=? AND active=1",(cat_name,direction)).fetchone()
        if not cat:
            cur=c.execute("INSERT INTO categories(parent_id,name,direction,active) VALUES(NULL,?,?,1)",(cat_name,direction)); category_id=cur.lastrowid
        else: category_id=cat[0]
        ts=iso(utcnow())
        cur=c.execute("""INSERT INTO transactions(account_id,amount,direction,booking_date,value_date,name,payee,note,category_id,status,external_id,confidence,fixed_cost,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (account_id,diff,direction,x.checked_at.isoformat(),x.checked_at.isoformat(),x.label,x.label,x.note,category_id,"executed","reconcile-"+secrets.token_hex(16),"fixed",0,ts,ts))
        c.execute("""INSERT INTO account_reconciliations(account_id,checked_at,expected_balance,actual_balance,difference,note,created_at)
                     VALUES(?,?,?,?,?,?,?)""",(account_id,x.checked_at.isoformat(),expected,actual,diff,x.note,ts))
        magnitude=abs(diff)
        c.execute("""INSERT INTO reconciliation_learning(account_id,direction,amount_cents,label,accepted_count,last_used_at)
                     VALUES(?,?,?,?,1,?)
                     ON CONFLICT(account_id,direction,amount_cents,label) DO UPDATE SET accepted_count=accepted_count+1,last_used_at=excluded.last_used_at""",
                  (account_id,direction,magnitude,x.label,ts))
        audit_append(c,sess[1],"account.reconcile_correction","account",account_id,{"transaction_id":cur.lastrowid,"difference":diff,"checked_at":x.checked_at.isoformat()})
        return {"ok":True,"created":True,"transaction_id":cur.lastrowid,"difference":euros(diff),"new_balance":euros(actual)}


@app.get("/api/accounts/{account_id}/reconciliations")
def account_reconciliations(account_id: int, request: Request):
    session(request)
    rows=db.db().execute("""SELECT id,checked_at,expected_balance,actual_balance,difference,note
                            FROM account_reconciliations WHERE account_id=? ORDER BY checked_at DESC,id DESC LIMIT 50""",(account_id,)).fetchall()
    return [{**dict(r),"expected_balance":euros(r["expected_balance"]),"actual_balance":euros(r["actual_balance"]),"difference":euros(r["difference"])} for r in rows]


def detect_attachment_type(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if b"\x00" not in data[:8192]:
        try:
            data[:8192].decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    return None


@app.post("/api/transactions/{tx_id}/attachments")
async def attachment_upload(tx_id: int, request: Request, file: UploadFile = File(...)):
    sess=session(request, True)
    data=await file.read(MAX_ATTACHMENT_BYTES+1)
    if len(data)>MAX_ATTACHMENT_BYTES:
        raise HTTPException(413,f"Beleg zu groß. Maximum: {MAX_ATTACHMENT_BYTES//1024//1024} MB")
    detected=detect_attachment_type(data)
    if not detected:
        raise HTTPException(400,"Dateiinhalt ist kein erlaubtes PDF/Bild/Textformat")
    declared=(file.content_type or "").lower()
    if declared and declared not in {detected,"application/octet-stream"}:
        raise HTTPException(400,"Dateiendung/Content-Type passt nicht zum tatsächlichen Dateiinhalt")
    with db.transaction() as c:
        if not c.execute("SELECT 1 FROM transactions WHERE id=?",(tx_id,)).fetchone():
            raise HTTPException(404,"Buchung nicht gefunden")
        count=c.execute("SELECT COUNT(*) FROM attachments WHERE transaction_id=?",(tx_id,)).fetchone()[0]
        if count>=MAX_ATTACHMENTS_PER_TX:
            raise HTTPException(409,f"Maximal {MAX_ATTACHMENTS_PER_TX} Belege pro Buchung")
        used=int(c.execute("SELECT COALESCE(SUM(size),0) FROM attachments").fetchone()[0] or 0)
        if used+len(data)>MAX_ATTACHMENT_TOTAL_BYTES:
            raise HTTPException(507,"Belegspeicher-Limit erreicht. Alte Belege löschen oder Limit bewusst erhöhen.")
        filename=Path(file.filename or "beleg").name[:180]
        cur=c.execute("""INSERT INTO attachments(transaction_id,filename,content_type,data,size,created_at) VALUES(?,?,?,?,?,?)""",
                      (tx_id,filename,detected,data,len(data),iso(utcnow())))
        audit_append(c,sess[1],"attachment.create","transaction",tx_id,{"attachment_id":cur.lastrowid,"filename":filename,"size":len(data),"content_type":detected})
        return {"id":cur.lastrowid,"filename":filename,"size":len(data),"content_type":detected,
                "total_used":used+len(data),"total_limit":MAX_ATTACHMENT_TOTAL_BYTES}

@app.get("/api/transactions/{tx_id}/attachments")
def attachments_list(tx_id: int, request: Request):
    session(request)
    rows=db.db().execute("SELECT id,filename,content_type,size,created_at FROM attachments WHERE transaction_id=? ORDER BY id",(tx_id,)).fetchall()
    return [dict(r) for r in rows]

@app.get("/api/attachments/{attachment_id}")
def attachment_download(attachment_id: int, request: Request):
    session(request)
    r=db.db().execute("SELECT filename,content_type,data FROM attachments WHERE id=?",(attachment_id,)).fetchone()
    if not r: raise HTTPException(404,"Beleg nicht gefunden")
    return Response(content=bytes(r["data"]),media_type=r["content_type"] or "application/octet-stream",
                    headers={"Content-Disposition":f'attachment; filename="{Path(r["filename"]).name}"'})

@app.delete("/api/attachments/{attachment_id}")
def attachment_delete(attachment_id: int, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        row=c.execute("SELECT transaction_id,filename,size FROM attachments WHERE id=?",(attachment_id,)).fetchone()
        if not row: raise HTTPException(404,"Beleg nicht gefunden")
        c.execute("DELETE FROM attachments WHERE id=?",(attachment_id,))
        audit_append(c,sess[1],"attachment.delete","transaction",row["transaction_id"],{"attachment_id":attachment_id,"filename":row["filename"],"size":row["size"]})
    return {"ok":True}

@app.get("/api/history")
def documentation_history(request: Request, limit: int = 100):
    session(request)
    c=db.db()
    txh=c.execute("""SELECT h.id,h.transaction_id,h.action,h.changed_at,t.name,t.payee,t.booking_date
                     FROM transaction_history h LEFT JOIN transactions t ON t.id=h.transaction_id
                     ORDER BY h.changed_at DESC LIMIT ?""",(min(max(limit,1),500),)).fetchall()
    rec=c.execute("""SELECT * FROM recurring ORDER BY created_at DESC LIMIT ?""",(min(max(limit,1),500),)).fetchall()
    return {"transactions":[{**dict(r)} for r in txh],
            "recurring":[{**dict(r),"amount":euros(recurring_signed_amount(c,r))} for r in rec]}

def _scenario_include(confidence: str, amount: int, scenario: str) -> bool:
    if scenario=="expected": return True
    if scenario=="conservative":
        return amount < 0 or confidence=="fixed"
    if scenario=="optimistic":
        return amount > 0 or confidence=="fixed"
    return True

def _long_forecast(c, months: int, scenario: str):
    today=date.today()
    end=add_months(date(today.year,today.month,1),months)-timedelta(days=1)
    account_ids=[r["id"] for r in c.execute("SELECT id FROM accounts WHERE active=1 AND start_date<=?",(end.isoformat(),)).fetchall()]
    running=sum(projected_account_balance(c,aid,today) for aid in account_ids)
    events=defaultdict(int)
    for r in c.execute("""SELECT booking_date,CASE WHEN direction='expense' THEN -ABS(amount) WHEN direction='income' THEN ABS(amount) ELSE amount END amount,
                                 COALESCE(confidence,'fixed') confidence
                          FROM transactions WHERE status<>'cancelled' AND booking_date>? AND booking_date<=?""",(today.isoformat(),end.isoformat())).fetchall():
        amount=int(r["amount"])
        if _scenario_include(r["confidence"],amount,scenario):
            events[date.fromisoformat(r["booking_date"])]+=amount
    conf={int(r["id"]):(r["confidence"] if "confidence" in r.keys() else "fixed") for r in c.execute("SELECT * FROM recurring").fetchall()}
    for ev in recurring_events(c,None,today+timedelta(days=1),end):
        amount=int(ev["amount"]); confidence=conf.get(int(ev["recurring_id"]),"fixed")
        if _scenario_include(confidence,amount,scenario): events[ev["date"]]+=amount
    out=[]; d=today
    while d<=end:
        if d in events: running+=events[d]
        nextd=d+timedelta(days=1)
        if nextd.month!=d.month or d==end:
            out.append({"month":d.strftime("%Y-%m"),"end_balance":euros(running)})
        d=nextd
    return out

@app.get("/api/planning/overview")
def planning_overview(request: Request, month: str | None = None):
    session(request)
    cache_key=(month or date.today().strftime("%Y-%m"),date.today().isoformat())
    cached=_cache_get("planning_overview",*cache_key,ttl=25)
    if cached is not None:
        return cached
    c=db.db(); today=date.today(); start,end=month_bounds(month)
    selected=start.strftime("%Y-%m")
    # Month plan/actual by category semantics.
    actual={"income":0,"expense":0,"savings":0}
    for r in c.execute("""SELECT ABS(t.amount) amount,COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) typ
                          FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
                          WHERE t.status='executed' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",(start.isoformat(),min(end,today).isoformat())).fetchall():
        actual[r["typ"] if r["typ"] in actual else "expense"]+=int(r["amount"])
    planned={"income":0,"expense":0,"savings":0}
    for r in planned_month_category_totals(c,start,end).values():
        planned[r["type"] if r["type"] in planned else "expense"]+=int(r["amount"])
    # Fixed-cost ratio is a planning metric: use planned recurring amounts, not actual deviations.
    fixed=planned_fixed_costs(c,start,end)
    income=planned["income"]
    free=max(0,income-planned["expense"]-planned["savings"])
    fixed_ratio=(fixed/income*100) if income else 0
    # Liquidity warning: first negative day per account in selected/future horizon.
    warnings=[]
    horizon_end=add_months(date(today.year,today.month,1),12)-timedelta(days=1)
    # Liquiditätswarnungen sind eine Vorwärtsrechnung ab dem heutigen
    # Kontostand. Bereits angespartes Guthaben ist damit Teil der Basis.
    # Historische, nicht materialisierte Serientermine werden nicht jeden
    # zukünftigen Tag erneut aus der kompletten Vergangenheit rekonstruiert.
    for a in c.execute("SELECT id,name,start_date FROM accounts WHERE active=1").fetchall():
        account_start=date.fromisoformat(a["start_date"])
        if account_start>horizon_end:
            continue
        sim_start=max(today,account_start)
        running=projected_account_balance(c,a["id"],sim_start)

        # Bekannte künftige Einzelbuchungen und noch offene Serien ab morgen.
        events=defaultdict(int)
        for r in c.execute("""SELECT booking_date,
                                     CASE WHEN direction='expense' THEN -ABS(amount)
                                          WHEN direction='income' THEN ABS(amount)
                                          ELSE amount END amount
                              FROM transactions
                              WHERE account_id=? AND status<>'cancelled'
                                AND booking_date>? AND booking_date<=?""",
                           (a["id"],sim_start.isoformat(),horizon_end.isoformat())).fetchall():
            events[date.fromisoformat(r["booking_date"])]+=int(r["amount"])
        for ev in recurring_events(c,a["id"],sim_start+timedelta(days=1),horizon_end):
            events[ev["date"]]+=int(ev["amount"])

        # Zukünftige manuelle Monatsanfangs-Korrekturen sind harte Baselines
        # und werden am jeweiligen 1. vor den Bewegungen dieses Tages gesetzt.
        overrides={
            date.fromisoformat(r["month"]+"-01"):int(r["opening_balance"])
            for r in c.execute("""SELECT month,opening_balance
                                  FROM account_month_overrides
                                  WHERE account_id=? AND month>? AND month<=?""",
                               (a["id"],sim_start.strftime("%Y-%m"),horizon_end.strftime("%Y-%m"))).fetchall()
        }

        if running<0:
            warnings.append({"account":a["name"],"date":sim_start.isoformat(),"balance":euros(running)})
            continue
        d=sim_start+timedelta(days=1)
        while d<=horizon_end:
            if d in overrides:
                running=overrides[d]
            running+=events.get(d,0)
            if running<0:
                warnings.append({"account":a["name"],"date":d.isoformat(),"balance":euros(running)})
                break
            d+=timedelta(days=1)
    # Historical comparison.
    prev_start=date(start.year-1,start.month,1); prev_end=month_bounds(prev_start.strftime("%Y-%m"))[1]
    def month_totals(ms,me):
        vals={"income":0,"expense":0,"savings":0}
        for r in c.execute("""SELECT ABS(t.amount) amount,COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) typ
                              FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
                              WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",(ms.isoformat(),me.isoformat())).fetchall():
            vals[r["typ"] if r["typ"] in vals else "expense"]+=int(r["amount"])
        return vals
    prev=month_totals(prev_start,prev_end)
    history=[]
    cur=start
    for n in (6,12):
        vals=[]
        m=add_months(start,-n)
        for _ in range(n):
            me=month_bounds(m.strftime("%Y-%m"))[1]; vals.append(month_totals(m,me)); m=add_months(m,1)
        history.append({"months":n,"income":euros(sum(v["income"] for v in vals)//n),"expense":euros(sum(v["expense"] for v in vals)//n),"savings":euros(sum(v["savings"] for v in vals)//n)})
    # Forecast snapshots are meaningful only if captured no later than the target month end.
    # A past month opened for the first time today must never manufacture a "historical forecast" retroactively.
    projected_end=sum(projected_account_balance(c,a["id"],end) for a in c.execute("SELECT id FROM accounts WHERE active=1 AND start_date<=?",(end.isoformat(),)).fetchall())
    if end >= today:
        with db.transaction() as cw:
            cw.execute("""INSERT OR IGNORE INTO forecast_snapshots(month,captured_on,projected_end_balance) VALUES(?,?,?)""",(selected,today.isoformat(),projected_end))
    first=c.execute("""SELECT captured_on,projected_end_balance FROM forecast_snapshots
                       WHERE month=? AND captured_on<=? ORDER BY captured_on LIMIT 1""",(selected,end.isoformat())).fetchone()
    deviation=None
    if end<today and first:
        actual_end=sum(account_balance(c,a["id"],end) for a in c.execute("SELECT id FROM accounts WHERE active=1 AND start_date<=?",(end.isoformat(),)).fetchall())
        deviation={"forecast":euros(first["projected_end_balance"]),"actual":euros(actual_end),"difference":euros(actual_end-first["projected_end_balance"]),"captured_on":first["captured_on"]}
    consumption_cashflow = income - planned["expense"]
    total_cashflow = income - planned["expense"] - planned["savings"]
    cashflow_warning = {
        "consumption_negative": consumption_cashflow < 0,
        "total_negative": total_cashflow < 0,
        "consumption_cashflow": euros(consumption_cashflow),
        "total_cashflow": euros(total_cashflow),
        "consumption_shortfall": euros(abs(consumption_cashflow)) if consumption_cashflow < 0 else 0.0,
        "total_shortfall": euros(abs(total_cashflow)) if total_cashflow < 0 else 0.0,
    }

    result={"month":selected,
            "plan_actual":{"planned":{k:euros(v) for k,v in planned.items()},"actual":{k:euros(v) for k,v in actual.items()}},
            "fixed_costs":euros(fixed),"fixed_cost_ratio_pct":round(fixed_ratio,1),"free_money":euros(free),
            "liquidity_warnings":warnings,"cashflow_warning":cashflow_warning,"previous_year":{k:euros(v) for k,v in prev.items()},"averages":history,
            "forecast":{"3":_long_forecast(c,3,"expected"),"6":_long_forecast(c,6,"expected"),"12":_long_forecast(c,12,"expected"),
                        "conservative":_long_forecast(c,12,"conservative"),"optimistic":_long_forecast(c,12,"optimistic")},
            "forecast_deviation":deviation}
    return _cache_set("planning_overview",result,*cache_key,ttl=25)

@app.get("/")
def index():
    return FileResponse("/app/static/index.html")


@app.get("/healthz")
def health():
    return {"status":"ok"}


@app.get("/api/status")
def status():
    initialized=AUTH_PATH.exists() or db.is_initialized(db.DB_PATH)
    base={"version":APP_VERSION,"initialized":initialized,"public_mode":PUBLIC_MODE,
          "registration_enabled":ALLOW_SELF_REGISTRATION,
          "setup_token_required":bool(PUBLIC_MODE and not initialized)}
    if not PUBLIC_MODE:
        base.update({"locked":len(_app_sessions)==0,"multi_user_auth":AUTH_PATH.exists(),"multi_book":True})
    return base


@app.post("/api/setup")
def setup(x: SetupIn, request: Request, response: Response):
    same_origin_or_no_origin(request)
    rate_limit(request,"setup",5,600)
    if PUBLIC_MODE:
        if len(PUBLIC_SETUP_TOKEN) < 24:
            raise HTTPException(503,"Public-Setup ist gesperrt: PUBLIC_SETUP_TOKEN mit mindestens 24 Zeichen setzen")
        if not x.setup_token or not hmac.compare_digest(x.setup_token,PUBLIC_SETUP_TOKEN):
            raise HTTPException(403,"Ungültiger Setup-Token")
    validate_new_password(x.password)
    with _setup_lock:
        if AUTH_PATH.exists() or db.is_initialized(db.DB_PATH):
            raise HTTPException(409,"HaushaltPro ist bereits eingerichtet")
        username=x.username.strip(); user_key=username.casefold()
        if not username: raise HTTPException(400,"Ungültiger Benutzername")
        master=secrets.token_urlsafe(48)
        password_hash,public_pem,private_blob=_new_user_crypto(x.password)
        private=_unlock_private(x.password,private_blob)
        try:
            c=db.unlock(master,initialize=True,path=db.DB_PATH,set_default=False)
            _ensure_book_user(c,username,password_hash)
            auth={"version":2,"users":{user_key:{"username":username,"password_hash":password_hash,"public_key":public_pem,"private_key":private_blob,"system_role":"admin","created_at":iso(utcnow()),"last_book_id":"default"}},
                  "books":{"default":{"id":"default","name":"Haushalt","path":str(db.DB_PATH),"created_at":iso(utcnow()),"members":{user_key:{"role":"owner","wrapped_master":_wrap_master(public_pem,master)}}}}}
            _auth_save(auth)
            csrf=create_session(user_key,private,"default",master,x.trusted_device,response)
            return {"ok":True,"csrf":csrf}
        except Exception:
            db.clear_context();AUTH_PATH.unlink(missing_ok=True)
            for suffix in ("","-wal","-shm"): Path(str(db.DB_PATH)+suffix).unlink(missing_ok=True)
            raise

@app.post("/api/register")
def register(x: RegisterIn, request: Request):
    same_origin_or_no_origin(request)
    rate_limit(request,"register",5 if PUBLIC_MODE else 20,600)
    if not ALLOW_SELF_REGISTRATION:
        raise HTTPException(403,"Selbstregistrierung ist deaktiviert. Benutzer werden von einem Eigentümer angelegt.")
    validate_new_password(x.password)
    if not AUTH_PATH.exists(): raise HTTPException(409,"HaushaltPro muss zuerst eingerichtet werden")
    username=x.username.strip();key=username.casefold();data=_auth_load_v2()
    if not username: raise HTTPException(400,"Ungültiger Benutzername")
    if key in data.get("users",{}): raise HTTPException(409,"Benutzername existiert bereits")
    password_hash,public_pem,private_blob=_new_user_crypto(x.password)
    data.setdefault("users",{})[key]={"username":username,"password_hash":password_hash,"public_key":public_pem,"private_key":private_blob,"system_role":"user","created_at":iso(utcnow())}
    _auth_save(data)
    return {"ok":True,"message":"Benutzer angelegt. Ein Eigentümer muss ihn einem Haushaltsbuch zuordnen."}

@app.post("/api/login")
def login(x: LoginIn, request: Request, response: Response):
    same_origin_or_no_origin(request)
    if PUBLIC_MODE: rate_limit(request,"login",30,300)
    limiter_key=client_key(request,x.username);retry=login_allowed(limiter_key)
    if retry:
        response.headers["Retry-After"]=str(retry);raise HTTPException(429,"Zu viele fehlgeschlagene Anmeldeversuche")
    username=x.username.strip();user_key=username.casefold()
    try:
        if not AUTH_PATH.exists():
            # Very old installation: unlock once with the historical password and migrate to v2 auth.
            c=db.unlock(x.password,path=db.DB_PATH,set_default=False)
            row=c.execute("SELECT id,username,password_hash FROM users WHERE username=?",(username,)).fetchone()
            if not row: raise VerifyMismatchError("user")
            ph.verify(row[2],x.password)
            master=secrets.token_urlsafe(48);db.rekey(master)
            password_hash,public_pem,private_blob=_new_user_crypto(x.password);private=_unlock_private(x.password,private_blob)
            data={"version":2,"users":{user_key:{"username":row[1],"password_hash":password_hash,"public_key":public_pem,"private_key":private_blob,"system_role":"admin","created_at":iso(utcnow()),"last_book_id":"default"}},
                  "books":{"default":{"id":"default","name":"Haushalt","path":str(db.DB_PATH),"created_at":iso(utcnow()),"members":{user_key:{"role":"owner","wrapped_master":_wrap_master(public_pem,master)}}}}}
            _auth_save(data)
        else:
            raw_data=_auth_load();entry=raw_data.get("users",{}).get(user_key)
            if not entry: raise VerifyMismatchError("user")
            ph.verify(entry["password_hash"],x.password)
            private=_unlock_private(x.password,entry["private_key"])
            data=_auth_v2(raw_data);_auth_save(data)
            entry=data["users"][user_key]
        books=_user_books(data,user_key)
        if not books: raise HTTPException(403,"Benutzer ist noch keinem Haushaltsbuch zugeordnet")
        preferred=entry.get("last_book_id")
        book_id=preferred if preferred and any(b["id"]==preferred for b in books) else books[0]["id"]
        master=_unwrap_book_master(data,book_id,user_key,private)
        book=data["books"][book_id];db.activate(_book_path(book),master)
        if not db.is_initialized(_book_path(book)): raise HTTPException(500,"Haushaltsbuch-Datenbank fehlt")
        try: c=db.db()
        except Exception: c=db.unlock(master,path=_book_path(book),set_default=False)
        db.migrate_schema(c);_ensure_book_user(c,entry["username"],entry["password_hash"])
        entry["last_book_id"]=book_id;_auth_save(data)
        login_succeeded(limiter_key);csrf=create_session(user_key,private,book_id,master,x.trusted_device,response)
        return {"ok":True,"csrf":csrf,"book_id":book_id}
    except HTTPException:
        login_failed(limiter_key);raise
    except Exception:
        login_failed(limiter_key);raise HTTPException(401,"Benutzername oder Passwort falsch")

@app.post("/api/logout")
def logout(request: Request,response: Response):
    raw=request.cookies.get(COOKIE_NAME)
    if raw:
        with _app_session_lock:_app_sessions.pop(token_hash(raw),None)
    delete_cookie(response);db.clear_context();return {"ok":True}

@app.get("/api/me")
def me(request: Request):
    s=session(request);_,rec=_session_record(request);data=_auth_load_v2();entry=data["users"][rec["user_key"]];book=data["books"][rec["book_id"]];member=book["members"][rec["user_key"]]
    return {"username":entry["username"],"system_role":entry.get("system_role","user"),"role":member.get("role","viewer"),"permissions":_permission_set(member.get("role","viewer")),
            "book":{"id":rec["book_id"],"name":book.get("name",rec["book_id"])},"books":_user_books(data,rec["user_key"]),"csrf":s[2],"trusted_device":bool(s[3]),"autolock_minutes":int(setting_value(db.db(),"autolock_minutes","15")),"must_change_password":bool(entry.get("must_change_password",False))}


def _database_file_stats(path: Path) -> dict:
    main_bytes=path.stat().st_size if path.exists() else 0
    wal=Path(str(path)+"-wal"); shm=Path(str(path)+"-shm")
    wal_bytes=wal.stat().st_size if wal.exists() else 0
    shm_bytes=shm.stat().st_size if shm.exists() else 0
    return {"database_file_bytes":main_bytes,"wal_bytes":wal_bytes,"shm_bytes":shm_bytes,
            "size_bytes":main_bytes+wal_bytes+shm_bytes}

@app.get("/api/books")
def books_list(request: Request):
    session(request);_,rec=_session_record(request);data=_auth_load_v2();rows=[]
    for b in _user_books(data,rec["user_key"]):
        path=Path(b["path"]);stats=_database_file_stats(path);b.update(stats);b["active"]=b["id"]==rec["book_id"]
        b["transactions"]=None;b["attachments_bytes"]=None
        try:
            if b["active"]:
                bc=db.db(); close_after=False
            elif db._conn is None:
                master=_unwrap_book_master(data,b["id"],rec["user_key"],rec["private_key"])
                bc=db.connect(master,path); close_after=True
            else:
                bc=None; close_after=False
            if bc is not None:
                b["transactions"]=int(bc.execute("SELECT COUNT(*) FROM transactions").fetchone()[0])
                b["attachments_bytes"]=int(bc.execute("SELECT COALESCE(SUM(size),0) FROM attachments").fetchone()[0])
            if close_after: bc.close()
        except Exception:
            pass
        rows.append(b)
    return rows

def _create_book_record(data: dict, owner_key: str, name: str, editor_key: str | None = None) -> dict:
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


@app.post("/api/books/{book_id}/switch")
def book_switch(book_id: str,request: Request):
    s=session(request);sent=request.headers.get("X-CSRF-Token")
    if not sent or not hmac.compare_digest(sent,s[2]): raise HTTPException(403,"CSRF-Prüfung fehlgeschlagen")
    th,rec=_session_record(request);data=_auth_load_v2();master=_unwrap_book_master(data,book_id,rec["user_key"],rec["private_key"]);book=data["books"][book_id]
    db.activate(_book_path(book),master);c=db.unlock(master,path=_book_path(book),set_default=False);entry=data["users"][rec["user_key"]];_ensure_book_user(c,entry["username"],entry["password_hash"])
    rec["book_id"]=book_id;rec["book_master"]=master;entry["last_book_id"]=book_id;_auth_save(data)
    return {"ok":True,"book":{"id":book_id,"name":book.get("name",book_id)}}


def _can_manage_book(data: dict, book_id: str, user_key: str) -> bool:
    user=data.get("users",{}).get(user_key,{})
    member=data.get("books",{}).get(book_id,{}).get("members",{}).get(user_key,{})
    return user.get("system_role")=="admin" or member.get("role")=="owner"

@app.put("/api/books/{book_id}")
def book_rename(book_id: str,x: BookIn,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();book=data.get("books",{}).get(book_id)
    if not book: raise HTTPException(404,"Haushaltsbuch nicht gefunden")
    if not _can_manage_book(data,book_id,rec["user_key"]): raise HTTPException(403,"Nur Eigentümer dürfen dieses Haushaltsbuch verwalten")
    old=book.get("name",book_id);new=clean_text(x.name,80) or old;book["name"]=new;_auth_save(data)
    c=db.db();audit_append(c,sess[1],"book.rename","book",book_id,{"changes":{"name":{"old":old,"new":new}},"current":{"name":new}});c.commit()
    return {"ok":True,"id":book_id,"name":new}

@app.delete("/api/books/{book_id}")
def book_delete(book_id: str,x: BookDeleteIn,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();book=data.get("books",{}).get(book_id)
    if not book: raise HTTPException(404,"Haushaltsbuch nicht gefunden")
    if not _can_manage_book(data,book_id,rec["user_key"]): raise HTTPException(403,"Nur Eigentümer dürfen dieses Haushaltsbuch löschen")
    if rec["book_id"]==book_id: raise HTTPException(400,"Aktives Haushaltsbuch zuerst wechseln")
    if len(data.get("books",{}))<=1: raise HTTPException(400,"Das letzte Haushaltsbuch kann nicht gelöscht werden")
    expected=(book.get("name") or book_id).strip()
    if x.confirmation.strip()!=expected: raise HTTPException(400,f"Zur Bestätigung exakt {expected} eingeben")
    path=_book_path(book);members=list(book.get("members",{}).keys());size=path.stat().st_size if path.exists() else 0
    del data["books"][book_id]
    for key,u in data.get("users",{}).items():
        if u.get("last_book_id")==book_id:
            alternatives=[b["id"] for b in _user_books(data,key)]
            u["last_book_id"]=alternatives[0] if alternatives else None
    _auth_save(data)
    with _app_session_lock:
        for token,r in list(_app_sessions.items()):
            if r.get("book_id")==book_id:_app_sessions.pop(token,None)
    db.close_all_connections()
    for suffix in ("","-wal","-shm"):
        Path(str(path)+suffix).unlink(missing_ok=True)
    shutil.rmtree(BACKUP_DIR/book_id,ignore_errors=True)
    current=data["books"][rec["book_id"]];db.activate(_book_path(current),rec["book_master"]);c=db.db()
    audit_append(c,sess[1],"book.delete","book",book_id,{"name":expected,"size_bytes":size,"member_count":len(members)});c.commit()
    return {"ok":True,"deleted":book_id,"name":expected}


def _managed_book_master(data: dict, rec: dict, book_id: str) -> tuple[dict,str]:
    book=data.get("books",{}).get(book_id)
    if not book: raise HTTPException(404,"Haushaltsbuch nicht gefunden")
    if not _can_manage_book(data,book_id,rec["user_key"]):
        raise HTTPException(403,"Keine Verwaltungsrechte für dieses Haushaltsbuch")
    actor_member=book.get("members",{}).get(rec["user_key"])
    if not actor_member:
        raise HTTPException(403,"Zum Freigeben muss der Verwalter selbst Zugriff auf dieses Haushaltsbuch haben")
    if book_id==rec["book_id"]:
        master=rec["book_master"]
    else:
        master=_unwrap_master(rec["private_key"],actor_member["wrapped_master"])
    return book,master

@app.post("/api/users")
def admin_user_create(x: AdminUserCreateIn,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2()
    target_book_id=x.book_id or rec["book_id"];book,master=_managed_book_master(data,rec,target_book_id)
    username=x.username.strip();user_key=username.casefold()
    if not username: raise HTTPException(400,"Ungültiger Benutzername")
    if user_key in data.get("users",{}): raise HTTPException(409,"Benutzername existiert bereits")
    password_hash,public_pem,private_blob=_new_user_crypto(x.password)
    data.setdefault("users",{})[user_key]={"username":username,"password_hash":password_hash,"public_key":public_pem,"private_key":private_blob,"system_role":"user","must_change_password":True,"created_at":iso(utcnow()),"last_book_id":target_book_id}
    book.setdefault("members",{})[user_key]={"role":x.role,"wrapped_master":_wrap_master(public_pem,master)}
    _auth_save(data)
    if target_book_id==rec["book_id"]:
        c=db.db(); actor_uid=sess[1]; close_after=False
    else:
        c=db.connect(master,_book_path(book)); actor=_auth_load_v2()["users"][rec["user_key"]];actor_uid=_ensure_book_user(c,actor["username"],actor["password_hash"]);close_after=True
    _ensure_book_user(c,username,password_hash);audit_append(c,actor_uid,"user.create","user",username,{"role":x.role,"book":book.get("name"),"book_id":target_book_id});c.commit()
    if close_after:c.close()
    return {"ok":True,"username":username,"role":x.role,"book_id":target_book_id}

@app.get("/api/users")
def users_list(request: Request):
    session(request);_,rec=_session_record(request);data=_auth_load_v2()
    manageable=[]
    for bid,b in data.get("books",{}).items():
        if _can_manage_book(data,bid,rec["user_key"]) and rec["user_key"] in b.get("members",{}):
            manageable.append({"id":bid,"name":b.get("name",bid),"active":bid==rec["book_id"]})
    if not manageable: raise HTTPException(403,"Keine Benutzerverwaltung verfügbar")
    out=[]
    current=data["books"][rec["book_id"]]
    for key,u in sorted(data.get("users",{}).items(),key=lambda kv:kv[1]["username"].casefold()):
        memberships={bid:b.get("members",{}).get(key,{}).get("role") for bid,b in data.get("books",{}).items() if key in b.get("members",{})}
        cur=current.get("members",{}).get(key)
        out.append({"username":u["username"],"system_role":u.get("system_role","user"),"role":cur.get("role") if cur else None,
                    "approved":bool(cur),"book_count":len(memberships),"memberships":memberships,"manageable_books":manageable})
    return out

@app.put("/api/users/{username}/membership")
def user_membership(username: str,x: MembershipIn,request: Request):
    sess=session(request,True);_,rec=_session_record(request);data=_auth_load_v2();target_key=username.casefold();target=data.get("users",{}).get(target_key)
    if not target: raise HTTPException(404,"Benutzer nicht gefunden")
    target_book_id=x.book_id or rec["book_id"];book,master=_managed_book_master(data,rec,target_book_id);members=book.setdefault("members",{})
    existing=members.get(target_key)
    if target_key==rec["user_key"] and x.role is None and target_book_id==rec["book_id"]:
        raise HTTPException(400,"Eigenen Zugriff auf das aktive Haushaltsbuch nicht entfernen")
    if existing and existing.get("role")=="owner" and x.role!="owner":
        owners=[k for k,v in members.items() if v.get("role")=="owner"]
        if len(owners)<=1: raise HTTPException(409,"Der letzte Eigentümer dieses Haushaltsbuchs kann nicht entfernt oder herabgestuft werden")
    if x.role is None:
        members.pop(target_key,None)
        with _app_session_lock:
            for token,r in list(_app_sessions.items()):
                if r["user_key"]==target_key and r["book_id"]==target_book_id:_app_sessions.pop(token,None)
    else:
        members[target_key]={"role":x.role,"wrapped_master":_wrap_master(target["public_key"],master)}
    _auth_save(data)
    if target_book_id==rec["book_id"]:
        c=db.db();actor_uid=sess[1];close_after=False
    else:
        c=db.connect(master,_book_path(book));actor=data["users"][rec["user_key"]];actor_uid=_ensure_book_user(c,actor["username"],actor["password_hash"]);close_after=True
    if x.role is not None:_ensure_book_user(c,target["username"],target["password_hash"])
    audit_append(c,actor_uid,"user.membership","user",target["username"],{"role":x.role,"book":book.get("name"),"book_id":target_book_id});c.commit()
    if close_after:c.close()
    return {"ok":True}

# Backward-compatible approval maps to editor access in the current book.
@app.put("/api/users/{username}/approval")
def user_approval(username: str,x: UserApprovalIn,request: Request):
    return user_membership(username,MembershipIn(role="editor" if x.approved else None),request)

@app.post("/api/users/{username}/reset-password")
def admin_reset_password(username: str,x: AdminPasswordResetIn,request: Request):
    sess=session(request,True);rec=require_system_admin(request);data=_auth_load_v2();target_key=username.casefold();target=data.get("users",{}).get(target_key)
    if not target: raise HTTPException(404,"Benutzer nicht gefunden")
    new_hash,new_public,new_private_blob=_new_user_crypto(x.new_password)
    # Re-wrap every household key. The administrator must also have access to that household.
    for bid,book in data.get("books",{}).items():
        tm=book.get("members",{}).get(target_key)
        if not tm: continue
        adminm=book.get("members",{}).get(rec["user_key"])
        if not adminm: raise HTTPException(409,f"Passwort-Reset nicht möglich: Administrator hat keinen Zugriff auf {book.get('name',bid)}")
        master=_unwrap_master(rec["private_key"],adminm["wrapped_master"])
        tm["wrapped_master"]=_wrap_master(new_public,master)
        try:
            db.activate(_book_path(book),master);c=db.db();row=c.execute("SELECT id FROM users WHERE username=?",(target["username"],)).fetchone()
            if row:c.execute("UPDATE users SET password_hash=? WHERE id=?",(new_hash,row[0]));c.commit()
        except Exception: pass
    target.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob,"must_change_password":True})
    _auth_save(data)
    with _app_session_lock:
        for token,r in list(_app_sessions.items()):
            if r["user_key"]==target_key:_app_sessions.pop(token,None)
    # Return to current household for audit.
    db.activate(_book_path(data["books"][rec["book_id"]]),rec["book_master"]);c=db.db();audit_append(c,sess[1],"user.password_reset","user",target["username"],{});c.commit()
    return {"ok":True}

@app.delete("/api/users/{username}")
def admin_user_delete(username: str,request: Request):
    rec=require_system_admin(request);data=_auth_load_v2();target_key=username.casefold();target=data.get("users",{}).get(target_key)
    if not target: raise HTTPException(404,"Benutzer nicht gefunden")
    if target_key==rec["user_key"]: raise HTTPException(400,"Eigenen Benutzer nicht löschen")
    if target.get("system_role")=="admin": raise HTTPException(400,"System-Administrator kann nicht gelöscht werden")
    blockers=[]
    for bid,book in data.get("books",{}).items():
        tm=book.get("members",{}).get(target_key)
        if not tm: continue
        owners=[k for k,m in book.get("members",{}).items() if m.get("role")=="owner"]
        if tm.get("role")=="owner" and len(owners)<=1: blockers.append(book.get("name",bid))
    if blockers: raise HTTPException(409,"Benutzer ist alleiniger Eigentümer: "+", ".join(blockers))
    affected=[];targets=[]
    for bid,book in data.get("books",{}).items():
        tm=book.get("members",{}).get(target_key)
        if not tm: continue
        adminm=book.get("members",{}).get(rec["user_key"])
        if not adminm: raise HTTPException(409,f"Benutzerlöschung nicht möglich: Administrator hat keinen Zugriff auf {book.get('name',bid)}")
        master=_unwrap_master(rec["private_key"],adminm["wrapped_master"]);targets.append((bid,book,master))
    for bid,book,master in targets:
        db.activate(_book_path(book),master);c=db.db()
        row=c.execute("SELECT id FROM users WHERE username=?",(target["username"],)).fetchone()
        if row:
            uid=int(row[0]);audit_rows=c.execute("SELECT id,details_json FROM audit_log WHERE user_id=?",(uid,)).fetchall()
            for ar in audit_rows:
                try:d=json.loads(ar["details_json"] or "{}")
                except Exception:d={}
                d.setdefault("_actor_username",target["username"]);c.execute("UPDATE audit_log SET details_json=? WHERE id=?",(json.dumps(d,ensure_ascii=False,separators=(",",":"),sort_keys=True),ar["id"]))
            c.execute("DELETE FROM users WHERE id=?",(uid,));audit_rebuild_chain(c)
        admin_local=_ensure_book_user(c,data["users"][rec["user_key"]]["username"],data["users"][rec["user_key"]]["password_hash"])
        audit_append(c,admin_local,"user.delete","user",target["username"],{"username":target["username"]});c.commit();affected.append(book.get("name",bid))
        book.get("members",{}).pop(target_key,None)
    data.get("users",{}).pop(target_key,None);_auth_save(data)
    with _app_session_lock:
        for token,r in list(_app_sessions.items()):
            if r.get("user_key")==target_key:_app_sessions.pop(token,None)
    current=data["books"][rec["book_id"]];db.activate(_book_path(current),rec["book_master"])
    return {"ok":True,"username":target["username"],"books":affected}

@app.post("/api/password")
def change_password(x: PasswordChangeIn,request: Request):
    sess=require_csrf_session(request);th,rec=_session_record(request);data=_auth_load_v2();entry=data["users"][rec["user_key"]]
    validate_new_password(x.new_password)
    try: ph.verify(entry["password_hash"],x.current_password)
    except VerifyMismatchError: raise HTTPException(401,"Aktuelles Passwort ist falsch")
    old_private=rec["private_key"];new_hash,new_public,new_private_blob=_new_user_crypto(x.new_password);new_private=_unlock_private(x.new_password,new_private_blob)
    for bid,book in data.get("books",{}).items():
        member=book.get("members",{}).get(rec["user_key"])
        if not member: continue
        master=_unwrap_master(old_private,member["wrapped_master"]);member["wrapped_master"]=_wrap_master(new_public,master)
        try:
            db.activate(_book_path(book),master);c=db.db();row=c.execute("SELECT id FROM users WHERE username=?",(entry["username"],)).fetchone()
            if row:c.execute("UPDATE users SET password_hash=? WHERE id=?",(new_hash,row[0]));c.commit()
        except Exception: pass
    entry.update({"password_hash":new_hash,"public_key":new_public,"private_key":new_private_blob,"must_change_password":False});_auth_save(data);rec["private_key"]=new_private
    # Keep current session, close every other session of this user.
    with _app_session_lock:
        for token,r in list(_app_sessions.items()):
            if token!=th and r["user_key"]==rec["user_key"]:_app_sessions.pop(token,None)
    book=data["books"][rec["book_id"]];master=_unwrap_book_master(data,rec["book_id"],rec["user_key"],new_private);rec["book_master"]=master;db.activate(_book_path(book),master);c=db.db();audit_append(c,sess[1],"user.password_change","user",entry["username"],{});c.commit()
    return {"ok":True}

def _account_baseline(c, account_id: int, as_of: date) -> tuple[date, int]:
    row = c.execute("SELECT opening_balance,start_date FROM accounts WHERE id=? AND active=1", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Konto nicht gefunden")
    account_start = date.fromisoformat(row["start_date"])
    if as_of < account_start:
        return account_start, 0
    month_key = as_of.strftime("%Y-%m")
    override = c.execute(
        "SELECT month,opening_balance FROM account_month_overrides WHERE account_id=? AND month<=? ORDER BY month DESC LIMIT 1",
        (account_id, month_key),
    ).fetchone()
    if override:
        return date.fromisoformat(override["month"] + "-01"), int(override["opening_balance"])
    return account_start, int(row["opening_balance"])


def account_balance(c, account_id: int, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    baseline_date, baseline_value = _account_baseline(c, account_id, as_of)
    if as_of < baseline_date:
        return 0
    tx = c.execute(
        "SELECT COALESCE(SUM(CASE WHEN direction='expense' THEN -ABS(amount) WHEN direction='income' THEN ABS(amount) ELSE amount END),0) FROM transactions WHERE account_id=? AND status='executed' AND booking_date>=? AND booking_date<=?",
        (account_id, baseline_date.isoformat(), as_of.isoformat()),
    ).fetchone()[0]
    return baseline_value + int(tx)


def month_bounds(month: str | None = None) -> tuple[date, date]:
    try:
        anchor = date.fromisoformat((month or date.today().strftime('%Y-%m')) + '-01')
    except ValueError:
        raise HTTPException(400, 'Monat muss YYYY-MM sein')
    start = date(anchor.year, anchor.month, 1)
    end = date(anchor.year + (anchor.month == 12), 1 if anchor.month == 12 else anchor.month + 1, 1) - timedelta(days=1)
    return start, end


def projected_account_balance(c, account_id: int, as_of: date) -> int:
    """Balance used by month views and forecasts.

    It starts at the latest account/month baseline, applies every real/manual
    transaction through *as_of* and then every still-unexecuted recurring due
    date in the same window. recurring_events() suppresses occurrences that
    already have a transaction, so a series is never counted twice. This rule
    is deliberately identical for past, current and future selected months.
    """
    baseline_date, baseline_value = _account_baseline(c, account_id, as_of)
    if as_of < baseline_date:
        return 0

    tx_total=int(c.execute(
        """SELECT COALESCE(SUM(CASE WHEN direction='expense' THEN -ABS(amount) WHEN direction='income' THEN ABS(amount) ELSE amount END),0)
           FROM transactions WHERE account_id=? AND status<>'cancelled' AND booking_date>=? AND booking_date<=?""",
        (account_id, baseline_date.isoformat(), as_of.isoformat()),
    ).fetchone()[0] or 0)
    recurring_total=sum(int(ev["amount"]) for ev in recurring_events(c, account_id, baseline_date, as_of))
    return baseline_value + tx_total + recurring_total


def _month_opening_balance(c, account_id: int, start: date) -> int:
    override = c.execute(
        "SELECT opening_balance FROM account_month_overrides WHERE account_id=? AND month=?",
        (account_id, start.strftime("%Y-%m")),
    ).fetchone()
    if override:
        return int(override["opening_balance"])
    account = c.execute("SELECT start_date,opening_balance FROM accounts WHERE id=?", (account_id,)).fetchone()
    if account and date.fromisoformat(account["start_date"]) == start:
        return int(account["opening_balance"])
    return projected_account_balance(c, account_id, start - timedelta(days=1))


def monthly_account_series(c, account_id: int, month: str | None = None) -> list[dict]:
    start,end=month_bounds(month)
    opening=_month_opening_balance(c,account_id,start)
    movements=defaultdict(int)

    # If an account starts after the first day of the selected month, the
    # month opens at zero and the account's opening balance becomes effective
    # exactly on its start date. A month-opening override deliberately takes
    # precedence and must not be combined with the original opening balance.
    account=c.execute("SELECT start_date,opening_balance FROM accounts WHERE id=? AND active=1",(account_id,)).fetchone()
    exact_override=c.execute(
        "SELECT 1 FROM account_month_overrides WHERE account_id=? AND month=?",
        (account_id,start.strftime("%Y-%m")),
    ).fetchone()
    if account:
        account_start=date.fromisoformat(account["start_date"])
        if start < account_start <= end and not exact_override:
            movements[account_start.isoformat()]+=int(account["opening_balance"])
    for r in c.execute(
        """SELECT booking_date,COALESCE(SUM(CASE WHEN direction='expense' THEN -ABS(amount) WHEN direction='income' THEN ABS(amount) ELSE amount END),0) amount
           FROM transactions WHERE account_id=? AND status<>'cancelled' AND booking_date BETWEEN ? AND ?
           GROUP BY booking_date""",
        (account_id,start.isoformat(),end.isoformat())).fetchall():
        movements[r["booking_date"]]+=int(r["amount"] or 0)
    for ev in recurring_events(c,account_id,start,end):
        movements[ev["date"].isoformat()]+=int(ev["amount"])
    out=[];running=opening;d=start
    while d<=end:
        running+=movements.get(d.isoformat(),0)
        out.append({"date":d.isoformat(),"balance":euros(running),"opening_balance":euros(opening) if d==start else None})
        d+=timedelta(days=1)
    return out


def account_month_metrics(c, account_id: int, month: str | None = None) -> dict:
    start,end=month_bounds(month);today=date.today();cutoff_day=min(today.day,end.day);cutoff=date(start.year,start.month,cutoff_day)
    series=monthly_account_series(c,account_id,month)
    opening=float(series[0]["opening_balance"]) if series else euros(_month_opening_balance(c,account_id,start))
    by_date={p["date"]:p["balance"] for p in series}
    return {"month_start_balance":opening,"balance":by_date.get(cutoff.isoformat(),opening),
            "month_end_balance":by_date.get(end.isoformat(),opening),"balance_cutoff":cutoff.isoformat()}


@app.get('/api/accounts')
def accounts(request: Request, month: str | None = None):
    session(request)
    c = db.db()
    _, selected_end = month_bounds(month)
    rows = c.execute('SELECT id,name,type,iban,opening_balance,currency,start_date FROM accounts WHERE active=1 AND start_date<=? ORDER BY name',(selected_end.isoformat(),)).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item.update(account_month_metrics(c, r['id'], month))
        item['opening_balance'] = euros(r['opening_balance'])
        out.append(item)
    return out

@app.post("/api/accounts")
def account_create(x: AccountIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        cur = c.execute(
            "INSERT INTO accounts(name,type,iban,opening_balance,currency,start_date,created_at) VALUES(?,?,?,?,?,?,?)",
            (x.name.strip(), x.type, x.iban, cents(x.opening_balance), x.currency.upper(), x.start_date.isoformat(), iso(utcnow())),
        )
        audit_append(c,sess[1],"account.create","account",cur.lastrowid,{"added":{"name":x.name.strip(),"type":x.type,"iban":x.iban,"opening_balance":cents(x.opening_balance),"currency":x.currency.upper(),"start_date":x.start_date.isoformat()}})
        return {"id": cur.lastrowid}


@app.put("/api/accounts/{account_id}")
def account_update(account_id: int, x: AccountIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        before_row=c.execute("SELECT name,type,iban,opening_balance,currency,start_date FROM accounts WHERE id=? AND active=1",(account_id,)).fetchone()
        if not before_row:
            raise HTTPException(404, "Konto nicht gefunden")
        before=dict(before_row)
        cur = c.execute(
            "UPDATE accounts SET name=?,type=?,iban=?,opening_balance=?,currency=?,start_date=? WHERE id=? AND active=1",
            (x.name.strip(), x.type, x.iban, cents(x.opening_balance), x.currency.upper(), x.start_date.isoformat(), account_id),
        )
        after=dict(c.execute("SELECT name,type,iban,opening_balance,currency,start_date FROM accounts WHERE id=?",(account_id,)).fetchone())
        audit_append(c,sess[1],"account.update","account",account_id,{"name":after.get("name"),"changes":audit_changes(before,after,("name","type","iban","opening_balance","currency","start_date")),"current":audit_pick(after,("name","type","iban","opening_balance","currency","start_date"))})
    return {"ok": True}


class AccountMonthCorrectionIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    opening_balance: Decimal
    note: str | None = Field(default=None, max_length=300)


@app.get("/api/accounts/{account_id}/corrections")
def account_corrections(account_id: int, request: Request):
    session(request)
    rows = db.db().execute(
        "SELECT id,month,opening_balance,note,created_at FROM account_month_overrides WHERE account_id=? ORDER BY month DESC",
        (account_id,),
    ).fetchall()
    return [{**dict(r), "opening_balance": euros(r["opening_balance"])} for r in rows]


@app.put("/api/accounts/{account_id}/month-opening")
def account_month_opening(account_id: int, x: AccountMonthCorrectionIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        account = c.execute("SELECT start_date FROM accounts WHERE id=? AND active=1", (account_id,)).fetchone()
        if not account:
            raise HTTPException(404, "Konto nicht gefunden")
        if x.month < str(account["start_date"])[:7]:
            raise HTTPException(400, "Korrekturmonat liegt vor dem Kontostart")
        prior=c.execute("SELECT opening_balance,note FROM account_month_overrides WHERE account_id=? AND month=?",(account_id,x.month)).fetchone()
        c.execute(
            """INSERT INTO account_month_overrides(account_id,month,opening_balance,note,created_at) VALUES(?,?,?,?,?)
               ON CONFLICT(account_id,month) DO UPDATE SET opening_balance=excluded.opening_balance,note=excluded.note,created_at=excluded.created_at""",
            (account_id, x.month, cents(x.opening_balance), clean_text(x.note, 300), iso(utcnow())),
        )
        after={"opening_balance":cents(x.opening_balance),"note":clean_text(x.note,300)}
        details={"month":x.month}
        if prior:
            details["changes"]=audit_changes(dict(prior),after,("opening_balance","note"))
        else:
            details["added"]=after
        audit_append(c,sess[1],"account.month_opening","account",account_id,details)
    return {"ok": True}


@app.delete("/api/accounts/{account_id}/month-opening/{month}")
def account_month_opening_delete(account_id: int, month: str, request: Request):
    sess=session(request, True)
    month_bounds(month)
    with db.transaction() as c:
        c.execute("DELETE FROM account_month_overrides WHERE account_id=? AND month=?", (account_id, month))
        audit_append(c,sess[1],"account.month_opening.delete","account",account_id,{"month":month})
    return {"ok": True}


@app.delete("/api/accounts/{account_id}")
def account_delete(account_id: int, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        used = c.execute("SELECT COUNT(*) FROM transactions WHERE account_id=?", (account_id,)).fetchone()[0]
        if used:
            c.execute("UPDATE accounts SET active=0 WHERE id=?", (account_id,))
        else:
            c.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        audit_append(c,sess[1],"account.delete","account",account_id,{"soft":bool(used)})
    return {"ok": True}


def tx_snapshot(c, tx_id: int) -> dict:
    r = c.execute("""SELECT t.*,a.name account_name,c.name category_name,
                          tr.name transfer_name,fa.name transfer_from_account_name,ta.name transfer_to_account_name
                   FROM transactions t
                   LEFT JOIN accounts a ON a.id=t.account_id
                   LEFT JOIN categories c ON c.id=t.category_id
                   LEFT JOIN transfers tr ON tr.id=t.transfer_id
                   LEFT JOIN accounts fa ON fa.id=tr.from_account_id
                   LEFT JOIN accounts ta ON ta.id=tr.to_account_id
                   WHERE t.id=?""", (tx_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Buchung nicht gefunden")
    snap = dict(r)
    snap["tags"] = [x[0] for x in c.execute("SELECT tag FROM transaction_tags WHERE transaction_id=? ORDER BY tag", (tx_id,)).fetchall()]
    snap["splits"] = [dict(x) for x in c.execute("SELECT category_id,amount,note FROM splits WHERE transaction_id=? ORDER BY id", (tx_id,)).fetchall()]
    return snap


def validate_splits(amount_cents: int, splits: list[SplitIn]) -> None:
    if splits and sum(cents(s.amount) for s in splits) != amount_cents:
        raise HTTPException(400, "Die Summe der Splits muss exakt dem Buchungsbetrag entsprechen")


def write_tx_children(c, tx_id: int, tags: list[str], splits: list[SplitIn]) -> None:
    c.execute("DELETE FROM transaction_tags WHERE transaction_id=?", (tx_id,))
    c.execute("DELETE FROM splits WHERE transaction_id=?", (tx_id,))
    for tag in tags:
        tag = clean_text(tag, 64)
        if tag:
            c.execute("INSERT OR IGNORE INTO transaction_tags(transaction_id,tag) VALUES(?,?)", (tx_id, tag))
    for split in splits:
        c.execute(
            "INSERT INTO splits(transaction_id,category_id,amount,note) VALUES(?,?,?,?)",
            (tx_id, split.category_id, cents(split.amount), clean_text(split.note, 300)),
        )


def serialize_transaction_rows(c, rows) -> list[dict]:
    """Serialize a transaction page with batched child lookups.

    This removes the previous tags/splits/recurring N+1 query pattern, which
    matters once the user switches to yearly/all-bookings views.
    """
    rows=list(rows)
    if not rows:
        return []
    ids=[int(r["id"]) for r in rows]
    marks=",".join("?" for _ in ids)
    tags_by=defaultdict(list)
    for r in c.execute("SELECT transaction_id,tag FROM transaction_tags WHERE transaction_id IN ("+marks+") ORDER BY transaction_id,tag",ids).fetchall():
        tags_by[int(r["transaction_id"])].append(r["tag"])
    splits_by=defaultdict(list)
    for r in c.execute("SELECT transaction_id,category_id,amount,note FROM splits WHERE transaction_id IN ("+marks+") ORDER BY transaction_id,id",ids).fetchall():
        splits_by[int(r["transaction_id"])].append({"category_id":r["category_id"],"amount":euros(r["amount"]),"note":r["note"]})

    recurring_ids=sorted({int(r["recurring_id"]) for r in rows if r["recurring_id"]})
    recurring_by_id={}
    latest_by_series={}
    if recurring_ids:
        rm=",".join("?" for _ in recurring_ids)
        base=c.execute("SELECT * FROM recurring WHERE id IN ("+rm+")",recurring_ids).fetchall()
        recurring_by_id={int(r["id"]):r for r in base}
        series_ids=sorted({int(r["series_id"] or r["id"]) for r in base})
        sm=",".join("?" for _ in series_ids)
        versions=c.execute("SELECT * FROM recurring WHERE COALESCE(series_id,id) IN ("+sm+") AND active=1 ORDER BY COALESCE(valid_from,next_date),id",series_ids).fetchall()
        for rr in versions:
            latest_by_series[int(rr["series_id"] or rr["id"])]=rr

    transfer_ids=sorted({int(r["transfer_id"]) for r in rows if "transfer_id" in r.keys() and r["transfer_id"]})
    transfers={}
    if transfer_ids:
        tm=",".join("?" for _ in transfer_ids)
        trs=c.execute(f"""SELECT tr.*,fa.name from_account_name,ta.name to_account_name
                           FROM transfers tr JOIN accounts fa ON fa.id=tr.from_account_id
                           JOIN accounts ta ON ta.id=tr.to_account_id WHERE tr.id IN ({tm})""",transfer_ids).fetchall()
        transfers={int(r["id"]):dict(r) for r in trs}

    out=[]
    for r in rows:
        item=dict(r); item["amount"]=euros(item["amount"]); rid=int(r["id"])
        item["tags"]=tags_by.get(rid,[])
        item["splits"]=splits_by.get(rid,[])
        item["recurring"]=False
        if r["recurring_id"]:
            rr=recurring_by_id.get(int(r["recurring_id"]))
            if rr:
                series_id=int(rr["series_id"] or rr["id"]); latest=latest_by_series.get(series_id,rr)
                item.update({"recurring":True,"recurring_id":latest["id"],"recurring_series_id":series_id,
                             "recurring_frequency":latest["frequency"],"recurring_interval_count":int(latest["interval_count"] or 1),"recurring_until":latest["valid_until"],
                             "recurring_effective_from":latest["valid_from"] or latest["next_date"],"recurring_name":latest["name"]})
        item["transfer"]=False
        if item.get("transfer_id"):
            tr=transfers.get(int(item["transfer_id"]))
            if tr:
                item.update({"transfer":True,"transfer_name":tr["name"],"transfer_from_account_id":tr["from_account_id"],
                             "transfer_to_account_id":tr["to_account_id"],"transfer_from_account_name":tr["from_account_name"],
                             "transfer_to_account_name":tr["to_account_name"],"transfer_note":tr["note"]})
        out.append(item)
    return out


@app.get("/api/payees")
def payee_presets(request: Request):
    session(request)
    return [dict(r) for r in db.db().execute(
        "SELECT id,name,usage_count,created_at,last_used_at FROM payee_presets ORDER BY usage_count DESC,last_used_at DESC,name COLLATE NOCASE"
    ).fetchall()]


@app.post("/api/payees")
def payee_preset_create(x: PayeePresetIn, request: Request):
    sess=session(request,True); name=clean_text(x.name,200)
    with db.transaction() as c:
        ts=iso(utcnow())
        try:
            cur=c.execute("INSERT INTO payee_presets(name,usage_count,created_at,last_used_at) VALUES(?,1,?,?)",(name,ts,ts))
        except Exception:
            raise HTTPException(409,"Empfänger ist bereits gespeichert")
        audit_append(c,sess[1],"payee.create","payee",cur.lastrowid,{"added":{"name":name}})
        return {"id":cur.lastrowid,"name":name}


@app.put("/api/payees/{payee_id}")
def payee_preset_update(payee_id: int, x: PayeePresetIn, request: Request):
    sess=session(request,True); name=clean_text(x.name,200)
    with db.transaction() as c:
        old=c.execute("SELECT * FROM payee_presets WHERE id=?",(payee_id,)).fetchone()
        if not old: raise HTTPException(404,"Empfänger nicht gefunden")
        try: c.execute("UPDATE payee_presets SET name=?,last_used_at=? WHERE id=?",(name,iso(utcnow()),payee_id))
        except Exception: raise HTTPException(409,"Empfänger ist bereits gespeichert")
        audit_append(c,sess[1],"payee.update","payee",payee_id,{"name":name,"changes":{"name":{"old":old["name"],"new":name}},"current":{"name":name,"usage_count":old["usage_count"]}})
    return {"ok":True}


@app.delete("/api/payees/{payee_id}")
def payee_preset_delete(payee_id: int, request: Request):
    sess=session(request,True)
    with db.transaction() as c:
        old=c.execute("SELECT * FROM payee_presets WHERE id=?",(payee_id,)).fetchone()
        if not old: raise HTTPException(404,"Empfänger nicht gefunden")
        audit_append(c,sess[1],"payee.delete","payee",payee_id,{"snapshot":{"name":old["name"],"usage_count":old["usage_count"]}})
        c.execute("DELETE FROM payee_presets WHERE id=?",(payee_id,))
    return {"ok":True}


def validate_transfer_accounts(c, from_account_id: int, to_account_id: int) -> tuple:
    if from_account_id==to_account_id:
        raise HTTPException(400,"Quell- und Zielkonto müssen verschieden sein")
    rows=c.execute("SELECT id,name,active FROM accounts WHERE id IN (?,?)",(from_account_id,to_account_id)).fetchall()
    amap={int(r["id"]):r for r in rows}
    if from_account_id not in amap or to_account_id not in amap:
        raise HTTPException(400,"Quell- oder Zielkonto nicht gefunden")
    if not int(amap[from_account_id]["active"]) or not int(amap[to_account_id]["active"]):
        raise HTTPException(400,"Transfer nur zwischen aktiven Konten möglich")
    return amap[from_account_id],amap[to_account_id]


def recurring_transfer_snapshot(c, recurring_transfer_id: int) -> dict:
    row=c.execute("""SELECT rt.*,fa.name from_account_name,ta.name to_account_name
                     FROM recurring_transfers rt
                     JOIN accounts fa ON fa.id=rt.from_account_id
                     JOIN accounts ta ON ta.id=rt.to_account_id
                     WHERE rt.id=?""",(recurring_transfer_id,)).fetchone()
    if not row:
        raise HTTPException(404,"Wiederkehrender Transfer nicht gefunden")
    item=dict(row)
    item["amount"]=euros(int(item["amount"]))
    return item


def _recurring_transfer_end(r, reference: date | None = None) -> date:
    if r["valid_until"]:
        return date.fromisoformat(r["valid_until"])
    start=date.fromisoformat(r["next_date"])
    base=max(reference or date.today(),start)
    return add_months(base,24)-timedelta(days=1)


def _create_transfer_instance(c, from_account_id: int, to_account_id: int, amount: int,
                              booking_date: date, name: str, note: str | None,
                              status: str="executed", recurring_transfer_id: int | None=None) -> int:
    src,dst=validate_transfer_accounts(c,from_account_id,to_account_id)
    ts=iso(utcnow())
    cur=c.execute("""INSERT INTO transfers(from_account_id,to_account_id,amount,booking_date,name,note,recurring_transfer_id,active,created_at,updated_at)
                     VALUES(?,?,?,?,?,?,?,1,?,?)""",
                  (from_account_id,to_account_id,amount,booking_date.isoformat(),name,note,recurring_transfer_id,ts,ts))
    tid=int(cur.lastrowid)
    c.execute("""INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,note,category_id,status,external_id,recurring_id,transfer_id,transfer_side,confidence,fixed_cost,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,NULL,?,?,NULL,?,'out','fixed',0,?,?)""",
              (from_account_id,-amount,'expense',booking_date.isoformat(),name,dst["name"],note,status,f"transfer-{tid}-out",tid,ts,ts))
    c.execute("""INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,note,category_id,status,external_id,recurring_id,transfer_id,transfer_side,confidence,fixed_cost,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,NULL,?,?,NULL,?,'in','fixed',0,?,?)""",
              (to_account_id,amount,'income',booking_date.isoformat(),name,src["name"],note,status,f"transfer-{tid}-in",tid,ts,ts))
    return tid


def _materialize_recurring_transfer_window(c, from_day: date, to_day: date,
                                           recurring_transfer_id: int | None=None) -> list[dict]:
    if from_day>to_day:
        return []
    sql="""SELECT * FROM recurring_transfers
           WHERE active=1 AND next_date<=? AND (valid_until IS NULL OR valid_until>=?)"""
    args=[to_day.isoformat(),from_day.isoformat()]
    if recurring_transfer_id is not None:
        sql+=" AND id=?";args.append(recurring_transfer_id)
    created=[]
    for r in c.execute(sql,args).fetchall():
        start=date.fromisoformat(r["next_date"])
        high=min(to_day,date.fromisoformat(r["valid_until"]) if r["valid_until"] else to_day)
        low=max(from_day,start)
        if low>high:
            continue
        for due in occurrences(start,r["frequency"],low,high,int(r["interval_count"] or 1)):
            existing=c.execute("SELECT id FROM transfers WHERE recurring_transfer_id=? AND booking_date=?",
                               (r["id"],due.isoformat())).fetchone()
            if existing:
                continue
            tid=_create_transfer_instance(c,int(r["from_account_id"]),int(r["to_account_id"]),int(r["amount"]),
                                          due,r["name"],r["note"],"planned",int(r["id"]))
            created.append({"transfer_id":tid,"recurring_transfer_id":int(r["id"]),
                            "due_date":due.isoformat(),"amount":euros(int(r["amount"])),"kind":"transfer"})
    return created


def _materialize_recurring_transfer_series(c, recurring_transfer_id: int,
                                           from_day: date | None=None) -> list[dict]:
    r=c.execute("SELECT * FROM recurring_transfers WHERE id=? AND active=1",(recurring_transfer_id,)).fetchone()
    if not r:
        return []
    start=date.fromisoformat(r["next_date"])
    low=from_day or max(date.today(),start)
    high=_recurring_transfer_end(r,low)
    return _materialize_recurring_transfer_window(c,low,high,recurring_transfer_id)


def _remove_planned_recurring_transfer_instances(c, recurring_transfer_id: int, from_day: date) -> int:
    rows=c.execute("""SELECT tr.id FROM transfers tr
                      WHERE tr.recurring_transfer_id=? AND tr.booking_date>=?
                        AND NOT EXISTS (
                          SELECT 1 FROM transactions t
                          WHERE t.transfer_id=tr.id AND t.status='executed'
                        )""",(recurring_transfer_id,from_day.isoformat())).fetchall()
    ids=[int(r["id"]) for r in rows]
    for tid in ids:
        c.execute("DELETE FROM transactions WHERE transfer_id=?",(tid,))
        c.execute("DELETE FROM transfers WHERE id=?",(tid,))
    return len(ids)


def _next_recurring_transfer_due(c, r, from_day: date | None=None) -> date | None:
    start=date.fromisoformat(r["next_date"])
    low=max(from_day or date.today(),start)
    high=_recurring_transfer_end(r,low)
    for due in occurrences(start,r["frequency"],low,high,int(r["interval_count"] or 1)):
        tr=c.execute("SELECT id,active FROM transfers WHERE recurring_transfer_id=? AND booking_date=?",
                     (r["id"],due.isoformat())).fetchone()
        if not tr:
            return due
        statuses=[x["status"] for x in c.execute("SELECT status FROM transactions WHERE transfer_id=?",(tr["id"],)).fetchall()]
        if int(tr["active"] or 0) and statuses and "executed" not in statuses and "cancelled" not in statuses:
            return due
    return None


@app.get("/api/transfers/{transfer_id}")
def transfer_get(transfer_id: int, request: Request):
    session(request)
    c=db.db();snap=transfer_snapshot(c,transfer_id);snap["amount"]=euros(snap["amount"])
    recurring_transfer_id=snap.get("recurring_transfer_id")
    snap["recurring_transfer_id"]=int(recurring_transfer_id) if recurring_transfer_id else None
    snap["recurring"]=bool(recurring_transfer_id)
    if recurring_transfer_id:
        rr=c.execute("SELECT frequency,interval_count,valid_until FROM recurring_transfers WHERE id=?",(recurring_transfer_id,)).fetchone()
        if rr:
            snap["recurring_frequency"]=rr["frequency"]
            snap["recurring_interval_count"]=int(rr["interval_count"] or 1)
            snap["recurring_until"]=rr["valid_until"]
    return snap


@app.post("/api/transfers")
def transfer_create(x: TransferIn, request: Request):
    sess=session(request,True);request_id=client_request_id(request);endpoint="POST /api/transfers"
    replay=client_mutation_replay(db.db(),request_id,endpoint)
    if replay is not None:
        return replay
    amount=abs(cents(x.amount));ts=iso(utcnow())
    if amount<=0:
        raise HTTPException(400,"Transferbetrag muss größer als 0 sein")
    if x.recurring and not x.recurring_frequency:
        raise HTTPException(400,"Intervall für wiederkehrenden Transfer fehlt")
    if x.recurring_until and x.recurring_until<x.booking_date:
        raise HTTPException(400,"Enddatum darf nicht vor dem Startdatum liegen")
    with db.transaction() as c:
        validate_transfer_accounts(c,x.from_account_id,x.to_account_id)
        name=clean_text(x.name,160) or "Transfer";note=clean_text(x.note,1000)
        recurring_transfer_id=None
        if x.recurring:
            cur=c.execute("""INSERT INTO recurring_transfers(from_account_id,to_account_id,amount,next_date,frequency,interval_count,name,note,valid_until,active,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,1,?,?)""",
                          (x.from_account_id,x.to_account_id,amount,x.booking_date.isoformat(),x.recurring_frequency,
                           x.recurring_interval_count,name,note,x.recurring_until.isoformat() if x.recurring_until else None,ts,ts))
            recurring_transfer_id=int(cur.lastrowid)
        status="planned" if x.booking_date>date.today() else "executed"
        tid=_create_transfer_instance(c,x.from_account_id,x.to_account_id,amount,x.booking_date,name,note,status,recurring_transfer_id)
        generated=0
        if recurring_transfer_id:
            generated=1+len(_materialize_recurring_transfer_series(c,recurring_transfer_id,x.booking_date+timedelta(days=1)))
        snap=transfer_snapshot(c,tid)
        details={"name":name,"added":audit_pick(snap,("name","amount","booking_date","from_account_name","to_account_name","note"))}
        if recurring_transfer_id:
            details.update({"recurring_transfer_id":recurring_transfer_id,"frequency":x.recurring_frequency,
                            "interval_count":x.recurring_interval_count,"valid_until":x.recurring_until.isoformat() if x.recurring_until else None,
                            "generated_transfers":generated})
        audit_append(c,sess[1],"transfer.create","transfer",tid,details)
        result={"id":tid,"recurring_transfer_id":recurring_transfer_id,"generated_transfers":generated}
        client_mutation_store(c,request_id,endpoint,result)
    return result


@app.put("/api/transfers/{transfer_id}")
def transfer_update(transfer_id: int, x: TransferIn, request: Request):
    sess=session(request,True);amount=abs(cents(x.amount));ts=iso(utcnow())
    if amount<=0:
        raise HTTPException(400,"Transferbetrag muss größer als 0 sein")
    with db.transaction() as c:
        before=transfer_snapshot(c,transfer_id)
        if not int(before.get("active",1)):
            raise HTTPException(400,"Transfer ist storniert")
        src,dst=validate_transfer_accounts(c,x.from_account_id,x.to_account_id)
        name=clean_text(x.name,160) or "Transfer";note=clean_text(x.note,1000)
        c.execute("UPDATE transfers SET from_account_id=?,to_account_id=?,amount=?,booking_date=?,name=?,note=?,updated_at=? WHERE id=?",
                  (x.from_account_id,x.to_account_id,amount,x.booking_date.isoformat(),name,note,ts,transfer_id))
        c.execute("""UPDATE transactions SET account_id=?,amount=?,direction='expense',booking_date=?,name=?,payee=?,note=?,updated_at=?
                     WHERE transfer_id=? AND transfer_side='out'""",
                  (x.from_account_id,-amount,x.booking_date.isoformat(),name,dst["name"],note,ts,transfer_id))
        c.execute("""UPDATE transactions SET account_id=?,amount=?,direction='income',booking_date=?,name=?,payee=?,note=?,updated_at=?
                     WHERE transfer_id=? AND transfer_side='in'""",
                  (x.to_account_id,amount,x.booking_date.isoformat(),name,src["name"],note,ts,transfer_id))
        after=transfer_snapshot(c,transfer_id)
        fields=("name","amount","booking_date","from_account_name","to_account_name","note")
        audit_append(c,sess[1],"transfer.update","transfer",transfer_id,
                     {"name":name,"changes":audit_changes(before,after,fields),"current":audit_pick(after,fields)})
    return {"ok":True}


@app.delete("/api/transfers/{transfer_id}")
def transfer_delete(transfer_id: int, request: Request, hard: bool=False):
    sess=session(request,True)
    with db.transaction() as c:
        before=transfer_snapshot(c,transfer_id)
        linked=before.get("recurring_transfer_id")
        audit_append(c,sess[1],"transfer.delete","transfer",transfer_id,
                     {"snapshot":audit_pick(before,("name","amount","booking_date","from_account_name","to_account_name","note")),
                      "recurring_transfer_id":linked})
        # A hard-deleted generated occurrence would immediately be recreated by
        # the series materialiser. Keep it as a cancelled tombstone instead.
        if hard and not linked:
            c.execute("DELETE FROM transactions WHERE transfer_id=?",(transfer_id,))
            c.execute("DELETE FROM transfers WHERE id=?",(transfer_id,))
        else:
            c.execute("UPDATE transfers SET active=0,updated_at=? WHERE id=?",(iso(utcnow()),transfer_id))
            c.execute("UPDATE transactions SET status='cancelled',updated_at=? WHERE transfer_id=?",(iso(utcnow()),transfer_id))
    return {"ok":True,"hard":bool(hard and not linked)}


@app.post("/api/recurring-transfers/materialize-due")
def recurring_transfer_materialize_due(request: Request, month: str | None=None, year: int | None=None):
    sess=session(request,True);today=date.today()
    with db.transaction() as c:
        if month:
            start,end=month_bounds(month)
            items=_materialize_recurring_transfer_window(c,start,end)
            return {"created":len(items),"items":items,"through":end.isoformat(),"scope":"month"}
        if year is not None:
            if year<1970 or year>2200:
                raise HTTPException(400,"Ungültiges Jahr")
            start,end=date(year,1,1),date(year,12,31)
            items=_materialize_recurring_transfer_window(c,start,end)
            return {"created":len(items),"items":items,"through":end.isoformat(),"scope":"year"}
        items=[]
        rows=c.execute("SELECT * FROM recurring_transfers WHERE active=1").fetchall()
        for r in rows:
            low=max(today,date.fromisoformat(r["next_date"]))
            items.extend(_materialize_recurring_transfer_series(c,int(r["id"]),low))
        horizons=[_recurring_transfer_end(r,today) for r in rows]
        return {"created":len(items),"items":items,"through":max(horizons).isoformat() if horizons else today.isoformat(),"scope":"all"}


@app.get("/api/recurring-transfers")
def recurring_transfers(request: Request):
    session(request);c=db.db();out=[]
    for r in c.execute("""SELECT rt.*,fa.name from_account_name,ta.name to_account_name
                          FROM recurring_transfers rt
                          JOIN accounts fa ON fa.id=rt.from_account_id
                          JOIN accounts ta ON ta.id=rt.to_account_id
                          WHERE rt.active=1 ORDER BY rt.next_date,rt.id""").fetchall():
        due=_next_recurring_transfer_due(c,r)
        if due is None:
            continue
        item=dict(r);item["next_date"]=due.isoformat();item["first_date"]=r["next_date"]
        item["amount"]=euros(int(r["amount"]));item["interval_count"]=int(r["interval_count"] or 1)
        item["status"]="overdue" if due<date.today() else "planned"
        out.append(item)
    return out


@app.get("/api/recurring-transfers/{recurring_transfer_id}")
def recurring_transfer_get(recurring_transfer_id: int, request: Request):
    session(request);c=db.db()
    row=c.execute("""SELECT rt.*,fa.name from_account_name,ta.name to_account_name
                     FROM recurring_transfers rt
                     JOIN accounts fa ON fa.id=rt.from_account_id
                     JOIN accounts ta ON ta.id=rt.to_account_id WHERE rt.id=?""",(recurring_transfer_id,)).fetchone()
    if not row:
        raise HTTPException(404,"Wiederkehrender Transfer nicht gefunden")
    item=dict(row);item["first_date"]=row["next_date"];due=_next_recurring_transfer_due(c,row)
    item["next_date"]=(due or date.fromisoformat(row["next_date"])).isoformat()
    item["amount"]=euros(int(row["amount"]));item["interval_count"]=int(row["interval_count"] or 1)
    return item


@app.put("/api/recurring-transfers/{recurring_transfer_id}")
def recurring_transfer_update(recurring_transfer_id: int, x: TransferIn, request: Request):
    sess=session(request,True);amount=abs(cents(x.amount));ts=iso(utcnow())
    if not x.recurring_frequency:
        raise HTTPException(400,"Intervall für wiederkehrenden Transfer fehlt")
    if x.recurring_until and x.recurring_until<x.booking_date:
        raise HTTPException(400,"Enddatum darf nicht vor dem nächsten Termin liegen")
    with db.transaction() as c:
        old=c.execute("SELECT * FROM recurring_transfers WHERE id=? AND active=1",(recurring_transfer_id,)).fetchone()
        if not old:
            raise HTTPException(404,"Wiederkehrender Transfer nicht gefunden")
        validate_transfer_accounts(c,x.from_account_id,x.to_account_id)
        removed=_remove_planned_recurring_transfer_instances(c,recurring_transfer_id,date.today())
        name=clean_text(x.name,160) or "Transfer";note=clean_text(x.note,1000)
        c.execute("""UPDATE recurring_transfers SET from_account_id=?,to_account_id=?,amount=?,next_date=?,frequency=?,interval_count=?,
                     name=?,note=?,valid_until=?,updated_at=? WHERE id=?""",
                  (x.from_account_id,x.to_account_id,amount,x.booking_date.isoformat(),x.recurring_frequency,
                   x.recurring_interval_count,name,note,x.recurring_until.isoformat() if x.recurring_until else None,ts,recurring_transfer_id))
        generated=_materialize_recurring_transfer_series(c,recurring_transfer_id,max(date.today(),x.booking_date))
        audit_append(c,sess[1],"recurring_transfer.update","recurring_transfer",recurring_transfer_id,
                     {"name":name,"removed_planned_transfers":removed,"generated_transfers":len(generated),
                      "frequency":x.recurring_frequency,"interval_count":x.recurring_interval_count,
                      "next_date":x.booking_date.isoformat(),"valid_until":x.recurring_until.isoformat() if x.recurring_until else None})
    return {"ok":True,"removed_planned_transfers":removed,"generated_transfers":len(generated)}


@app.delete("/api/recurring-transfers/{recurring_transfer_id}")
def recurring_transfer_delete(recurring_transfer_id: int, request: Request, hard: bool=False):
    sess=session(request,True)
    with db.transaction() as c:
        row=c.execute("SELECT * FROM recurring_transfers WHERE id=?",(recurring_transfer_id,)).fetchone()
        if not row:
            raise HTTPException(404,"Wiederkehrender Transfer nicht gefunden")
        removed=_remove_planned_recurring_transfer_instances(c,recurring_transfer_id,date.today())
        if hard:
            c.execute("UPDATE transfers SET recurring_transfer_id=NULL WHERE recurring_transfer_id=?",(recurring_transfer_id,))
            c.execute("DELETE FROM recurring_transfers WHERE id=?",(recurring_transfer_id,))
        else:
            c.execute("UPDATE recurring_transfers SET active=0,updated_at=? WHERE id=?",(iso(utcnow()),recurring_transfer_id))
        audit_append(c,sess[1],"recurring_transfer.delete" if hard else "recurring_transfer.stop",
                     "recurring_transfer",recurring_transfer_id,
                     {"name":row["name"],"hard":hard,"removed_planned_transfers":removed})
    return {"ok":True,"hard":hard,"removed_planned_transfers":removed}

@app.get("/api/transactions")
def transactions(request: Request, account_id: int | None = None, q: str | None = None, month: str | None = None, limit: int = 250, include_cancelled: bool = False):
    session(request)
    limit = max(1, min(limit, 1000))
    sql = """SELECT t.id,t.account_id,a.name account_name,t.amount,t.booking_date,t.value_date,t.name,t.payee,t.note,
             t.category_id,c.name category_name,t.direction,t.status,t.recurring_id,t.transfer_id,t.transfer_side,t.confidence,t.fixed_cost,t.created_at,t.updated_at
             FROM transactions t JOIN accounts a ON a.id=t.account_id
             LEFT JOIN categories c ON c.id=t.category_id WHERE 1=1"""
    args: list = []
    if not include_cancelled:
        sql += " AND t.status<>?"
        args.append("cancelled")
    if account_id is not None:
        sql += " AND t.account_id=?"
        args.append(account_id)
    if month:
        start, end = month_bounds(month)
        sql += " AND t.booking_date BETWEEN ? AND ?"
        args.extend([start.isoformat(), end.isoformat()])
    if q:
        sql += """ AND (COALESCE(t.name,'') LIKE ? OR COALESCE(t.payee,'') LIKE ? OR COALESCE(t.note,'') LIKE ? OR COALESCE(c.name,'') LIKE ? OR EXISTS (SELECT 1 FROM transaction_tags tt WHERE tt.transaction_id=t.id AND tt.tag LIKE ?))"""
        pattern = f"%{q[:100]}%"
        args.extend([pattern, pattern, pattern, pattern, pattern])
    sql += " ORDER BY t.booking_date DESC,t.id DESC LIMIT ?"
    args.append(limit)
    c = db.db()
    return serialize_transaction_rows(c,c.execute(sql,args).fetchall())


@app.get("/api/transactions/paged")
def transactions_paged(request: Request, account_id: int | None = None, q: str | None = None,
                       period: str = "month", month: str | None = None, year: int | None = None,
                       page: int = 1, page_size: int = 25, include_cancelled: bool = False):
    session(request)
    if period not in {"month","year","all"}:
        raise HTTPException(400,"Zeitraum muss month, year oder all sein")
    page=max(1,page)
    page_size=0 if page_size==0 else max(1,min(page_size,100))
    c=db.db()
    where=["1=1"]; args=[]
    if not include_cancelled:
        where.append("t.status<>?"); args.append("cancelled")
    if account_id is not None:
        where.append("t.account_id=?"); args.append(account_id)
    if period=="month":
        start,end=month_bounds(month)
        where.append("t.booking_date BETWEEN ? AND ?"); args.extend([start.isoformat(),end.isoformat()])
    elif period=="year":
        y=year or date.today().year
        where.append("t.booking_date BETWEEN ? AND ?"); args.extend([f"{y:04d}-01-01",f"{y:04d}-12-31"])
    if q:
        pattern=f"%{q[:100]}%"
        where.append("""(COALESCE(t.name,'') LIKE ? OR COALESCE(t.payee,'') LIKE ? OR COALESCE(t.note,'') LIKE ?
                        OR COALESCE(cat.name,'') LIKE ?
                        OR EXISTS (SELECT 1 FROM transaction_tags tt WHERE tt.transaction_id=t.id AND tt.tag LIKE ?))""")
        args.extend([pattern]*5)
    wh=" AND ".join(where)
    total=int(c.execute(f"""SELECT COUNT(*) FROM transactions t
                            LEFT JOIN categories cat ON cat.id=t.category_id WHERE {wh}""",args).fetchone()[0])
    effective=max(total,1) if page_size==0 else page_size
    pages=1 if page_size==0 else max(1,(total+effective-1)//effective)
    page=min(page,pages)
    offset=(page-1)*effective
    rows=c.execute(f"""SELECT t.id,t.account_id,a.name account_name,t.amount,t.booking_date,t.value_date,t.name,t.payee,t.note,
                              t.category_id,cat.name category_name,t.direction,t.status,t.recurring_id,t.transfer_id,t.transfer_side,t.confidence,t.fixed_cost,t.created_at,t.updated_at
                       FROM transactions t JOIN accounts a ON a.id=t.account_id
                       LEFT JOIN categories cat ON cat.id=t.category_id
                       WHERE {wh}
                       ORDER BY t.booking_date DESC,t.id DESC LIMIT ? OFFSET ?""",
                   [*args,effective,offset]).fetchall()
    items=serialize_transaction_rows(c,rows)
    return {"items":items,"total":total,"page":page,"page_size":0 if page_size==0 else effective,"pages":pages,"period":period}



IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def client_request_id(request: Request) -> str | None:
    value=(request.headers.get("X-Idempotency-Key") or "").strip()
    if not value:
        return None
    if not IDEMPOTENCY_KEY_RE.fullmatch(value):
        raise HTTPException(400,"Ungültiger Idempotency-Key")
    return value


def client_mutation_replay(c, request_id: str | None, endpoint: str):
    if not request_id:
        return None
    row=c.execute("SELECT endpoint,response_json FROM client_mutations WHERE request_id=?",(request_id,)).fetchone()
    if not row:
        return None
    if row["endpoint"] != endpoint:
        raise HTTPException(409,"Idempotency-Key wurde bereits für eine andere Aktion verwendet")
    payload=json.loads(row["response_json"])
    if isinstance(payload,dict):
        payload=dict(payload);payload["idempotent_replay"]=True
    return payload


def client_mutation_store(c, request_id: str | None, endpoint: str, payload: dict) -> None:
    if not request_id:
        return
    c.execute("DELETE FROM client_mutations WHERE created_at<?",(iso(utcnow()-timedelta(days=365)),))
    c.execute("INSERT INTO client_mutations(request_id,endpoint,response_json,created_at) VALUES(?,?,?,?)",
              (request_id,endpoint,json.dumps(payload,ensure_ascii=False,separators=(",",":")),iso(utcnow())))

@app.post("/api/transactions")
def transaction_create(x: TransactionIn, request: Request):
    sess=session(request, True)
    request_id=client_request_id(request); endpoint="POST /api/transactions"
    c0 = db.db()
    replay=client_mutation_replay(c0,request_id,endpoint)
    if replay is not None:
        return replay
    if x.category_id is not None:
        cat = c0.execute("SELECT direction FROM categories WHERE id=? AND active=1", (x.category_id,)).fetchone()
        if not cat:
            raise HTTPException(400, "Kategorie nicht gefunden")
        category_type = cat["direction"]
        tx_direction = "income" if category_type == "income" else "expense"
    else:
        # Compatibility for API/import clients. The Web UI requires a category.
        tx_direction = x.direction or ("income" if x.amount >= 0 else "expense")
        category_type = tx_direction
    amount = abs(cents(x.amount)) if tx_direction == "income" else -abs(cents(x.amount))
    validate_splits(amount, x.splits)
    if x.recurring and not x.recurring_frequency:
        raise HTTPException(400, "Intervall für wiederkehrende Buchung fehlt")
    if x.recurring_until and x.recurring_until < x.booking_date:
        raise HTTPException(400, "Enddatum darf nicht vor dem Startdatum liegen")
    ts = iso(utcnow())
    with db.transaction() as c:
        recurring_id = None
        if x.recurring:
            kind = "income" if tx_direction == "income" else "direct_debit"
            name = clean_text(x.name, 160) or clean_text(x.payee, 200) or clean_text(x.note, 150) or "Wiederkehrende Buchung"
            rcur = c.execute(
                """INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)""",
                (x.account_id, x.category_id, name, amount, x.booking_date.isoformat(), x.recurring_frequency, kind, None, 1,
                 x.booking_date.isoformat(), x.booking_date.isoformat(), x.recurring_until.isoformat() if x.recurring_until else None, x.confidence, int(x.fixed_cost), ts),
            )
            recurring_id = rcur.lastrowid
            c.execute("UPDATE recurring SET interval_count=?,payee=? WHERE id=?", (x.recurring_interval_count, clean_text(x.payee,200), recurring_id))
            c.execute("UPDATE recurring SET series_id=? WHERE id=?", (recurring_id, recurring_id))
        initial_status = "planned" if x.recurring and x.booking_date > date.today() else "executed"
        cur = c.execute(
            """INSERT INTO transactions(account_id,amount,direction,booking_date,value_date,name,payee,note,category_id,status,external_id,recurring_id,confidence,fixed_cost,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (x.account_id, amount, tx_direction, x.booking_date.isoformat(), x.value_date.isoformat() if x.value_date else None,
             clean_text(x.name, 160) or clean_text(x.payee, 200) or "Buchung", clean_text(x.payee, 200), clean_text(x.note, 1000), x.category_id, initial_status,
             "manual-" + secrets.token_hex(16), recurring_id, x.confidence, int(x.fixed_cost), ts, ts),
        )
        write_tx_children(c, cur.lastrowid, x.tags, x.splits)
        generated_transactions=[]
        if recurring_id:
            c.execute(
                "INSERT OR REPLACE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,'executed',?)",
                (recurring_id, x.booking_date.isoformat(), cur.lastrowid, ts),
            )
            # A recurring transaction is a contract template plus journal rows:
            # materialise the rest of the finite contract immediately, or a
            # rolling 24-month horizon for an open-ended series. The explicitly
            # entered first row above already owns its occurrence and is not
            # duplicated by the materialiser.
            generated_transactions=_materialize_recurring_series(
                c, recurring_id, sess[1], from_day=max(date.today(), x.booking_date)
            )
        created_tx=tx_snapshot(c,cur.lastrowid)
        if x.remember_payee:
            remember_payee(c,x.payee)
        audit_append(c,sess[1],"transaction.create","transaction",cur.lastrowid,{"name":created_tx.get("name"),"added":audit_pick(created_tx,("name","amount","booking_date","value_date","account_name","payee","category_name","note","confidence","fixed_cost","tags"))})
        result={"id":cur.lastrowid,"recurring_id":recurring_id,"generated_transactions":len(generated_transactions)}
        client_mutation_store(c,request_id,endpoint,result)
        return result


@app.put("/api/transactions/{tx_id}")
def transaction_update(tx_id: int, x: TransactionIn, request: Request):
    sess=session(request, True)
    c0 = db.db()
    if x.category_id is not None:
        cat = c0.execute("SELECT direction FROM categories WHERE id=? AND active=1", (x.category_id,)).fetchone()
        if not cat:
            raise HTTPException(400, "Kategorie nicht gefunden")
        category_type = cat["direction"]
        tx_direction = "income" if category_type == "income" else "expense"
    else:
        tx_direction = x.direction or ("income" if x.amount >= 0 else "expense")
        category_type = tx_direction
    amount = abs(cents(x.amount)) if tx_direction == "income" else -abs(cents(x.amount))
    validate_splits(amount, x.splits)
    if x.recurring and not x.recurring_frequency:
        raise HTTPException(400, "Intervall für wiederkehrende Buchung fehlt")
    if x.recurring_until and x.recurring_until < x.booking_date:
        raise HTTPException(400, "Enddatum darf nicht vor dem Buchungsdatum liegen")
    with db.transaction() as c:
        before = tx_snapshot(c, tx_id)
        if before.get("transfer_id"):
            raise HTTPException(400,"Diese Buchung gehört zu einem Transfer. Bitte den Transfer gemeinsam bearbeiten.")
        c.execute(
            "INSERT INTO transaction_history(transaction_id,action,snapshot_json,changed_at) VALUES(?,?,?,?)",
            (tx_id, "update", json.dumps(before, ensure_ascii=False), iso(utcnow())),
        )
        c.execute(
            """UPDATE transactions SET account_id=?,amount=?,direction=?,booking_date=?,value_date=?,name=?,payee=?,note=?,category_id=?,status=?,confidence=?,fixed_cost=?,updated_at=?
               WHERE id=?""",
            (x.account_id, amount, tx_direction, x.booking_date.isoformat(), x.value_date.isoformat() if x.value_date else None,
             clean_text(x.name,160) or clean_text(x.payee,200) or "Buchung", clean_text(x.payee, 200), clean_text(x.note, 1000), x.category_id, "executed", x.confidence, int(x.fixed_cost), iso(utcnow()), tx_id),
        )
        write_tx_children(c, tx_id, x.tags, x.splits)

        existing_recurring_id = before.get("recurring_id")
        if x.recurring:
            kind = "income" if tx_direction == "income" else "direct_debit"
            name = clean_text(x.name, 160) or clean_text(x.payee, 200) or clean_text(x.note, 150) or "Wiederkehrende Buchung"
            effective = x.recurring_effective_from or x.booking_date
            valid_until = x.recurring_until.isoformat() if x.recurring_until else None
            if existing_recurring_id:
                linked = c.execute("SELECT * FROM recurring WHERE id=?", (existing_recurring_id,)).fetchone()
                if linked:
                    series_id = linked["series_id"] or linked["id"]
                    current = c.execute("SELECT * FROM recurring WHERE COALESCE(series_id,id)=? AND active=1 ORDER BY COALESCE(valid_from,next_date) DESC,id DESC LIMIT 1", (series_id,)).fetchone()
                    current_from = date.fromisoformat(current["valid_from"] or current["next_date"])
                    if effective <= current_from:
                        c.execute("""UPDATE recurring SET account_id=?,category_id=?,name=?,amount=?,frequency=?,kind=?,valid_from=?,valid_until=?,confidence=?,fixed_cost=? WHERE id=?""",
                                  (x.account_id,x.category_id,name,amount,x.recurring_frequency,kind,effective.isoformat(),valid_until,x.confidence,int(x.fixed_cost),current["id"]))
                        active_recurring_id = current["id"]
                    else:
                        c.execute("UPDATE recurring SET valid_until=? WHERE id=?", ((effective-timedelta(days=1)).isoformat(), current["id"]))
                        cur_r = c.execute("""INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at)
                                             VALUES(?,?,?,?,?,?,?,NULL,1,?,?,?,?,?,?,?)""",
                                          (x.account_id,x.category_id,name,amount,current["next_date"],x.recurring_frequency,kind,series_id,current["anchor_date"] or current["valid_from"] or current["next_date"],effective.isoformat(),valid_until,x.confidence,int(x.fixed_cost),iso(utcnow())))
                        active_recurring_id = cur_r.lastrowid
            else:
                cur_r = c.execute("""INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at)
                                     VALUES(?,?,?,?,?,?,?,NULL,1,NULL,?,?,?,?,?,?)""",
                                  (x.account_id,x.category_id,name,amount,x.booking_date.isoformat(),x.recurring_frequency,kind,x.booking_date.isoformat(),x.booking_date.isoformat(),valid_until,x.confidence,int(x.fixed_cost),iso(utcnow())))
                active_recurring_id = cur_r.lastrowid
                c.execute("UPDATE recurring SET series_id=? WHERE id=?", (active_recurring_id, active_recurring_id))
                c.execute("UPDATE transactions SET recurring_id=? WHERE id=?", (active_recurring_id, tx_id))
                c.execute("INSERT OR REPLACE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,'executed',?)",
                          (active_recurring_id,x.booking_date.isoformat(),tx_id,iso(utcnow())))

            if active_recurring_id:
                c.execute("UPDATE recurring SET interval_count=?,payee=? WHERE id=?", (x.recurring_interval_count, clean_text(x.payee,200), active_recurring_id))

            # Rebuild only the future/planned part of the contract. Executed
            # history remains untouched. This keeps the bookings journal in sync
            # immediately after editing a recurring transaction.
            series_id = int(series_id if existing_recurring_id and linked else active_recurring_id)
            rebuild_from=max(date.today(),effective)
            _remove_planned_series_transactions(c,series_id,rebuild_from)
            _materialize_recurring_series(c,series_id,sess[1],from_day=rebuild_from)
        after=tx_snapshot(c,tx_id)
        if x.remember_payee:
            remember_payee(c,x.payee)
        audit_fields=("name","amount","booking_date","value_date","account_name","payee","category_name","note","confidence","fixed_cost","tags","splits","status")
        audit_append(c,sess[1],"transaction.update","transaction",tx_id,{"name":after.get("name"),"changes":audit_changes(before,after,audit_fields),"current":audit_pick(after,audit_fields)})
    return {"ok": True}


@app.delete("/api/transactions/{tx_id}")
def transaction_delete(tx_id: int, request: Request, hard: bool = False):
    sess=session(request, True)
    with db.transaction() as c:
        before = tx_snapshot(c, tx_id)
        if before.get("transfer_id"):
            raise HTTPException(400,"Diese Buchung gehört zu einem Transfer. Bitte den Transfer gemeinsam stornieren/löschen.")
        c.execute(
            "INSERT INTO transaction_history(transaction_id,action,snapshot_json,changed_at) VALUES(?,?,?,?)",
            (tx_id, "delete" if hard else "cancel", json.dumps(before, ensure_ascii=False), iso(utcnow())),
        )
        audit_append(c,sess[1],"transaction.delete" if hard else "transaction.cancel","transaction",tx_id,{"snapshot":before})
        if hard:
            c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
        else:
            c.execute("UPDATE transactions SET status='cancelled',updated_at=? WHERE id=?", (iso(utcnow()), tx_id))
    return {"ok": True}


@app.get("/api/categories")
def categories(request: Request):
    session(request)
    return [dict(r) for r in db.db().execute("SELECT id,parent_id,name,direction FROM categories WHERE active=1 ORDER BY direction,name").fetchall()]


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    parent_id: int | None = None
    direction: str = 'expense'

    @field_validator('direction')
    @classmethod
    def direction_ok(cls, value):
        if value not in {'expense','income','savings'}:
            raise ValueError('Ungültiger Kategorietyp')
        return value


@app.post("/api/categories")
def category_create(x: CategoryIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        cur = c.execute("INSERT INTO categories(parent_id,name,direction) VALUES(?,?,?)", (x.parent_id, x.name.strip(), x.direction))
        audit_append(c,sess[1],"category.create","category",cur.lastrowid,{"name":x.name.strip(),"direction":x.direction})
        return {"id": cur.lastrowid}


def add_months(d: date, months: int = 1) -> date:
    index = d.year * 12 + d.month - 1 + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def next_occurrence(d: date, frequency: str, interval_count: int = 1) -> date:
    step=max(1,int(interval_count or 1))
    if frequency == "daily":
        return d + timedelta(days=step)
    if frequency == "weekly":
        return d + timedelta(weeks=step)
    if frequency == "monthly":
        return add_months(d,step)
    if frequency == "yearly":
        try:
            return d.replace(year=d.year + step)
        except ValueError:
            return d.replace(year=d.year + step, day=28)
    raise ValueError("frequency")


def occurrences(start: date, frequency: str, from_day: date, to_day: date, interval_count: int = 1):
    """Yield calendar-anchored occurrences for every N days/weeks/months/years.

    Month/year schedules always derive from the original anchor. A series
    started on the 31st therefore returns to the 31st after a short month.
    """
    if from_day > to_day:
        return
    step=max(1,int(interval_count or 1))
    if frequency in {"daily","weekly"}:
        step_days=step if frequency=="daily" else step*7
        delta=(from_day-start).days
        n=max(0,delta//step_days-1)
        while True:
            d=start+timedelta(days=n*step_days)
            if d>to_day:
                break
            if d>=from_day:
                yield d
            n+=1
        return
    if frequency == "monthly":
        diff=(from_day.year-start.year)*12+from_day.month-start.month
        n=max(0,diff//step-1)
        while True:
            d=add_months(start,n*step)
            if d>to_day:
                break
            if d>=from_day:
                yield d
            n+=1
        return
    if frequency == "yearly":
        diff=from_day.year-start.year
        n=max(0,diff//step-1)
        while True:
            target_year=start.year+n*step
            try:
                d=start.replace(year=target_year)
            except ValueError:
                d=start.replace(year=target_year,day=28)
            if d>to_day:
                break
            if d>=from_day:
                yield d
            n+=1
        return
    raise ValueError("frequency")

def _next_unexecuted_due(c, r, horizon_years: int = 10) -> date | None:
    start = date.fromisoformat(r["valid_from"] or r["next_date"])
    anchor = date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
    high = date.fromisoformat(r["valid_until"]) if r["valid_until"] else add_months(date.today(), horizon_years * 12)
    for due in occurrences(anchor,r["frequency"],start,high,int(r["interval_count"] or 1)):
        done = c.execute("SELECT 1 FROM recurring_occurrences WHERE recurring_id=? AND due_date=? AND status IN ('executed','skipped')", (r["id"], due.isoformat())).fetchone()
        if not done:
            return due
    return None

def recurring_rows_for_window(c, account_id: int | None, from_day: date, to_day: date):
    sql = "SELECT * FROM recurring WHERE active=1 AND COALESCE(valid_from,next_date)<=? AND (valid_until IS NULL OR valid_until>=?)"
    args = [to_day.isoformat(), from_day.isoformat()]
    if account_id is not None:
        sql += " AND account_id=?"; args.append(account_id)
    return c.execute(sql, args).fetchall()


def recurring_signed_amount(c, r, raw_amount: int | None = None) -> int:
    """Return the economic sign of a recurring amount, independent of legacy storage.

    Older HaushaltPro releases could leave direct-debit rows with a positive raw
    amount. Forecasts must never trust that legacy sign: category semantics win,
    then the recurring kind is used as a fallback. Savings behaves like an
    outflow for account balances while remaining a separate analysis category.
    """
    raw = int(r["amount"] if raw_amount is None else raw_amount)
    category_type = None
    if r["category_id"] is not None:
        cat = c.execute("SELECT direction FROM categories WHERE id=?", (r["category_id"],)).fetchone()
        if cat:
            category_type = cat["direction"]
    is_income = category_type == "income" or (category_type is None and r["kind"] == "income")
    return abs(raw) if is_income else -abs(raw)


def recurring_events(c, account_id: int | None, from_day: date, to_day: date):
    """Return unmaterialized recurring events with batched lookup tables.

    Forecast-heavy views call this helper repeatedly. The previous implementation
    queried occurrence state, overrides and category semantics for every due date,
    creating a severe N+1 pattern. All lookup data for the requested window is now
    loaded in bounded batches and the calendar loop itself performs no SQL.
    """
    rows=list(recurring_rows_for_window(c, account_id, from_day, to_day))
    if not rows or from_day > to_day:
        return []

    recurring_ids=sorted({int(r["id"]) for r in rows})
    series_ids=sorted({int(r["series_id"] or r["id"]) for r in rows})
    category_ids=sorted({int(r["category_id"]) for r in rows if r["category_id"] is not None})
    low_s,high_s=from_day.isoformat(),to_day.isoformat()

    def chunks(values, size=800):
        for i in range(0,len(values),size):
            yield values[i:i+size]

    done=set()
    for ids in chunks(recurring_ids):
        marks=",".join("?" for _ in ids)
        sql=("SELECT recurring_id,due_date FROM recurring_occurrences "
             "WHERE recurring_id IN ({}) AND due_date BETWEEN ? AND ? "
             "AND status IN ('executed','skipped')").format(marks)
        for x in c.execute(sql,[*ids,low_s,high_s]).fetchall():
            done.add((int(x["recurring_id"]),x["due_date"]))

    overrides={}
    for ids in chunks(series_ids):
        marks=",".join("?" for _ in ids)
        sql=("SELECT series_id,due_date,amount,note FROM recurring_overrides "
             "WHERE series_id IN ({}) AND due_date BETWEEN ? AND ?").format(marks)
        for x in c.execute(sql,[*ids,low_s,high_s]).fetchall():
            overrides[(int(x["series_id"]),x["due_date"])]=x

    category_direction={}
    for ids in chunks(category_ids):
        marks=",".join("?" for _ in ids)
        sql="SELECT id,direction FROM categories WHERE id IN ({})".format(marks)
        for x in c.execute(sql,ids).fetchall():
            category_direction[int(x["id"])]=x["direction"]

    def signed(r, raw_amount: int) -> int:
        raw=int(raw_amount)
        typ=category_direction.get(int(r["category_id"])) if r["category_id"] is not None else None
        is_income=typ=="income" or (typ is None and r["kind"]=="income")
        return abs(raw) if is_income else -abs(raw)

    events=[]
    for r in rows:
        valid_from=date.fromisoformat(r["valid_from"] or r["next_date"])
        valid_until=date.fromisoformat(r["valid_until"]) if r["valid_until"] else to_day
        low=max(from_day,valid_from); high=min(to_day,valid_until)
        if low>high:
            continue
        anchor=date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
        recurring_id=int(r["id"]); series_id=int(r["series_id"] or r["id"])
        base_amount=signed(r,int(r["amount"]))
        for d in occurrences(anchor,r["frequency"],low,high,int(r["interval_count"] or 1)):
            due=d.isoformat()
            if (recurring_id,due) in done:
                continue
            override=overrides.get((series_id,due))
            raw_amount=int(override["amount"]) if override else int(r["amount"])
            events.append({"date":d,"amount":signed(r,raw_amount),"base_amount":base_amount,
                           "overridden":bool(override),"override_note":override["note"] if override else None,
                           "name":r["name"],"account_id":r["account_id"],"kind":r["kind"],
                           "recurring_id":recurring_id,"series_id":series_id})
    return events


def _materialize_recurring_window(c, from_day: date, to_day: date, user_id: int | None = None, series_id: int | None = None) -> list[dict]:
    """Create journal rows for recurring occurrences in a time window.

    Recurring occurrences are stored immediately as ``planned`` transactions so
    the bookings view can show the complete contract schedule without pretending
    that future or merely due payments are already settled.  The occurrence marker
    is consumed, so forecasts never add the same recurring amount a second time.
    ``series_id`` limits synchronization to one recurring contract.
    """
    if from_day > to_day:
        return []
    created=[]

    # A newly defined series must never auto-backfill occurrences from before
    # that definition/version was created. Mark such historical open dates as
    # skipped so the recurring overview advances, while leaving the planning
    # model itself untouched for reports that intentionally inspect history.
    for r in c.execute("SELECT * FROM recurring WHERE active=1").fetchall():
        if series_id is not None and int(r["series_id"] or r["id"]) != int(series_id):
            continue
        try:
            created_day=min(date.today(),date.fromisoformat(str(r["created_at"])[:10]))
        except (TypeError,ValueError):
            continue
        valid_from=date.fromisoformat(r["valid_from"] or r["next_date"])
        if valid_from >= created_day:
            continue
        valid_until=date.fromisoformat(r["valid_until"]) if r["valid_until"] else created_day-timedelta(days=1)
        high=min(valid_until,created_day-timedelta(days=1))
        if valid_from>high:
            continue
        anchor=date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
        ts=iso(utcnow())
        for due in occurrences(anchor,r["frequency"],valid_from,high,int(r["interval_count"] or 1)):
            c.execute(
                "INSERT OR IGNORE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,NULL,'skipped',?)",
                (r["id"],due.isoformat(),ts),
            )

    for ev in sorted(recurring_events(c, None, from_day, to_day), key=lambda x:(x["date"],x["recurring_id"])):
        if series_id is not None and int(ev["series_id"]) != int(series_id):
            continue
        due=ev["date"]
        recurring_id=int(ev["recurring_id"])
        r=c.execute("SELECT * FROM recurring WHERE id=? AND active=1",(recurring_id,)).fetchone()
        if not r:
            continue
        external_id=f"rec-{recurring_id}-{due.isoformat()}"
        existing=c.execute("SELECT id,status FROM transactions WHERE account_id=? AND external_id=?",(r["account_id"],external_id)).fetchone()
        ts=iso(utcnow())

        # Never backfill a transaction for a due date that predates creation of
        # this recurring definition/version.  This is especially important when
        # a user accidentally enters an already-past date as the "next open
        # occurrence": the series should move on, not invent historical book
        # entries.  Marking it skipped also keeps forecasts from counting the
        # missed occurrence later.
        created_day=min(date.today(),date.fromisoformat(str(r["created_at"])[:10])) if r["created_at"] else due
        if due < created_day and not existing:
            c.execute(
                "INSERT OR IGNORE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,NULL,'skipped',?)",
                (recurring_id,due.isoformat(),ts),
            )
            continue
        if existing:
            occurrence_status="skipped" if existing["status"]=="cancelled" else "executed"
            c.execute("INSERT OR IGNORE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,?,?)",
                      (recurring_id,due.isoformat(),existing["id"],occurrence_status,ts))
            continue
        amount=int(ev["amount"])
        transaction_status="planned"
        cur=c.execute(
            """INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,note,category_id,status,external_id,recurring_id,confidence,fixed_cost,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["account_id"],amount,"income" if amount>=0 else "expense",due.isoformat(),r["name"],r["payee"] or r["name"],
             ev.get("override_note"),r["category_id"],transaction_status,external_id,recurring_id,r["confidence"] or "fixed",int(r["fixed_cost"] or 0),ts,ts),
        )
        c.execute("INSERT INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,'executed',?)",
                  (recurring_id,due.isoformat(),cur.lastrowid,ts))
        created.append({"transaction_id":cur.lastrowid,"recurring_id":recurring_id,"due_date":due.isoformat(),"amount":euros(amount)})
    return created


RECURRING_OPEN_ENDED_MONTHS = 24


def _recurring_contract_end(r, reference: date | None = None) -> date:
    """Return the materialisation horizon for one recurring version.

    Finite contracts are materialised through their real end date.  Open-ended
    series get a rolling 24-month journal horizon; browsing later months can
    extend that horizon without changing the recurring definition.
    """
    if r["valid_until"]:
        return date.fromisoformat(r["valid_until"])
    start = date.fromisoformat(r["valid_from"] or r["next_date"])
    base = max(reference or date.today(), start)
    return add_months(base, RECURRING_OPEN_ENDED_MONTHS)-timedelta(days=1)


def _remove_planned_series_transactions(c, series_id: int, from_day: date) -> int:
    """Remove only future/planned generated rows for a recurring series.

    Executed history is intentionally immutable here.  This lets editing or
    stopping a contract rebuild its future schedule without rewriting what has
    already become part of the real household journal.
    """
    rows=c.execute("""SELECT t.id
                      FROM transactions t JOIN recurring r ON r.id=t.recurring_id
                      WHERE COALESCE(r.series_id,r.id)=? AND t.status='planned'
                        AND t.booking_date>=?""",(series_id,from_day.isoformat())).fetchall()
    ids=[int(r["id"]) for r in rows]
    if not ids:
        return 0
    marks=','.join('?' for _ in ids)
    c.execute("DELETE FROM recurring_occurrences WHERE transaction_id IN (" + marks + ")",ids)
    c.execute("DELETE FROM transactions WHERE id IN (" + marks + ")",ids)
    return len(ids)


def _materialize_recurring_series(c, series_id: int, user_id: int | None = None, from_day: date | None = None) -> list[dict]:
    versions=c.execute("""SELECT * FROM recurring
                          WHERE COALESCE(series_id,id)=? AND active=1
                          ORDER BY COALESCE(valid_from,next_date),id""",(series_id,)).fetchall()
    if not versions:
        return []
    low=from_day or min(date.fromisoformat(r["valid_from"] or r["next_date"]) for r in versions)
    high=max(_recurring_contract_end(r,low) for r in versions)
    return _materialize_recurring_window(c,low,high,user_id,series_id=series_id)


def _next_scheduled_due(r, from_day: date | None = None) -> date | None:
    """Next contractual date, regardless of whether its journal row already exists."""
    from_day=from_day or date.today()
    valid_from=date.fromisoformat(r["valid_from"] or r["next_date"])
    valid_until=date.fromisoformat(r["valid_until"]) if r["valid_until"] else _recurring_contract_end(r,from_day)
    low=max(valid_from,from_day)
    if low>valid_until:
        return None
    anchor=date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
    return next(occurrences(anchor,r["frequency"],low,valid_until,int(r["interval_count"] or 1)),None)


@app.post("/api/recurring/materialize-due")
def recurring_materialize_due(request: Request, month: str | None = None, year: int | None = None):
    sess=session(request, True)
    today=date.today()
    if month:
        start,end=month_bounds(month)
        through=end
        with db.transaction() as c:
            items=_materialize_recurring_window(c,start,through,sess[1])
        return {"created":len(items),"items":items,"through":through.isoformat(),"scope":"month"}
    if year is not None:
        if year < 1970 or year > 2200:
            raise HTTPException(400,"Ungültiges Jahr")
        start,end=date(year,1,1),date(year,12,31)
        with db.transaction() as c:
            items=_materialize_recurring_window(c,start,end,sess[1])
        return {"created":len(items),"items":items,"through":end.isoformat(),"scope":"year"}

    # No period means: synchronize every active contract into the journal.
    # This is used on app startup so existing series from older versions get
    # the same future-journal representation as newly created contracts.
    with db.transaction() as c:
        series_ids=[int(r[0]) for r in c.execute("SELECT DISTINCT COALESCE(series_id,id) FROM recurring WHERE active=1").fetchall()]
        items=[]
        for sid in series_ids:
            versions=c.execute("SELECT * FROM recurring WHERE COALESCE(series_id,id)=? AND active=1",(sid,)).fetchall()
            if not versions:
                continue
            first_future=max(today,min(date.fromisoformat(r["valid_from"] or r["next_date"]) for r in versions))
            items.extend(_materialize_recurring_series(c,sid,sess[1],from_day=first_future))
        horizons=[_recurring_contract_end(r,today) for r in c.execute("SELECT * FROM recurring WHERE active=1").fetchall()]
    return {"created":len(items),"items":items,"through":max(horizons).isoformat() if horizons else today.isoformat(),"scope":"all"}


@app.get("/api/recurring")
def recurring(request: Request):
    session(request)
    today = date.today()
    c = db.db()
    all_rows = c.execute("SELECT * FROM recurring WHERE active=1 ORDER BY COALESCE(series_id,id),COALESCE(valid_from,next_date),id").fetchall()
    grouped: dict[int, list] = defaultdict(list)
    for r in all_rows:
        grouped[int(r["series_id"] or r["id"])].append(r)
    out=[]
    for series_id, versions in grouped.items():
        # Pick the version that owns the next actually open occurrence. A version can be
        # valid "today" but have no occurrence inside its own validity window (for example
        # after a future version was created). In that case the series must not disappear;
        # the next valid future version is shown instead.
        due_candidates=[]
        for version in versions:
            due=_next_scheduled_due(version)
            if due is not None:
                due_candidates.append((due,version))
        if not due_candidates:
            continue
        due,r=min(due_candidates,key=lambda x:(x[0],x[1]["valid_from"] or x[1]["next_date"],x[1]["id"]))
        item=dict(r); item["next_date"]=due.isoformat(); item["amount"]=euros(recurring_signed_amount(c, r)); item["max_amount"]=euros(item["max_amount"]) if item["max_amount"] is not None else None
        item["status"]="overdue" if due<today else "planned"
        item["series_id"]=int(r["series_id"] or r["id"])
        item["first_date"]=min((v["valid_from"] or v["next_date"] for v in versions),default=r["next_date"])
        # A newly created future series is not a "future change". Only later versions of an
        # already established series should get that marker.
        selected_from=date.fromisoformat(r["valid_from"] or r["next_date"])
        later_versions=[v for v in versions if int(v["id"])!=int(r["id"]) and date.fromisoformat(v["valid_from"] or v["next_date"])>selected_from]
        item["future_change_from"]=min((v["valid_from"] or v["next_date"] for v in later_versions),default=None)
        executed=c.execute("""SELECT COUNT(*)
                              FROM recurring_occurrences o
                              JOIN recurring rr ON rr.id=o.recurring_id
                              JOIN transactions t ON t.id=o.transaction_id
                              WHERE COALESCE(rr.series_id,rr.id)=?
                                AND o.status='executed' AND t.status<>'cancelled'""",
                           (item["series_id"],)).fetchone()[0]
        item["journal_count"]=int(executed or 0)
        item["executed_count"]=item["journal_count"]
        out.append(item)
    return sorted(out,key=lambda x:(x["next_date"],x["name"]))


@app.post("/api/recurring")
def recurring_create(x: RecurringIn, request: Request):
    sess=session(request, True)
    request_id=client_request_id(request);endpoint="POST /api/recurring"
    c0=db.db()
    replay=client_mutation_replay(c0,request_id,endpoint)
    if replay is not None:
        return replay
    cat=c0.execute("SELECT direction FROM categories WHERE id=? AND active=1",(x.category_id,)).fetchone() if x.category_id else None
    kind = "income" if cat and cat["direction"]=="income" else x.kind
    if cat and cat["direction"] in {"expense","savings"}: kind="direct_debit"
    amount = abs(cents(x.amount)) if kind == "income" else -abs(cents(x.amount))
    max_amount = cents(x.max_amount) if x.max_amount is not None else None
    if max_amount is not None and abs(amount) > abs(max_amount): raise HTTPException(400, "Betrag überschreitet das Maximallimit")
    with db.transaction() as c:
        cur = c.execute("INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at) VALUES(?,?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)",
            (x.account_id,x.category_id,x.name.strip(),amount,x.next_date.isoformat(),x.frequency,kind,max_amount,int(x.active),x.next_date.isoformat(),x.next_date.isoformat(),x.valid_until.isoformat() if x.valid_until else None,x.confidence,int(x.fixed_cost),iso(utcnow())))
        c.execute("UPDATE recurring SET series_id=? WHERE id=?",(cur.lastrowid,cur.lastrowid))
        c.execute("UPDATE recurring SET interval_count=?,payee=? WHERE id=?",(x.interval_count,clean_text(x.payee,200),cur.lastrowid))
        created=recurring_snapshot(c,cur.lastrowid)
        generated=_materialize_recurring_series(c,cur.lastrowid,sess[1],from_day=max(date.today(),x.next_date)) if x.active else []
        audit_append(c,sess[1],"recurring.create","recurring",cur.lastrowid,{"name":created.get("name"),"added":audit_pick(created,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_until","confidence","fixed_cost","max_amount")),"generated_transactions":len(generated)})
        result={"id":cur.lastrowid,"generated_transactions":len(generated)}
        client_mutation_store(c,request_id,endpoint,result)
        return result


@app.put("/api/recurring/{recurring_id}")
def recurring_update(recurring_id: int, x: RecurringUpdateIn, request: Request):
    sess=session(request, True)
    c0=db.db()
    cat=c0.execute("SELECT direction FROM categories WHERE id=? AND active=1",(x.category_id,)).fetchone() if x.category_id else None
    kind = "income" if cat and cat["direction"]=="income" else x.kind
    if cat and cat["direction"] in {"expense","savings"}: kind="direct_debit"
    amount = abs(cents(x.amount)) if kind == "income" else -abs(cents(x.amount))
    max_amount = cents(x.max_amount) if x.max_amount is not None else None
    if max_amount is not None and abs(amount)>abs(max_amount): raise HTTPException(400,"Betrag überschreitet das Maximallimit")
    with db.transaction() as c:
        old=c.execute("SELECT * FROM recurring WHERE id=? AND active=1",(recurring_id,)).fetchone()
        if not old: raise HTTPException(404,"Wiederholungsserie nicht gefunden")
        before=recurring_snapshot(c,recurring_id)
        effective=x.effective_from
        old_from=date.fromisoformat(old["valid_from"] or old["next_date"])
        if effective <= old_from:
            c.execute("UPDATE recurring SET account_id=?,category_id=?,name=?,amount=?,next_date=?,frequency=?,interval_count=?,kind=?,max_amount=?,anchor_date=?,valid_from=?,valid_until=?,confidence=?,fixed_cost=? WHERE id=?",
                (x.account_id,x.category_id,x.name.strip(),amount,x.next_date.isoformat(),x.frequency,x.interval_count,kind,max_amount,x.next_date.isoformat(),effective.isoformat(),x.valid_until.isoformat() if x.valid_until else None,x.confidence,int(x.fixed_cost),recurring_id))
            c.execute("UPDATE recurring SET payee=? WHERE id=?",(clean_text(x.payee,200),recurring_id))
            series_id=int(old["series_id"] or old["id"])
            _remove_planned_series_transactions(c,series_id,effective)
            generated=_materialize_recurring_series(c,series_id,sess[1],from_day=max(date.today(),effective))
            after=recurring_snapshot(c,recurring_id)
            audit_append(c,sess[1],"recurring.update","recurring",recurring_id,{"name":after.get("name"),"changes":audit_changes(before,after,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_from","valid_until","confidence","fixed_cost","max_amount")),"current":audit_pick(after,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_from","valid_until","confidence","fixed_cost","max_amount")),"effective_from":effective.isoformat(),"versioned":False,"generated_transactions":len(generated)})
            return {"ok":True,"id":recurring_id,"versioned":False,"generated_transactions":len(generated)}
        c.execute("UPDATE recurring SET valid_until=? WHERE id=?",((effective-timedelta(days=1)).isoformat(),recurring_id))
        cur=c.execute("INSERT INTO recurring(account_id,category_id,name,amount,next_date,frequency,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (x.account_id,x.category_id,x.name.strip(),amount,x.next_date.isoformat(),x.frequency,kind,max_amount,1,old["series_id"] or old["id"],x.next_date.isoformat(),effective.isoformat(),x.valid_until.isoformat() if x.valid_until else None,x.confidence,int(x.fixed_cost),iso(utcnow())))
        series_id=int(old["series_id"] or old["id"])
        c.execute("UPDATE recurring SET interval_count=?,payee=? WHERE id=?",(x.interval_count,clean_text(x.payee,200),cur.lastrowid))
        _remove_planned_series_transactions(c,series_id,effective)
        generated=_materialize_recurring_series(c,series_id,sess[1],from_day=max(date.today(),effective))
        new_version=recurring_snapshot(c,cur.lastrowid)
        audit_append(c,sess[1],"recurring.version","recurring",cur.lastrowid,{"name":new_version.get("name"),"series_id":series_id,"changes":audit_changes(before,new_version,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_from","valid_until","confidence","fixed_cost","max_amount")),"current":audit_pick(new_version,("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_from","valid_until","confidence","fixed_cost","max_amount")),"effective_from":effective.isoformat(),"generated_transactions":len(generated)})
        return {"ok":True,"id":cur.lastrowid,"versioned":True,"generated_transactions":len(generated)}


@app.put("/api/recurring/{recurring_id}/override")
def recurring_override(recurring_id: int, x: RecurringOverrideIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        row = c.execute("SELECT id,series_id,kind,valid_from,valid_until,next_date FROM recurring WHERE id=?", (recurring_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Wiederholungsserie nicht gefunden")
        series_id = row["series_id"] or row["id"]
        # Make sure the requested date is an actual occurrence of some version in this series.
        versions = c.execute("SELECT * FROM recurring WHERE COALESCE(series_id,id)=? ORDER BY COALESCE(valid_from,next_date)", (series_id,)).fetchall()
        matching = None
        for version in versions:
            vf = date.fromisoformat(version["valid_from"] or version["next_date"])
            vu = date.fromisoformat(version["valid_until"]) if version["valid_until"] else x.due_date
            if vf <= x.due_date <= vu:
                anchor = date.fromisoformat(version["anchor_date"] or version["valid_from"] or version["next_date"])
                for occurrence in occurrences(anchor,version["frequency"],x.due_date,x.due_date,int(version["interval_count"] or 1)):
                    if occurrence == x.due_date:
                        matching = version
                        break
            if matching:
                break
        if not matching:
            raise HTTPException(400, "Für dieses Datum existiert kein Termin der Serie")
        amount = recurring_signed_amount(c, matching, cents(x.amount))
        prior_override=c.execute("SELECT amount,note FROM recurring_overrides WHERE series_id=? AND due_date=?",(series_id,x.due_date.isoformat())).fetchone()
        ts = iso(utcnow())
        c.execute("""INSERT INTO recurring_overrides(series_id,due_date,amount,note,created_at,updated_at) VALUES(?,?,?,?,?,?)
                     ON CONFLICT(series_id,due_date) DO UPDATE SET amount=excluded.amount,note=excluded.note,updated_at=excluded.updated_at""",
                  (series_id, x.due_date.isoformat(), amount, x.note, ts, ts))

        # If this occurrence was already materialised as a real transaction (for
        # example the first recurring salary created from the transaction form),
        # a month-only override must update that transaction as well. Otherwise
        # dashboards/reports would keep the original series amount while the
        # override table contains the corrected value.
        materialised=c.execute("""SELECT o.transaction_id,o.recurring_id
                                  FROM recurring_occurrences o
                                  JOIN recurring r ON r.id=o.recurring_id
                                  WHERE COALESCE(r.series_id,r.id)=? AND o.due_date=?
                                    AND o.status='executed' AND o.transaction_id IS NOT NULL
                                  ORDER BY o.id DESC LIMIT 1""",
                               (series_id,x.due_date.isoformat())).fetchone()
        if materialised:
            tx_before=tx_snapshot(c,int(materialised["transaction_id"]))
            c.execute("INSERT INTO transaction_history(transaction_id,action,snapshot_json,changed_at) VALUES(?,?,?,?)",
                      (materialised["transaction_id"],"recurring_override",json.dumps(tx_before,ensure_ascii=False),ts))
            c.execute("UPDATE transactions SET amount=?,direction=?,updated_at=? WHERE id=?",
                      (amount,"income" if amount>=0 else "expense",ts,materialised["transaction_id"]))

        details={"series_id":series_id,"due_date":x.due_date.isoformat()}
        if materialised:
            details["transaction_id"]=int(materialised["transaction_id"])
        current_override={"amount":amount,"note":clean_text(x.note,300)}
        if prior_override:
            details["changes"]=audit_changes(dict(prior_override),current_override,("amount","note"))
        else:
            details["added"]=current_override
        audit_append(c,sess[1],"recurring.override","recurring",recurring_id,details)
    return {"ok": True, "series_id": series_id, "due_date": x.due_date.isoformat(), "amount": euros(amount)}


@app.delete("/api/recurring/{recurring_id}/override")
def recurring_override_delete(recurring_id: int, due_date: date, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        row = c.execute("SELECT id,series_id FROM recurring WHERE id=?", (recurring_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Wiederholungsserie nicht gefunden")
        series_id = row["series_id"] or row["id"]
        prior=c.execute("SELECT amount,note FROM recurring_overrides WHERE series_id=? AND due_date=?",(series_id,due_date.isoformat())).fetchone()
        c.execute("DELETE FROM recurring_overrides WHERE series_id=? AND due_date=?", (series_id, due_date.isoformat()))

        # Revert an already materialised occurrence to the base amount of the
        # series version that owns this due date.
        versions=c.execute("SELECT * FROM recurring WHERE COALESCE(series_id,id)=? ORDER BY COALESCE(valid_from,next_date)",(series_id,)).fetchall()
        matching=None
        for version in versions:
            vf=date.fromisoformat(version["valid_from"] or version["next_date"])
            vu=date.fromisoformat(version["valid_until"]) if version["valid_until"] else due_date
            if vf<=due_date<=vu:
                anchor=date.fromisoformat(version["anchor_date"] or version["valid_from"] or version["next_date"])
                if any(occ==due_date for occ in occurrences(anchor,version["frequency"],due_date,due_date,int(version["interval_count"] or 1))):
                    matching=version; break
        materialised=c.execute("""SELECT o.transaction_id FROM recurring_occurrences o
                                  JOIN recurring r ON r.id=o.recurring_id
                                  WHERE COALESCE(r.series_id,r.id)=? AND o.due_date=?
                                    AND o.status='executed' AND o.transaction_id IS NOT NULL
                                  ORDER BY o.id DESC LIMIT 1""",
                               (series_id,due_date.isoformat())).fetchone()
        if prior and matching and materialised:
            base_amount=recurring_signed_amount(c,matching)
            ts=iso(utcnow())
            tx_before=tx_snapshot(c,int(materialised["transaction_id"]))
            c.execute("INSERT INTO transaction_history(transaction_id,action,snapshot_json,changed_at) VALUES(?,?,?,?)",
                      (materialised["transaction_id"],"recurring_override_delete",json.dumps(tx_before,ensure_ascii=False),ts))
            c.execute("UPDATE transactions SET amount=?,direction=?,updated_at=? WHERE id=?",
                      (base_amount,"income" if base_amount>=0 else "expense",ts,materialised["transaction_id"]))
        details={"series_id":series_id,"due_date":due_date.isoformat()}
        if materialised: details["transaction_id"]=int(materialised["transaction_id"])
        audit_append(c,sess[1],"recurring.override.delete","recurring",recurring_id,details)
    return {"ok": True}


@app.post("/api/recurring/{recurring_id}/execute")
def recurring_execute(recurring_id: int, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        r = c.execute("SELECT * FROM recurring WHERE id=? AND active=1", (recurring_id,)).fetchone()
        if not r:
            raise HTTPException(404, "Wiederholungsserie nicht gefunden")
        due = _next_scheduled_due(r)
        if due is None:
            raise HTTPException(400, "Kein weiterer Serientermin vorhanden")
        existing=c.execute("SELECT id,booking_date FROM transactions WHERE recurring_id=? AND booking_date=? AND status<>'cancelled'",(recurring_id,due.isoformat())).fetchone()
        if existing:
            c.execute("UPDATE transactions SET status='executed',updated_at=? WHERE id=?",(iso(utcnow()),existing["id"]))
            audit_append(c,sess[1],"recurring.execute","recurring",recurring_id,{"transaction_id":int(existing["id"]),"due_date":existing["booking_date"],"already_materialized":True})
            return {"transaction_id":int(existing["id"]),"due_date":existing["booking_date"],"already_materialized":True}
        ts = iso(utcnow())
        series_id = r["series_id"] or r["id"]
        override = c.execute("SELECT amount FROM recurring_overrides WHERE series_id=? AND due_date=?", (series_id, due.isoformat())).fetchone()
        raw_booked_amount = int(override["amount"]) if override else int(r["amount"]); booked_amount = recurring_signed_amount(c, r, raw_booked_amount)
        cur = c.execute(
            """INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,note,category_id,status,external_id,recurring_id,confidence,fixed_cost,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["account_id"], booked_amount, "income" if r["kind"]=="income" else "expense", due.isoformat(), r["name"], r["payee"] or r["name"], "Aus wiederkehrender Buchung", r["category_id"],
             "executed", f"rec-{recurring_id}-{due.isoformat()}", recurring_id, r["confidence"] or "fixed", int(r["fixed_cost"] or 0), ts, ts),
        )
        c.execute(
            "INSERT OR REPLACE INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(?,?,?,'executed',?)",
            (recurring_id, due.isoformat(), cur.lastrowid, ts),
        )
        audit_append(c,sess[1],"recurring.execute","recurring",recurring_id,{"transaction_id":cur.lastrowid,"due_date":due.isoformat(),"amount":booked_amount})
        return {"transaction_id": cur.lastrowid, "due_date": due.isoformat()}


@app.delete("/api/recurring/{recurring_id}")
def recurring_delete(recurring_id: int, request: Request, hard: bool = False):
    sess=session(request, True)
    with db.transaction() as c:
        row = c.execute("SELECT id,series_id FROM recurring WHERE id=?", (recurring_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Wiederholungsserie nicht gefunden")
        series_id = row["series_id"] or row["id"]
        before=recurring_snapshot(c,recurring_id)
        versions=int(c.execute("SELECT COUNT(*) FROM recurring WHERE COALESCE(series_id,id)=?",(series_id,)).fetchone()[0])
        # Future planned journal rows are part of the contract schedule, not immutable
        # history.  Stopping/deleting a series removes those rows while preserving
        # already executed past/today transactions.
        removed_planned=_remove_planned_series_transactions(c,int(series_id),date.today())
        if hard:
            c.execute("DELETE FROM recurring_overrides WHERE series_id=?", (series_id,))
            c.execute("DELETE FROM recurring WHERE COALESCE(series_id,id)=?", (series_id,))
        else:
            c.execute("UPDATE recurring SET active=0 WHERE COALESCE(series_id,id)=?", (series_id,))
        fields=("name","payee","amount","next_date","frequency","interval_count","account_name","category_name","valid_from","valid_until","confidence","fixed_cost")
        audit_append(c,sess[1],"recurring.delete" if hard else "recurring.stop","recurring",recurring_id,{"series_id":series_id,"versions":versions,"removed_planned_transactions":removed_planned,"snapshot":audit_pick(before,fields)})
    return {"ok": True, "hard": hard}


def forecast_for_account(c, aid: int, horizon: int) -> dict:
    today = date.today()
    end = today + timedelta(days=horizon)
    running = account_balance(c, aid, today)
    events: dict[date, int] = defaultdict(int)
    tx_rows = c.execute(
        """SELECT CASE WHEN direction='expense' THEN -ABS(amount) WHEN direction='income' THEN ABS(amount) ELSE amount END amount,booking_date,status FROM transactions
           WHERE account_id=? AND status<>'cancelled' AND booking_date>=? AND booking_date<=?""",
        (aid, today.isoformat(), end.isoformat()),
    ).fetchall()
    for r in tx_rows:
        d = date.fromisoformat(r["booking_date"])
        if r["status"] == "executed" and d == today:
            continue
        events[d] += int(r["amount"])
    for ev in recurring_events(c,aid,today,end):
        events[ev["date"]] += ev["amount"]
    points = []
    for offset in range(horizon + 1):
        d = today + timedelta(days=offset)
        running += events.get(d, 0)
        points.append({"date": d.isoformat(), "balance": euros(running)})
    return {"balance": euros(account_balance(c, aid, today)), "forecast": points}


@app.get('/api/dashboard')
def dashboard(request: Request, month: str | None = None):
    session(request)
    cache_key=month or date.today().strftime('%Y-%m');cached=_cache_get('dashboard',cache_key,ttl=20)
    if cached is not None:return cached
    c = db.db()
    today = date.today()
    start, month_end = month_bounds(month)
    selected_month = start.strftime('%Y-%m')
    cutoff_day = min(today.day, month_end.day)
    cutoff = date(start.year, start.month, cutoff_day)
    account_rows = c.execute('SELECT id,name,currency,start_date FROM accounts WHERE active=1 AND start_date<=? ORDER BY name',(month_end.isoformat(),)).fetchall()
    accounts_out = []
    total_series = defaultdict(float)
    total_opening_balance = 0.0
    total_balance_cents = 0
    for a in account_rows:
        series = monthly_account_series(c, a['id'], selected_month)
        by_date={p['date']:p['balance'] for p in series}
        opening=float(series[0]['opening_balance']) if series else euros(_month_opening_balance(c,a['id'],start))
        metrics={'month_start_balance':opening,'balance':by_date.get(cutoff.isoformat(),opening),
                 'month_end_balance':by_date.get(month_end.isoformat(),opening),'balance_cutoff':cutoff.isoformat()}
        total_balance_cents += cents(metrics['balance'])
        for p in series:
            total_series[p['date']] += p['balance']
            if p.get('opening_balance') is not None:
                total_opening_balance += float(p['opening_balance'])
        accounts_out.append({'id': a['id'], 'name': a['name'], 'currency': a['currency'], **metrics, 'forecast': series})

    # All dashboard month-relative values use the same calendar-day cutoff as
    # account_month_metrics(): if today is the 10th and December is selected,
    # the cutoff is 10 December. "Ausstehend" and "Nächste Zahlungen" start
    # after that cutoff and end at the selected month's final day.
    remaining_start = cutoff + timedelta(days=1)

    pending_outflows = 0
    pending_inflows = 0
    amap={r["id"]:r["name"] for r in c.execute("SELECT id,name FROM accounts WHERE active=1").fetchall()}

    # "Ausstehend bis Monatsende" intentionally follows the selected-month
    # cutoff used by the account cards. This is a what-if value for that month.
    if remaining_start <= month_end:
        for ev in recurring_events(c,None,remaining_start,month_end):
            amount = int(ev["amount"])
            if amount < 0: pending_outflows += abs(amount)
            elif amount > 0: pending_inflows += amount
        for r in c.execute("""SELECT CASE WHEN t.direction='expense' THEN -ABS(t.amount) WHEN t.direction='income' THEN ABS(t.amount) ELSE t.amount END amount
                     FROM transactions t
                     WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
                     (remaining_start.isoformat(),month_end.isoformat())).fetchall():
            amount = int(r["amount"])
            if amount < 0: pending_outflows += abs(amount)
            elif amount > 0: pending_inflows += amount

    # "Nächste Zahlungen" is different: it answers what is actually still in
    # the future from the real current date. Selecting a future month must not
    # hide its 1st..today.day payments merely because the account card uses a
    # synthetic same-day cutoff for comparison.
    next_payments=[]
    if month_end >= today:
        upcoming_start = max(start, today + timedelta(days=1))
        if upcoming_start <= month_end:
            for ev in recurring_events(c,None,upcoming_start,month_end):
                amount = int(ev["amount"])
                next_payments.append({"date":ev["date"].isoformat(),"name":ev["name"],"amount":euros(amount),"account_name":amap.get(ev["account_id"],"?"),"source":"recurring"})
            for r in c.execute("""SELECT t.booking_date date,COALESCE(t.payee,'Buchung') name,
                         CASE WHEN t.direction='expense' THEN -ABS(t.amount) WHEN t.direction='income' THEN ABS(t.amount) ELSE t.amount END amount,a.name account_name
                         FROM transactions t JOIN accounts a ON a.id=t.account_id
                         WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
                         (upcoming_start.isoformat(),month_end.isoformat())).fetchall():
                next_payments.append({"date":r["date"],"name":r["name"],"amount":euros(int(r["amount"])),"account_name":r["account_name"],"source":"transaction"})
            for r in c.execute("""SELECT tr.booking_date date,tr.name,tr.amount,fa.name from_name,ta.name to_name
                                  FROM transfers tr JOIN accounts fa ON fa.id=tr.from_account_id JOIN accounts ta ON ta.id=tr.to_account_id
                                  WHERE tr.active=1 AND tr.booking_date>=? AND tr.booking_date<=?""",
                               (upcoming_start.isoformat(),month_end.isoformat())).fetchall():
                next_payments.append({"date":r["date"],"name":f"{r['name']}: {r['from_name']} → {r['to_name']}","amount":euros(-int(r["amount"])),"account_name":r["from_name"],"source":"transfer"})
    next_payments=sorted(next_payments,key=lambda x:(x["date"],x["name"]))[:50]

    # Analysis is split deliberately into two concepts:
    # 1) actual values through the selected calendar-day cutoff ("bis heute")
    # 2) full-month planned totals, which include future manual bookings and
    #    recurring events. The daily averages use (2), so an income entered for
    #    later in the month is visible immediately instead of showing 0 EUR/day.
    booked_income = booked_expense = booked_savings = 0
    rows = c.execute("""SELECT t.amount,t.direction,COALESCE(c.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) category_type
                        FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
                        WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
                     (start.isoformat(),cutoff.isoformat())).fetchall()
    for r in rows:
        value=abs(int(r['amount']))
        typ=r['category_type']
        if typ == 'income': booked_income += value
        elif typ == 'savings': booked_savings += value
        else: booked_expense += value

    # Fällige, noch nicht als Transaktion erzeugte Serien gehören für die
    # Monatsansicht ebenfalls zu "bis heute". Ausgeführte Vorkommen werden
    # von recurring_events() unterdrückt und daher nicht doppelt gezählt.
    recurring_type_by_id = {
        int(r['id']): r['category_type']
        for r in c.execute("""SELECT r.id,COALESCE(cat.direction,CASE WHEN r.amount>=0 THEN 'income' ELSE 'expense' END) category_type
                              FROM recurring r LEFT JOIN categories cat ON cat.id=r.category_id""").fetchall()
    }
    for ev in recurring_events(c, None, start, cutoff):
        value = abs(int(ev['amount']))
        typ = recurring_type_by_id.get(int(ev['recurring_id']), 'income' if int(ev['amount']) >= 0 else 'expense')
        if typ == 'income': booked_income += value
        elif typ == 'savings': booked_savings += value
        else: booked_expense += value

    planned_income = planned_expense = planned_savings = 0
    month_rows = c.execute("""SELECT t.amount,COALESCE(c.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) category_type
                              FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
                              WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
                           (start.isoformat(),month_end.isoformat())).fetchall()
    for r in month_rows:
        value=abs(int(r['amount']))
        typ=r['category_type']
        if typ == 'income': planned_income += value
        elif typ == 'savings': planned_savings += value
        else: planned_expense += value

    recurring_category_types = recurring_type_by_id
    # recurring_events() already omits occurrences that have been executed into
    # a transaction, so adding these events does not double-count booked rows.
    for ev in recurring_events(c, None, start, month_end):
        value=abs(int(ev['amount']))
        typ=recurring_category_types.get(int(ev['recurring_id']), 'income' if int(ev['amount']) >= 0 else 'expense')
        if typ == 'income': planned_income += value
        elif typ == 'savings': planned_savings += value
        else: planned_expense += value

    cash_surplus = booked_income-booked_expense-booked_savings
    total_saved = booked_savings + max(0, cash_surplus)
    savings_rate = (total_saved/booked_income*100.0) if booked_income else 0.0
    days_in_month = max(1, month_end.day)

    def daily_average_euros(total_cents: int) -> float:
        # Decimal + ROUND_HALF_UP avoids Python's bankers-rounding surprises at
        # exact half-cent boundaries and keeps the displayed result cent-accurate.
        value = (Decimal(total_cents) / Decimal(days_in_month) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return float(value)

    cat_rows=c.execute("""SELECT COALESCE(c.name,'Nicht kategorisiert') name,SUM(ABS(t.amount)) amount
                         FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
                         WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND COALESCE(c.direction,CASE WHEN t.amount<0 THEN 'expense' ELSE 'income' END)='expense' AND t.booking_date>=? AND t.booking_date<=?
                         GROUP BY COALESCE(c.name,'Nicht kategorisiert') ORDER BY amount DESC LIMIT 5""",
                      (start.isoformat(),cutoff.isoformat())).fetchall()

    monthly_overview=[]
    cursor=start
    for _ in range(11):
        prev_end=cursor-timedelta(days=1)
        prev_start=date(prev_end.year,prev_end.month,1)
        cursor=prev_start
    for _ in range(12):
        mstart=cursor
        mend=(date(mstart.year+1,1,1) if mstart.month==12 else date(mstart.year,mstart.month+1,1))-timedelta(days=1)
        tx_month=c.execute("""SELECT t.amount,COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) category_type
              FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
              WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
            (mstart.isoformat(),mend.isoformat())).fetchall()
        mincome=mexpense=msavings=0
        for row in tx_month:
            value=abs(int(row['amount'])); typ=row['category_type']
            if typ=='income': mincome += value
            elif typ=='savings': msavings += value
            else: mexpense += value
        # Add planned recurring occurrences that have not already materialised
        # into transactions. recurring_events() suppresses executed occurrences,
        # so historical actuals and future plans can share one 12-month series.
        for ev in recurring_events(c,None,mstart,mend):
            value=abs(int(ev['amount']))
            typ=recurring_type_by_id.get(int(ev['recurring_id']), 'income' if int(ev['amount'])>=0 else 'expense')
            if typ=='income': mincome += value
            elif typ=='savings': msavings += value
            else: mexpense += value
        projected_total=0
        for ar in c.execute('SELECT id FROM accounts WHERE active=1 AND start_date<=?',(mend.isoformat(),)).fetchall():
            projected_total += projected_account_balance(c,ar['id'],mend)
        mcash_surplus = mincome - mexpense - msavings
        mtotal_saved = msavings + max(0, mcash_surplus)
        msavings_rate = (mtotal_saved / mincome * 100.0) if mincome else 0.0
        monthly_overview.append({
            'month':mstart.strftime('%Y-%m'),'income':euros(mincome),'expense':euros(mexpense),'savings':euros(msavings),
            'net':euros(mincome-mexpense-msavings),'projected_end_balance':euros(projected_total),
            'savings_rate_pct': round(msavings_rate, 1)
        })
        cursor=date(mstart.year+1,1,1) if mstart.month==12 else date(mstart.year,mstart.month+1,1)

    # Calendar-year savings overview for the selected year. Past months use
    # materialised transactions; future months add still-open recurring events.
    year_start = date(start.year, 1, 1)
    year_end = date(start.year, 12, 31)
    annual_income = annual_expense = annual_savings = 0
    annual_rows = c.execute("""SELECT t.amount,COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) category_type
                              FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
                              WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.booking_date>=? AND t.booking_date<=?""",
                           (year_start.isoformat(), year_end.isoformat())).fetchall()
    for row in annual_rows:
        value = abs(int(row['amount'])); typ = row['category_type']
        if typ == 'income': annual_income += value
        elif typ == 'savings': annual_savings += value
        else: annual_expense += value
    for ev in recurring_events(c, None, year_start, year_end):
        value = abs(int(ev['amount']))
        typ = recurring_type_by_id.get(int(ev['recurring_id']), 'income' if int(ev['amount']) >= 0 else 'expense')
        if typ == 'income': annual_income += value
        elif typ == 'savings': annual_savings += value
        else: annual_expense += value
    annual_cash_surplus = annual_income - annual_expense - annual_savings
    annual_total_saved = annual_savings + max(0, annual_cash_surplus)
    annual_savings_rate = (annual_total_saved / annual_income * 100.0) if annual_income else 0.0

    month_end_balance = round(sum(a['month_end_balance'] for a in accounts_out), 2)
    investment_value_cents = 0
    if setting_value(c, 'investment_tracking', 'false') == 'true':
        for ir in c.execute('SELECT quantity,manual_price_cents FROM investment_assets WHERE active=1').fetchall():
            investment_value_cents += int((Decimal(str(ir['quantity'] or 0))*Decimal(int(ir['manual_price_cents'] or 0))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    investment_value = euros(investment_value_cents)
    result = {
        'today': today.isoformat(), 'month': selected_month, 'month_start': start.isoformat(), 'month_end': month_end.isoformat(),
        'total_balance': euros(total_balance_cents), 'pending_outflows': euros(pending_outflows), 'pending_inflows': euros(pending_inflows), 'month_end_balance': month_end_balance,
        'cutoff': cutoff.isoformat(), 'remaining_start': remaining_start.isoformat(),
        'investment_value': investment_value, 'net_worth': euros(total_balance_cents + investment_value_cents),
        'accounts': accounts_out,
        'next_payments': next_payments,
        'analysis': {
            'booked_income': euros(booked_income), 'booked_expense': euros(booked_expense), 'booked_savings': euros(booked_savings),
            'booked_net': euros(booked_income-booked_expense-booked_savings),
            'balance_to_cutoff': euros(total_balance_cents),
            'savings_rate_pct': round(savings_rate,1),
            'planned_income': euros(planned_income), 'planned_expense': euros(planned_expense), 'planned_savings': euros(planned_savings),
            'average_daily_income': daily_average_euros(planned_income),
            'average_daily_expense': daily_average_euros(planned_expense),
            'average_daily_savings': daily_average_euros(planned_savings),
            'remaining_outflows': euros(pending_outflows), 'remaining_inflows': euros(pending_inflows),
            'annual_year': start.year,
            'annual_income': euros(annual_income), 'annual_expense': euros(annual_expense),
            'annual_explicit_savings': euros(annual_savings), 'annual_total_saved': euros(annual_total_saved),
            'annual_savings_rate_pct': round(annual_savings_rate, 1),
            'annual_average_monthly_saved': float((Decimal(annual_total_saved) / Decimal(12) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)),
            'top_expense_categories': [{'name':r['name'],'amount':euros(int(r['amount'] or 0))} for r in cat_rows],
            'monthly_overview': monthly_overview,
        },
        'earliest_month': (c.execute("SELECT MIN(substr(start_date,1,7)) FROM accounts WHERE active=1").fetchone()[0] or selected_month),
        'total_forecast': [dict({'date': k, 'balance': round(v, 2)}, **({'opening_balance': round(total_opening_balance, 2)} if k == start.isoformat() else {})) for k, v in sorted(total_series.items())],
    }
    return _cache_set('dashboard',result,cache_key,ttl=20)


@app.get("/api/reports/categories")
def category_report(request: Request, period: str = "month", anchor: date | None = None):
    session(request)
    if period not in {"month", "year"}:
        raise HTTPException(400, "Zeitraum muss month oder year sein")
    anchor = anchor or date.today()
    cache_key=(period,anchor.isoformat(),date.today().isoformat());cached=_cache_get("category_report",*cache_key,ttl=25)
    if cached is not None:return cached
    if period == "month":
        start = date(anchor.year, anchor.month, 1)
        end = date(anchor.year + (anchor.month == 12), 1 if anchor.month == 12 else anchor.month + 1, 1) - timedelta(days=1)
    else:
        start, end = date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    c = db.db()
    today=date.today()
    actual_end=min(end,today)
    # A current/future monthly report is a month-end forecast: include every
    # known non-cancelled booking through month end, including materialised
    # recurring rows. Historical months and yearly reports remain documentary
    # actuals and therefore only include executed bookings through today.
    forecast_mode=period=="month" and end>=today
    query_end=end if forecast_mode else (actual_end if actual_end>=start else start-timedelta(days=1))
    status_sql="t.status<>'cancelled'" if forecast_mode else "t.status='executed'"
    rows = c.execute(f"""
        SELECT category_id, category_name, direction, SUM(amount) amount FROM (
          SELECT s.category_id, COALESCE(c.name,'Nicht kategorisiert') category_name,
                 COALESCE(c.direction, CASE WHEN s.amount>=0 THEN 'income' ELSE 'expense' END) direction, s.amount amount
          FROM splits s JOIN transactions t ON t.id=s.transaction_id
          LEFT JOIN categories c ON c.id=s.category_id
          WHERE {status_sql} AND t.transfer_id IS NULL AND t.booking_date BETWEEN ? AND ?
          UNION ALL
          SELECT t.category_id, COALESCE(c.name,'Nicht kategorisiert') category_name,
                 COALESCE(c.direction, CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) direction, t.amount amount
          FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
          WHERE {status_sql} AND t.transfer_id IS NULL AND t.booking_date BETWEEN ? AND ?
            AND NOT EXISTS (SELECT 1 FROM splits s WHERE s.transaction_id=t.id)
        ) GROUP BY category_id,category_name,direction ORDER BY direction,ABS(SUM(amount)) DESC
    """, (start.isoformat(), query_end.isoformat(), start.isoformat(), query_end.isoformat())).fetchall()
    items=[]; income=expense=savings=0
    for r in rows:
        raw=int(r['amount'] or 0); value=abs(raw)
        if r['direction']=='income': income += value
        elif r['direction']=='savings': savings += value
        else: expense += value
        items.append({"category_id":r['category_id'],"category_name":r['category_name'],"direction":r['direction'],"amount":euros(value)})
    retained = max(0, income - expense - savings)
    total_saved = savings + retained
    savings_rate = (total_saved / income * 100.0) if income else 0.0
    explicit_savings_rate = (savings / income * 100.0) if income else 0.0

    # Average metrics follow the documentary period actually covered by this report.
    # Current month/year therefore divides by elapsed days/months, while completed
    # periods use their full calendar length. Future periods have no actual divisor.
    if actual_end < start:
        elapsed_days = 0
        elapsed_months = 0
    else:
        elapsed_days = (actual_end - start).days + 1
        elapsed_months = (actual_end.year - start.year) * 12 + actual_end.month - start.month + 1
    avg_divisor = elapsed_months if period == "year" else elapsed_days
    avg_saved = (Decimal(total_saved) / Decimal(max(avg_divisor, 1)) / Decimal(100)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if avg_divisor else Decimal('0.00')

    result={"period":period,"start":start.isoformat(),"end":end.isoformat(),"actual_through":actual_end.isoformat() if actual_end>=start else None,
            "mode":"forecast" if forecast_mode else "actual","includes_planned":bool(forecast_mode),
            "income":euros(income),"expense":euros(expense),"savings":euros(savings),"net":euros(income-expense-savings),
            "retained":euros(retained),"total_saved":euros(total_saved),
            "savings_rate_pct":round(savings_rate,1),"explicit_savings_rate_pct":round(explicit_savings_rate,1),
            "average_saved":float(avg_saved),"average_saved_unit":"month" if period == "year" else "day",
            "average_saved_divisor":avg_divisor,"items":items}
    return _cache_set("category_report",result,*cache_key,ttl=25)

@app.get("/api/budgets")
def budgets(request: Request, month: str | None = None):
    session(request)
    month = month or date.today().strftime("%Y-%m")
    start, end = month_bounds(month)
    c = db.db()
    strategy = setting_value(c, "budget_strategy", "hybrid")
    rows = c.execute(
        """SELECT b.id,b.category_id,c.name category_name,b.month,b.amount,b.strategy,b.bucket,b.note
           FROM budgets b LEFT JOIN categories c ON c.id=b.category_id
           WHERE b.month=? AND b.id IN (SELECT MAX(id) FROM budgets WHERE month=? GROUP BY COALESCE(category_id,-1)) ORDER BY c.name""",
        (month,month),
    ).fetchall()

    spent_rows = c.execute(
        """SELECT t.category_id,COALESCE(SUM(ABS(t.amount)),0) amount FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
           WHERE t.status='executed' AND t.transfer_id IS NULL AND COALESCE(c.direction,CASE WHEN t.amount<0 THEN 'expense' ELSE 'income' END)='expense' AND t.booking_date BETWEEN ? AND ? GROUP BY t.category_id""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    spent_by_category = {r["category_id"]: int(r["amount"] or 0) for r in spent_rows}
    total_expense = int(c.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)),0) FROM transactions t LEFT JOIN categories c ON c.id=t.category_id WHERE t.status='executed' AND t.transfer_id IS NULL AND COALESCE(c.direction,CASE WHEN t.amount<0 THEN 'expense' ELSE 'income' END)='expense' AND t.booking_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()[0] or 0)
    tx_income = int(c.execute(
        "SELECT COALESCE(SUM(ABS(t.amount)),0) FROM transactions t LEFT JOIN categories c ON c.id=t.category_id WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND COALESCE(c.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END)='income' AND t.booking_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()[0] or 0)
    recurring_income = sum(max(0, int(ev["amount"])) for ev in recurring_events(c, None, start, end))
    expected_income = tx_income + recurring_income

    entries=[]
    category_budget_total=0
    overall_budget=None
    bucket_totals={"needs":0,"wants":0,"savings":0,"free":0}
    for r in rows:
        amount=int(r["amount"] or 0)
        if r["category_id"] is None:
            overall_budget=amount
            spent=total_expense
        else:
            category_budget_total += amount
            spent=spent_by_category.get(r["category_id"],0)
        bucket=r["bucket"] or "free"
        bucket_totals[bucket]=bucket_totals.get(bucket,0)+amount
        entries.append({**dict(r),"amount":euros(amount),"spent":euros(spent),"remaining":euros(amount-spent),"usage_pct":round((spent/amount*100),1) if amount else 0.0})

    strategy_metrics={}
    if strategy=="zero_based":
        strategy_metrics={"allocated":euros(category_budget_total),"unallocated":euros(expected_income-category_budget_total),"target":"Alle erwarteten Einnahmen verplanen; Rest idealerweise 0 €."}
    elif strategy=="envelope":
        strategy_metrics={"allocated":euros(category_budget_total),"remaining":euros(category_budget_total-sum(spent_by_category.get(r["category_id"],0) for r in rows if r["category_id"] is not None)),"target":"Jede Ausgabenkategorie hat einen eigenen Topf. Nicht über den Restbetrag hinaus ausgeben."}
    elif strategy=="50_30_20":
        strategy_metrics={
            "income":euros(expected_income),
            "targets":{"needs":euros(round(expected_income*.50)),"wants":euros(round(expected_income*.30)),"savings":euros(round(expected_income*.20))},
            "allocated":{"needs":euros(bucket_totals.get("needs",0)),"wants":euros(bucket_totals.get("wants",0)),"savings":euros(bucket_totals.get("savings",0))},
            "target":"Richtwert: 50 % Grundbedarf, 30 % Wünsche, 20 % Sparen/Rücklagen."
        }
    elif strategy=="pay_yourself_first":
        strategy_metrics={"income":euros(expected_income),"savings_planned":euros(bucket_totals.get("savings",0)),"after_savings":euros(expected_income-bucket_totals.get("savings",0)),"target":"Zuerst Sparen/Rücklagen reservieren; den verbleibenden Betrag danach verteilen."}
    else:
        strategy_metrics={"allocated":euros(category_budget_total),"income":euros(expected_income),"target":"Freie Kombination aus Kategorien, Gesamtlimit und Sparziel."}

    return {"month":month,"strategy":strategy,"expected_income":euros(expected_income),"booked_expense":euros(total_expense),"overall_budget":euros(overall_budget) if overall_budget is not None else None,"category_budget_total":euros(category_budget_total),"entries":entries,"strategy_metrics":strategy_metrics}


@app.post("/api/budgets")
def budget_create(x: BudgetIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        existing = c.execute("SELECT id FROM budgets WHERE month=? AND ((category_id IS NULL AND ? IS NULL) OR category_id=?) ORDER BY id DESC LIMIT 1", (x.month, x.category_id, x.category_id)).fetchone()
        if existing:
            before=dict(c.execute("SELECT category_id,month,amount,strategy,bucket,note FROM budgets WHERE id=?",(existing["id"],)).fetchone())
            c.execute("UPDATE budgets SET amount=?,strategy=?,bucket=?,note=? WHERE id=?",(cents(x.amount),x.strategy,x.bucket,clean_text(x.note,300),existing["id"]))
            after=dict(c.execute("SELECT category_id,month,amount,strategy,bucket,note FROM budgets WHERE id=?",(existing["id"],)).fetchone())
            audit_append(c,sess[1],"budget.update","budget",existing["id"],{"month":x.month,"changes":audit_changes(before,after,("category_id","month","amount","strategy","bucket","note")),"current":audit_pick(after,("category_id","month","amount","strategy","bucket","note"))})
            return {"id":existing["id"]}
        cur = c.execute(
            """INSERT INTO budgets(category_id,month,amount,strategy,bucket,note) VALUES(?,?,?,?,?,?)
               ON CONFLICT(category_id,month,strategy) DO UPDATE SET amount=excluded.amount,bucket=excluded.bucket,note=excluded.note""",
            (x.category_id, x.month, cents(x.amount), x.strategy, x.bucket, clean_text(x.note, 300)),
        )
        created=dict(c.execute("SELECT category_id,month,amount,strategy,bucket,note FROM budgets WHERE id=?",(cur.lastrowid,)).fetchone())
        audit_append(c,sess[1],"budget.create","budget",cur.lastrowid,{"month":x.month,"added":created})
        return {"id": cur.lastrowid}


@app.put("/api/budgets/{budget_id}")
def budget_update(budget_id: int, x: BudgetIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        row=c.execute("SELECT category_id,month,amount,strategy,bucket,note FROM budgets WHERE id=?",(budget_id,)).fetchone()
        if not row: raise HTTPException(404,"Budget nicht gefunden")
        before=dict(row)
        c.execute("UPDATE budgets SET category_id=?,month=?,amount=?,strategy=?,bucket=?,note=? WHERE id=?",
                  (x.category_id,x.month,cents(x.amount),x.strategy,x.bucket,clean_text(x.note,300),budget_id))
        after=dict(c.execute("SELECT category_id,month,amount,strategy,bucket,note FROM budgets WHERE id=?",(budget_id,)).fetchone())
        audit_append(c,sess[1],"budget.update","budget",budget_id,{"month":x.month,"changes":audit_changes(before,after,("category_id","month","amount","strategy","bucket","note")),"current":audit_pick(after,("category_id","month","amount","strategy","bucket","note"))})
    return {"ok":True}


@app.delete("/api/budgets/{budget_id}")
def budget_delete(budget_id: int, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        c.execute("DELETE FROM budgets WHERE id=?", (budget_id,))
        audit_append(c,sess[1],"budget.delete","budget",budget_id,{})
    return {"ok": True}


BANK_ALIASES = {
    "date": ["buchungstag", "datum", "booking date", "buchungsdatum", "date"],
    "value_date": ["valutadatum", "wertstellung", "value date"],
    "amount": ["betrag", "umsatz", "amount", "betrag (eur)", "umsatz eur"],
    "payee": ["begünstigter/zahlungspflichtiger", "beguenstigter", "empfänger", "name", "payee", "auftraggeber"],
    "note": ["verwendungszweck", "buchungstext", "description", "purpose", "buchungstext/verwendungszweck"],
    "iban": ["iban", "kontonummer/iban", "gegenkonto iban"],
    "external": ["transaktions-id", "transaction id", "referenz", "kundenreferenz", "end-to-end-ref."],
}


def normalize_header(value: str) -> str:
    return " ".join(value.strip().lower().replace("\ufeff", "").split())


def pick(row: dict, field: str) -> str:
    normalized = {normalize_header(str(k)): (v or "") for k, v in row.items() if k is not None}
    for name in BANK_ALIASES[field]:
        if name in normalized:
            return str(normalized[name]).strip()
    return ""


def parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError("date")


def parse_amount(value: str) -> int:
    raw = value.strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not raw:
        raise ValueError("amount")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return cents(Decimal(raw))


@app.post("/api/import/csv")
async def import_csv(request: Request, file: UploadFile = File(...), account_id: int | None = Form(default=None)):
    sess=session(request, True)
    raw_bytes = await file.read(MAX_UPLOAD + 1)
    if len(raw_bytes) > MAX_UPLOAD:
        raise HTTPException(413, "CSV-Datei ist zu groß")
    text = raw_bytes.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=";,\t|")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    rows = csv.DictReader(io.StringIO(text), dialect=dialect)
    imported = skipped = duplicates = 0
    c = db.db()
    with db.transaction() as c:
        for row in rows:
            try:
                d = parse_date(pick(row, "date"))
                amount = parse_amount(pick(row, "amount"))
                iban = normalize_iban(pick(row, "iban"))
                aid = account_id
                if aid is None and iban:
                    found = c.execute("SELECT id FROM accounts WHERE iban=? AND active=1", (iban,)).fetchone()
                    aid = found[0] if found else None
                if aid is None:
                    skipped += 1
                    continue
                payee = clean_text(pick(row, "payee"), 200)
                note = clean_text(pick(row, "note"), 1000)
                bank_ref = pick(row, "external")
                fingerprint = bank_ref or f"{d.isoformat()}|{amount}|{payee or ''}|{note or ''}"
                ext = "csv-" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
                exists = c.execute("SELECT 1 FROM transactions WHERE account_id=? AND external_id=?", (aid, ext)).fetchone()
                if exists:
                    duplicates += 1
                    continue
                vd_raw = pick(row, "value_date")
                vd = parse_date(vd_raw).isoformat() if vd_raw else None
                ts = iso(utcnow())
                c.execute(
                    """INSERT INTO transactions(account_id,amount,booking_date,value_date,name,payee,note,status,external_id,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,'executed',?,?,?)""",
                    (aid, amount, d.isoformat(), vd, payee or "CSV-Buchung", payee, note, ext, ts, ts),
                )
                imported += 1
            except Exception:
                skipped += 1
        audit_append(c,sess[1],"import.csv","import",None,{"filename":Path(file.filename or "import.csv").name,"imported":imported,"duplicates":duplicates,"skipped":skipped,"bytes":len(raw_bytes)})
    return {"imported": imported, "duplicates": duplicates, "skipped": skipped}


@app.get("/api/settings")
def settings(request: Request):
    session(request)
    return {r["key"]: r["value"] for r in db.db().execute("SELECT key,value FROM settings").fetchall()}


@app.put("/api/settings/{key}")
def setting_update(key: str, x: SettingsIn, request: Request):
    sess=session(request, True); require_book_owner(request)
    allowed = {
        "investment_tracking": {"true", "false"},
        "autolock_minutes": {"1", "5", "10", "15", "30", "60", "0"},
        "budget_strategy": {"zero_based", "envelope", "50_30_20", "pay_yourself_first", "hybrid"},
    }
    if key not in allowed or x.value not in allowed[key]:
        raise HTTPException(400, "Ungültige Einstellung")
    with db.transaction() as c:
        old_row=c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        old_value=old_row["value"] if old_row else None
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, x.value),
        )
        audit_append(c,sess[1],"settings.update","settings",key,{"name":key,"changes":{"value":{"old":old_value,"new":x.value}} if old_value!=x.value else {}})
    return {"ok": True}



class WhatIfIn(BaseModel):
    horizon_months: int = Field(default=12, ge=1, le=24)
    monthly_income_change: Decimal = Decimal("0.00")
    monthly_expense_change: Decimal = Decimal("0.00")
    monthly_savings_change: Decimal = Decimal("0.00")
    one_time_change: Decimal = Decimal("0.00")
    one_time_date: date | None = None


class ContractIn(BaseModel):
    recurring_series_id: int | None = None
    title: str = Field(min_length=1,max_length=150)
    provider: str | None = Field(default=None,max_length=150)
    start_date: date | None = None
    end_date: date | None = None
    cancellation_deadline: date | None = None
    notice_days: int | None = Field(default=None,ge=0,le=3650)
    notes: str | None = Field(default=None,max_length=1000)
    active: bool = True


def month_category_totals(c, start: date, end: date, include_recurring: bool = False) -> dict[int | None, dict]:
    out={}
    rows=c.execute("""SELECT t.category_id,COALESCE(cat.name,'Nicht kategorisiert') category_label,
                             COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) typ,
                             SUM(ABS(t.amount)) amount
                      FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
                      WHERE t.status='executed' AND t.transfer_id IS NULL AND t.booking_date BETWEEN ? AND ?
                      GROUP BY t.category_id,COALESCE(cat.name,'Nicht kategorisiert'),COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END)""",(start.isoformat(),end.isoformat())).fetchall()
    for r in rows:
        out[r["category_id"]]={"category_id":r["category_id"],"name":r["category_label"],"type":r["typ"],"amount":int(r["amount"] or 0)}
    if include_recurring:
        for item in planned_month_category_totals(c,start,end).values():
            row=out.setdefault(item["category_id"],{"category_id":item["category_id"],"name":item["name"],"type":item["type"],"amount":0})
            row["amount"]+=item["amount"]
    return out


def _recurring_plan_context(c, rows, start: date, end: date):
    category_ids=sorted({int(r["category_id"]) for r in rows if r["category_id"] is not None})
    series_ids=sorted({int(r["series_id"] or r["id"]) for r in rows})
    categories={}
    overrides={}

    for i in range(0,len(category_ids),800):
        ids=category_ids[i:i+800]
        marks=",".join("?" for _ in ids)
        sql="SELECT id,name,direction FROM categories WHERE id IN ({})".format(marks)
        for x in c.execute(sql,ids).fetchall():
            categories[int(x["id"])]=x

    for i in range(0,len(series_ids),800):
        ids=series_ids[i:i+800]
        marks=",".join("?" for _ in ids)
        sql=("SELECT series_id,due_date,amount FROM recurring_overrides "
             "WHERE series_id IN ({}) AND due_date BETWEEN ? AND ?").format(marks)
        for x in c.execute(sql,[*ids,start.isoformat(),end.isoformat()]).fetchall():
            overrides[(int(x["series_id"]),x["due_date"])]=int(x["amount"])
    return categories,overrides


def planned_month_category_totals(c, start: date, end: date) -> dict[int | None, dict]:
    """Plan values independent of whether a recurring occurrence was executed."""
    out={}
    rows=c.execute("""SELECT t.category_id,COALESCE(cat.name,'Nicht kategorisiert') category_label,
                             COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) typ,
                             SUM(ABS(t.amount)) amount
                      FROM transactions t LEFT JOIN categories cat ON cat.id=t.category_id
                      WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.recurring_id IS NULL AND t.booking_date BETWEEN ? AND ?
                      GROUP BY t.category_id,COALESCE(cat.name,'Nicht kategorisiert'),COALESCE(cat.direction,CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END)""",(start.isoformat(),end.isoformat())).fetchall()
    for r in rows:
        out[r["category_id"]]={"category_id":r["category_id"],"name":r["category_label"],"type":r["typ"],"amount":int(r["amount"] or 0)}

    recurring_rows=list(recurring_rows_for_window(c,None,start,end))
    categories,overrides=_recurring_plan_context(c,recurring_rows,start,end)
    for r in recurring_rows:
        vf=date.fromisoformat(r["valid_from"] or r["next_date"])
        vu=date.fromisoformat(r["valid_until"]) if r["valid_until"] else end
        low=max(start,vf); high=min(end,vu)
        if low>high:
            continue
        anchor=date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
        cid=r["category_id"]
        cat=categories.get(int(cid)) if cid is not None else None
        typ=cat["direction"] if cat else ("income" if r["kind"]=="income" else "expense")
        name=cat["name"] if cat else "Nicht kategorisiert"
        series_id=int(r["series_id"] or r["id"])
        row=out.setdefault(cid,{"category_id":cid,"name":name,"type":typ,"amount":0})
        for due in occurrences(anchor,r["frequency"],low,high,int(r["interval_count"] or 1)):
            raw=overrides.get((series_id,due.isoformat()),int(r["amount"]))
            row["amount"]+=abs(int(raw))
    return out


def planned_fixed_costs(c, start: date, end: date) -> int:
    """Planned fixed-cost outflows for a period, independent of actual recurring deviations."""
    total=int(c.execute("""SELECT COALESCE(SUM(ABS(t.amount)),0) FROM transactions t
                           LEFT JOIN categories cat ON cat.id=t.category_id
                           WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.recurring_id IS NULL AND t.fixed_cost=1
                             AND COALESCE(cat.direction,CASE WHEN t.direction='income' THEN 'income' ELSE 'expense' END)='expense'
                             AND t.booking_date BETWEEN ? AND ?""",
                        (start.isoformat(),end.isoformat())).fetchone()[0] or 0)
    recurring_rows=[r for r in recurring_rows_for_window(c,None,start,end) if int(r["fixed_cost"] or 0)]
    categories,overrides=_recurring_plan_context(c,recurring_rows,start,end)
    for r in recurring_rows:
        cid=r["category_id"]
        cat=categories.get(int(cid)) if cid is not None else None
        cat_type=cat["direction"] if cat else None
        if cat_type in {"income","savings"} or (cat_type is None and r["kind"]=="income"):
            continue
        vf=date.fromisoformat(r["valid_from"] or r["next_date"])
        vu=date.fromisoformat(r["valid_until"]) if r["valid_until"] else end
        low=max(start,vf); high=min(end,vu)
        if low>high:
            continue
        anchor=date.fromisoformat(r["anchor_date"] or r["valid_from"] or r["next_date"])
        series_id=int(r["series_id"] or r["id"])
        for due in occurrences(anchor,r["frequency"],low,high,int(r["interval_count"] or 1)):
            raw=overrides.get((series_id,due.isoformat()),int(r["amount"]))
            total+=abs(int(raw))
    return total


@app.get("/api/planning/variance")
def planning_variance(request: Request, month: str | None = None):
    session(request)
    c=db.db(); start,end=month_bounds(month); today=date.today()
    actual_end=min(end,today)
    actual=month_category_totals(c,start,actual_end,False) if actual_end>=start else {}
    planned=planned_month_category_totals(c,start,end)
    ids=set(actual)|set(planned); rows=[]
    for cid in ids:
        a=actual.get(cid,{"amount":0}); p=planned.get(cid,{"amount":0,"name":a.get("name","Nicht kategorisiert"),"type":a.get("type","expense")})
        av=int(a.get("amount",0)); pv=int(p.get("amount",0)); diff=av-pv
        rows.append({"category_id":cid,"name":p.get("name"),"type":p.get("type"),"planned":euros(pv),"actual":euros(av),"difference":euros(diff),"difference_pct":round(diff/pv*100,1) if pv else None})
    rows.sort(key=lambda x:abs(x["difference"]),reverse=True)
    return {"month":start.strftime("%Y-%m"),"rows":rows}


@app.get("/api/planning/runway")
def planning_runway(request: Request):
    session(request); c=db.db(); today=date.today()
    liquid=0
    for a in c.execute("SELECT id,type FROM accounts WHERE active=1 AND start_date<=?",(today.isoformat(),)).fetchall():
        bal=projected_account_balance(c,a["id"],today)
        if a["type"]!="credit_card": liquid+=bal
    totals=[]
    for offset in range(3):
        ms=add_months(date(today.year,today.month,1),offset); me=month_bounds(ms.strftime("%Y-%m"))[1]
        totals.append(planned_fixed_costs(c,ms,me))
    monthly_fixed=sum(totals)//len(totals) if totals else 0
    runway=(Decimal(liquid)/Decimal(monthly_fixed)) if monthly_fixed>0 else None
    return {"liquid_balance":euros(liquid),"monthly_fixed_costs":euros(monthly_fixed),"runway_months":float(runway.quantize(Decimal('0.1'),rounding=ROUND_HALF_UP)) if runway is not None else None}


@app.post("/api/planning/what-if")
def planning_what_if(x: WhatIfIn, request: Request):
    session(request); c=db.db(); base=_long_forecast(c,x.horizon_months,"expected")
    monthly_delta=cents(x.monthly_income_change)-cents(x.monthly_expense_change)-cents(x.monthly_savings_change)
    one_delta=cents(x.one_time_change); out=[]; cumulative=0
    for i,row in enumerate(base):
        cumulative+=monthly_delta
        month_start=date.fromisoformat(row["month"]+"-01"); month_end=month_bounds(row["month"])[1]
        if x.one_time_date and month_start<=x.one_time_date<=month_end: cumulative+=one_delta
        out.append({"month":row["month"],"baseline_end_balance":row["end_balance"],"scenario_end_balance":euros(cents(row["end_balance"])+cumulative),"difference":euros(cumulative)})
    return {"horizon_months":x.horizon_months,"monthly_delta":euros(monthly_delta),"series":out}


@app.get("/api/analysis/variability")
def variability(request: Request, months: int = 12):
    session(request); months=max(3,min(months,36)); c=db.db(); today=date.today(); current=date(today.year,today.month,1)
    series={"income":[],"expense":[],"savings":[]}
    for offset in range(months-1,-1,-1):
        ms=add_months(current,-offset); me=month_bounds(ms.strftime("%Y-%m"))[1]
        totals={"income":0,"expense":0,"savings":0}
        actual_end=min(me,today)
        if actual_end>=ms:
            for r in month_category_totals(c,ms,actual_end,False).values(): totals[r["type"] if r["type"] in totals else "expense"]+=r["amount"]
        for typ in series: series[typ].append({"month":ms.strftime("%Y-%m"),"amount":euros(totals[typ])})
    stats={}
    for typ,rows in series.items():
        vals=[Decimal(str(r["amount"])) for r in rows]
        stats[typ]={"min":float(min(vals)),"max":float(max(vals)),"average":float((sum(vals)/Decimal(len(vals))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)),"median":float(Decimal(str(statistics.median([float(v) for v in vals]))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))}
    return {"months":months,"series":series,"stats":stats}


@app.get("/api/contracts")
def contracts(request: Request):
    session(request); rows=db.db().execute("SELECT * FROM contracts WHERE active=1 ORDER BY COALESCE(cancellation_deadline,'9999-12-31'),title").fetchall(); return [dict(r) for r in rows]


@app.post("/api/contracts")
def contract_create(x: ContractIn, request: Request):
    sess=session(request,True); ts=iso(utcnow())
    if x.end_date and x.start_date and x.end_date<x.start_date: raise HTTPException(400,"Vertragsende liegt vor Vertragsbeginn")
    with db.transaction() as c:
        cur=c.execute("""INSERT INTO contracts(recurring_series_id,title,provider,start_date,end_date,cancellation_deadline,notice_days,notes,active,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(x.recurring_series_id,x.title.strip(),clean_text(x.provider,150),x.start_date.isoformat() if x.start_date else None,x.end_date.isoformat() if x.end_date else None,x.cancellation_deadline.isoformat() if x.cancellation_deadline else None,x.notice_days,clean_text(x.notes,1000),int(x.active),ts,ts))
        created=dict(c.execute("SELECT title,provider,start_date,end_date,cancellation_deadline,notice_days,notes,active FROM contracts WHERE id=?",(cur.lastrowid,)).fetchone())
        audit_append(c,sess[1],"contract.create","contract",cur.lastrowid,{"name":created.get("title"),"added":created})
        return {"id":cur.lastrowid}


@app.put("/api/contracts/{contract_id}")
def contract_update(contract_id: int, x: ContractIn, request: Request):
    sess=session(request,True); ts=iso(utcnow())
    with db.transaction() as c:
        old_row=c.execute("SELECT title,provider,start_date,end_date,cancellation_deadline,notice_days,notes,active FROM contracts WHERE id=?",(contract_id,)).fetchone()
        if not old_row: raise HTTPException(404,"Vertrag nicht gefunden")
        before=dict(old_row)
        cur=c.execute("""UPDATE contracts SET recurring_series_id=?,title=?,provider=?,start_date=?,end_date=?,cancellation_deadline=?,notice_days=?,notes=?,active=?,updated_at=? WHERE id=?""",
                      (x.recurring_series_id,x.title.strip(),clean_text(x.provider,150),x.start_date.isoformat() if x.start_date else None,x.end_date.isoformat() if x.end_date else None,x.cancellation_deadline.isoformat() if x.cancellation_deadline else None,x.notice_days,clean_text(x.notes,1000),int(x.active),ts,contract_id))
        after=dict(c.execute("SELECT title,provider,start_date,end_date,cancellation_deadline,notice_days,notes,active FROM contracts WHERE id=?",(contract_id,)).fetchone())
        audit_append(c,sess[1],"contract.update","contract",contract_id,{"name":after.get("title"),"changes":audit_changes(before,after,("title","provider","start_date","end_date","cancellation_deadline","notice_days","notes","active")),"current":audit_pick(after,("title","provider","start_date","end_date","cancellation_deadline","notice_days","notes","active"))})
    return {"ok":True}


@app.delete("/api/contracts/{contract_id}")
def contract_delete(contract_id: int, request: Request):
    sess=session(request,True)
    with db.transaction() as c:
        c.execute("UPDATE contracts SET active=0,updated_at=? WHERE id=?",(iso(utcnow()),contract_id)); audit_append(c,sess[1],"contract.archive","contract",contract_id,{})
    return {"ok":True}


def run_finance_check(c) -> dict:
    checks=[]
    def add(level,code,message,details=None): checks.append({"level":level,"code":code,"message":message,"details":details or {}})
    # SQL/data integrity
    try:
        cipher_errors=db.integrity_check()
        add("error" if cipher_errors else "ok","sqlcipher_integrity","SQLCipher Integrität" if not cipher_errors else "SQLCipher-Integritätsfehler",{"errors":cipher_errors})
    except Exception as exc: add("error","sqlcipher_integrity","Integritätsprüfung fehlgeschlagen",{"error":str(exc)})
    audit_ok,audit_errors=audit_verify(c); add("ok" if audit_ok else "error","audit_chain","Audit-Hashkette intakt" if audit_ok else "Audit-Hashkette beschädigt",{"errors":audit_errors})
    # split sums
    bad=c.execute("""SELECT t.id,t.amount,COALESCE(SUM(s.amount),0) split_sum FROM transactions t JOIN splits s ON s.transaction_id=t.id GROUP BY t.id HAVING split_sum<>t.amount""").fetchall()
    add("error" if bad else "ok","split_sums","Splits stimmen mit Buchungsbetrag überein" if not bad else f"{len(bad)} Buchungen mit falscher Split-Summe",{"transaction_ids":[r["id"] for r in bad]})
    # sign/category contradictions
    contradictions=c.execute("""SELECT t.id,t.amount,t.direction,c.direction category_direction FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
                                WHERE t.status<>'cancelled' AND ((t.direction='expense' AND t.amount>0) OR (t.direction='income' AND t.amount<0)
                                OR (c.direction='income' AND t.direction='expense') OR (c.direction IN ('expense','savings') AND t.direction='income'))""").fetchall()
    add("warning" if contradictions else "ok","directions","Vorzeichen/Kategorien plausibel" if not contradictions else f"{len(contradictions)} widersprüchliche Buchungen",{"transaction_ids":[r["id"] for r in contradictions]})
    # account continuity across last/next six months unless explicit override exists.
    discontinuities=[]; today=date.today()
    for a in c.execute("SELECT id,start_date FROM accounts WHERE active=1").fetchall():
        start=max(date.fromisoformat(a["start_date"]),add_months(date(today.year,today.month,1),-6)); m=date(start.year,start.month,1)
        for _ in range(13):
            nxt=add_months(m,1)
            if c.execute("SELECT 1 FROM account_month_overrides WHERE account_id=? AND month=?",(a["id"],nxt.strftime('%Y-%m'))).fetchone(): m=nxt; continue
            prev_end=month_bounds(m.strftime('%Y-%m'))[1]
            if _month_opening_balance(c,a["id"],nxt)!=projected_account_balance(c,a["id"],prev_end): discontinuities.append({"account_id":a["id"],"month":nxt.strftime('%Y-%m')})
            m=nxt
    add("error" if discontinuities else "ok","month_continuity","Monatsanfänge übernehmen Vormonatsende" if not discontinuities else f"{len(discontinuities)} Monatsübergänge unstimmig",{"items":discontinuities})
    # reconciliation status
    rec_warnings=[]
    for a in c.execute("SELECT id,name FROM accounts WHERE active=1").fetchall():
        r=c.execute("SELECT difference,checked_at FROM account_reconciliations WHERE account_id=? ORDER BY checked_at DESC,id DESC LIMIT 1",(a["id"],)).fetchone()
        if r and abs(int(r["difference"]))>1: rec_warnings.append({"account":a["name"],"difference":euros(r["difference"]),"checked_at":r["checked_at"]})
    add("warning" if rec_warnings else "ok","reconciliation","Kontenabgleich ohne offene Differenz" if not rec_warnings else f"{len(rec_warnings)} Konten mit letzter Abweichung",{"items":rec_warnings})
    # attachments storage
    used=int(c.execute("SELECT COALESCE(SUM(size),0) FROM attachments").fetchone()[0] or 0); ratio=used/MAX_ATTACHMENT_TOTAL_BYTES if MAX_ATTACHMENT_TOTAL_BYTES else 0
    add("warning" if ratio>=0.8 else "ok","attachment_storage",f"Belegspeicher {used/1024/1024:.1f} MB von {MAX_ATTACHMENT_TOTAL_BYTES/1024/1024:.0f} MB – bei vollem Limit werden nur neue Beleg-Uploads blockiert",{"used":used,"limit":MAX_ATTACHMENT_TOTAL_BYTES})
    errors=sum(1 for x in checks if x["level"]=="error"); warnings=sum(1 for x in checks if x["level"]=="warning")
    return {"ok":errors==0,"errors":errors,"warnings":warnings,"checks":checks,"checked_at":iso(utcnow())}


@app.post("/api/finance-check")
def finance_check(request: Request):
    sess=session(request,True); c=db.db(); result=run_finance_check(c)
    with db.transaction() as cw:
        cw.execute("INSERT INTO finance_check_runs(checked_at,ok,errors,warnings,result_json) VALUES(?,?,?,?,?)",(result["checked_at"],int(result["ok"]),result["errors"],result["warnings"],json.dumps(result,ensure_ascii=False,separators=(',',':'))))
        audit_append(cw,sess[1],"finance_check.run","system",None,{"ok":result["ok"],"errors":result["errors"],"warnings":result["warnings"]})
    return result


@app.get("/api/finance-check/last")
def finance_check_last(request: Request):
    session(request); r=db.db().execute("SELECT result_json FROM finance_check_runs ORDER BY id DESC LIMIT 1").fetchone(); return json.loads(r[0]) if r else None


@app.get("/api/planning/year")
def planning_year(request: Request, year: int | None = None):
    session(request)
    y=year or date.today().year
    cache_key=(y,date.today().isoformat());cached=_cache_get("planning_year",*cache_key,ttl=30)
    if cached is not None:return cached
    if y<2000 or y>2100:
        raise HTTPException(400,"Ungültiges Jahr")
    c=db.db(); today=date.today(); months=[]
    totals={k:0 for k in ("planned_income","planned_expense","planned_savings","actual_income","actual_expense","actual_savings")}
    for m in range(1,13):
        start=date(y,m,1); end=month_bounds(f"{y:04d}-{m:02d}")[1]
        pvals={"income":0,"expense":0,"savings":0}; avals={"income":0,"expense":0,"savings":0}
        for r in planned_month_category_totals(c,start,end).values():
            typ=r["type"] if r["type"] in pvals else "expense"; pvals[typ]+=int(r["amount"])
        actual_end=min(end,today)
        if actual_end>=start:
            for r in month_category_totals(c,start,actual_end,False).values():
                typ=r["type"] if r["type"] in avals else "expense"; avals[typ]+=int(r["amount"])
        month_end_total=sum(projected_account_balance(c,a["id"],end) for a in c.execute("SELECT id FROM accounts WHERE active=1 AND start_date<=?",(end.isoformat(),)).fetchall())
        row={"month":f"{y:04d}-{m:02d}",
             "planned_income":euros(pvals["income"]),"planned_expense":euros(pvals["expense"]),"planned_savings":euros(pvals["savings"]),
             "actual_income":euros(avals["income"]),"actual_expense":euros(avals["expense"]),"actual_savings":euros(avals["savings"]),
             "month_end_balance":euros(month_end_total)}
        months.append(row)
        totals["planned_income"]+=pvals["income"]; totals["planned_expense"]+=pvals["expense"]; totals["planned_savings"]+=pvals["savings"]
        totals["actual_income"]+=avals["income"]; totals["actual_expense"]+=avals["expense"]; totals["actual_savings"]+=avals["savings"]
    result={"year":y,"months":months,"totals":{k:euros(v) for k,v in totals.items()}}
    return _cache_set("planning_year",result,*cache_key,ttl=30)


@app.get("/api/audit/timeline")
def audit_timeline(request: Request, q: str | None = None, page: int = 1, page_size: int = 25, limit: int | None = None, offset: int | None = None):
    require_book_owner(request);can_delete=True
    try:
        _,rec=_session_record(request);data=_auth_load_v2();book=data["books"][rec["book_id"]];member=book.get("members",{}).get(rec["user_key"],{})
        can_delete=member.get("role")=="owner" or data.get("users",{}).get(rec["user_key"],{}).get("system_role")=="admin"
    except HTTPException:
        pass
    if limit is not None:
        page_size=max(1,min(limit,200));page=max(1,((offset or 0)//page_size)+1)
    page=max(1,page);page_size=0 if page_size==0 else max(10,min(page_size,100));c=db.db();where="1=1";args=[]
    if q and q.strip():
        pat=f"%{q.strip()[:120]}%";where="(COALESCE(u.username,'') LIKE ? OR al.action LIKE ? OR al.entity_type LIKE ? OR COALESCE(al.entity_id,'') LIKE ? OR al.details_json LIKE ?)";args=[pat]*5
    total=int(c.execute("SELECT COUNT(*) FROM audit_log al LEFT JOIN users u ON u.id=al.user_id WHERE "+where,args).fetchone()[0])
    effective=max(total,1) if page_size==0 else page_size;pages=1 if page_size==0 else max(1,(total+effective-1)//effective);page=min(page,pages);offset=(page-1)*effective
    rows=c.execute(f"""SELECT al.id,al.user_id,u.username,al.action,al.entity_type,al.entity_id,al.details_json,al.entry_hash,al.created_at
                      FROM audit_log al LEFT JOIN users u ON u.id=al.user_id WHERE {where}
                      ORDER BY al.id DESC LIMIT ? OFFSET ?""",[*args,effective,offset]).fetchall()
    ok_chain,errors=audit_verify(c);items=[]
    for r in rows:
        try:details=json.loads(r["details_json"] or "{}")
        except Exception:details={}
        username=r["username"] or details.get("_actor_username") or "System / gelöschter Nutzer"
        items.append({"id":r["id"],"user_id":r["user_id"],"username":username,"action":r["action"],"entity_type":r["entity_type"],"entity_id":r["entity_id"],"details":details,"created_at":r["created_at"],"entry_hash":r["entry_hash"]})
    return {"items":items,"total":total,"page":page,"page_size":page_size,"pages":pages,"chain_ok":ok_chain,"chain_errors":errors,"can_delete":can_delete}

@app.delete("/api/audit/{audit_id}")
def audit_delete(audit_id: int,x: AuditDeleteIn,request: Request):
    sess=session(request,True);require_book_owner(request)
    if x.confirmation.strip().upper()!="LÖSCHEN": raise HTTPException(400,"Zur Bestätigung exakt LÖSCHEN eingeben")
    with db.transaction() as c:
        r=c.execute("SELECT id,action,entity_type,entity_id,created_at FROM audit_log WHERE id=?",(audit_id,)).fetchone()
        if not r: raise HTTPException(404,"Audit-Eintrag nicht gefunden")
        meta=dict(r)
        audit_append(c,sess[1],"audit.delete","audit",audit_id,{"deleted_action":meta["action"],"deleted_entity_type":meta["entity_type"],"deleted_entity_id":meta["entity_id"],"deleted_created_at":meta["created_at"]})
        c.execute("DELETE FROM audit_log WHERE id=?",(audit_id,));audit_rebuild_chain(c)
    return {"ok":True,"deleted":audit_id}

@app.get("/api/dashboard/year")
def dashboard_year(request: Request, year: int | None = None):
    return planning_year(request, year)

def _bulk_tx_where(mode: str, from_date: date | None, to_date: date | None):
    if mode=="all": return "1=1",[]
    if mode=="from":
        if not from_date: raise HTTPException(400,"Startdatum fehlt")
        return "booking_date>=?",[from_date.isoformat()]
    if not from_date or not to_date: raise HTTPException(400,"Von- und Bis-Datum fehlen")
    if to_date<from_date: raise HTTPException(400,"Bis-Datum liegt vor Von-Datum")
    return "booking_date BETWEEN ? AND ?",[from_date.isoformat(),to_date.isoformat()]

@app.get("/api/admin/storage")
def admin_storage(request: Request):
    require_book_owner(request);path=db.active_path();c=db.db()
    db_bytes=sum(Path(str(path)+suffix).stat().st_size for suffix in ("","-wal","-shm") if Path(str(path)+suffix).exists())
    attachments=int(c.execute("SELECT COALESCE(SUM(size),0) FROM attachments").fetchone()[0])
    tx_count=int(c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]);rec_count=int(c.execute("SELECT COUNT(*) FROM recurring").fetchone()[0])
    return {"database_path":str(path),"database_bytes":db_bytes,"database_file_bytes":path.stat().st_size if path.exists() else 0,
            "attachments_bytes":attachments,"attachment_limit_bytes":MAX_ATTACHMENT_TOTAL_BYTES,"transactions":tx_count,"recurring":rec_count}

@app.get("/api/admin/transactions-delete-preview")
def bulk_delete_preview(request: Request,mode: str="range",from_date: date|None=None,to_date: date|None=None):
    require_book_owner(request);where,args=_bulk_tx_where(mode,from_date,to_date);c=db.db()
    count=int(c.execute("SELECT COUNT(*) FROM transactions WHERE "+where,args).fetchone()[0])
    transfer_count=int(c.execute("SELECT COUNT(*) FROM transfers WHERE "+where,args).fetchone()[0])
    row=c.execute("SELECT MIN(booking_date),MAX(booking_date) FROM transactions WHERE "+where,args).fetchone()
    return {"count":count,"transfers":transfer_count,"from":row[0],"to":row[1],"mode":mode}

@app.delete("/api/admin/transactions")
def bulk_delete_transactions(x: BulkDeleteIn,request: Request):
    sess=session(request,True);require_book_owner(request)
    if x.confirmation.strip().upper()!="LÖSCHEN": raise HTTPException(400,"Zur Bestätigung exakt LÖSCHEN eingeben")
    where,args=_bulk_tx_where(x.mode,x.from_date,x.to_date)
    with db.transaction() as c:
        deleted_rows=c.execute("SELECT t.id,t.name,t.amount,t.booking_date,a.name account_name,t.payee,cat.name category_name FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories cat ON cat.id=t.category_id WHERE "+where+" ORDER BY t.booking_date,t.id",args).fetchall()
        deleted_items=[dict(r) for r in deleted_rows];count=len(deleted_items)
        transfer_count=int(c.execute("SELECT COUNT(*) FROM transfers WHERE "+where,args).fetchone()[0])
        c.execute("DELETE FROM recurring_occurrences WHERE transaction_id IN (SELECT id FROM transactions WHERE "+where+")",args)
        c.execute("DELETE FROM transactions WHERE "+where,args)
        c.execute("DELETE FROM transfers WHERE "+where,args)
        audit_append(c,sess[1],"transaction.bulk_delete","transaction",None,{"mode":x.mode,"from":x.from_date.isoformat() if x.from_date else None,"to":x.to_date.isoformat() if x.to_date else None,"count":count,"transfers":transfer_count,"deleted_items":deleted_items})
    return {"ok":True,"deleted":count,"transfers":transfer_count}

@app.get("/api/security")
def security_status(request: Request):
    session(request)
    info = db.cipher_info()
    integrity = db.integrity_check()
    return {**info, "cipher_integrity_ok": not integrity, "cipher_integrity_errors": integrity}


def _backup_snapshot_paths(book_id: str, kind: str, stamp: str) -> tuple[Path,Path]:
    folder=BACKUP_DIR/book_id/kind;folder.mkdir(parents=True,exist_ok=True)
    return folder/f"{stamp}.db",folder/f"{stamp}.meta.json"

def _prune_backup_storage() -> None:
    files=sorted([p for p in BACKUP_DIR.rglob('*') if p.is_file()],key=lambda p:p.stat().st_mtime)
    total=sum(p.stat().st_size for p in files)
    while files and total>MAX_BACKUP_STORAGE_BYTES:
        p=files.pop(0);size=p.stat().st_size
        try:p.unlink();total-=size
        except FileNotFoundError:pass

def rotate_internal_backups(book_id: str|None=None,path: Path|None=None,key: str|None=None) -> dict:
    key=key or db.current_key();path=Path(path or db.active_path())
    if not key or not path.exists():raise RuntimeError('Datenbank ist gesperrt')
    if book_id is None:
        book_id='default' if path==db.DB_PATH else path.stem
    db.checkpoint(True);now=date.today();created=[]
    specs=[('daily',now.isoformat()),('weekly',f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"),('monthly',now.strftime('%Y-%m'))]
    data=_auth_load_v2();book=data.get('books',{}).get(book_id,{})
    for kind,stamp in specs:
        dbp,metap=_backup_snapshot_paths(book_id,kind,stamp)
        if not dbp.exists():
            shutil.copy2(path,dbp);os.chmod(dbp,0o600)
            metap.write_text(json.dumps({'book_id':book_id,'book_name':book.get('name',book_id),'created_at':iso(utcnow())},ensure_ascii=False),encoding='utf-8');os.chmod(metap,0o600);created.append(str(dbp))
    for kind,keep in [('daily',7),('weekly',4),('monthly',12)]:
        folder=BACKUP_DIR/book_id/kind;dbs=sorted(folder.glob('*.db'),key=lambda p:p.stat().st_mtime,reverse=True) if folder.exists() else []
        for old in dbs[keep:]:old.unlink(missing_ok=True);old.with_suffix('.meta.json').unlink(missing_ok=True)
    _prune_backup_storage()
    return {'created':created,'book_id':book_id,'storage_bytes':sum(p.stat().st_size for p in (BACKUP_DIR/book_id).rglob('*') if p.is_file()) if (BACKUP_DIR/book_id).exists() else 0}

def verify_latest_internal_backup(book_id: str|None=None,key: str|None=None) -> dict:
    key=key or db.current_key();path=db.active_path();book_id=book_id or ('default' if path==db.DB_PATH else path.stem)
    folder=BACKUP_DIR/book_id;dbs=sorted(folder.rglob('*.db'),key=lambda p:p.stat().st_mtime,reverse=True) if folder.exists() else []
    if not dbs:return {'ok':False,'message':'Noch kein internes Backup vorhanden'}
    latest=dbs[0]
    try:db.verify_database_file(latest,key);return {'ok':True,'path':str(latest),'size':latest.stat().st_size,'checked_at':iso(utcnow())}
    except Exception as exc:return {'ok':False,'path':str(latest),'error':str(exc),'checked_at':iso(utcnow())}

@app.post('/api/backup/rotate')
def backup_rotate(request: Request):
    sess=session(request,True);require_book_owner(request);_,rec=_session_record(request);result=rotate_internal_backups(rec['book_id'],db.active_path(),rec['book_master'])
    with db.transaction() as c:audit_append(c,sess[1],'backup.rotate','backup',None,result)
    return result

@app.get('/api/backup/status')
def backup_status(request: Request):
    session(request);_,rec=_session_record(request);return verify_latest_internal_backup(rec['book_id'],rec['book_master'])

_backup_worker_started=False

def _backup_worker_loop():
    while True:
        threading.Event().wait(3600)
        with _app_session_lock: sessions=list(_app_sessions.values())
        seen=set()
        for rec in sessions:
            bid=rec.get('book_id')
            if not bid or bid in seen:continue
            seen.add(bid)
            try:
                data=_auth_load_v2();book=data.get('books',{}).get(bid)
                if book:db.activate(_book_path(book),rec['book_master']);rotate_internal_backups(bid,_book_path(book),rec['book_master'])
            except Exception:pass
        db.clear_context()

@app.on_event("startup")
def _start_backup_worker():
    global _backup_worker_started
    if not _backup_worker_started:
        threading.Thread(target=_backup_worker_loop,name="haushaltpro-backup",daemon=True).start();_backup_worker_started=True

def derive_backup_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA512(),length=32,salt=salt,iterations=600_000).derive(password.encode("utf-8"))

@app.post("/api/backup")
def backup(x: BackupIn,request: Request):
    session(request,True);require_book_owner(request);_,rec=_session_record(request);c=db.db();c.execute("PRAGMA wal_checkpoint(TRUNCATE)");c.commit();data=_auth_load_v2();book=data['books'][rec['book_id']];entry=data['users'][rec['user_key']];member=book['members'][rec['user_key']]
    auth_subset={'version':2,'users':{rec['user_key']:entry},'books':{rec['book_id']:{**book,'members':{rec['user_key']:member}}}}
    payload=json.dumps({'format':4,'book_id':rec['book_id'],'book_name':book.get('name'),'database':base64.b64encode(db.active_path().read_bytes()).decode('ascii'),'auth':auth_subset},separators=(',',':')).encode('utf-8')
    salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12);key=derive_backup_key(x.password,salt);header=b"HPB4"+salt+nonce;encrypted=AESGCM(key).encrypt(nonce,payload,header)
    safe=''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in book.get('name','haushalt'))
    return Response(header+encrypted,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="haushaltpro-{safe}.hpb"','Cache-Control':'no-store'})

@app.post("/api/restore")
async def restore(request: Request,response: Response,file: UploadFile=File(...),backup_password: str=Form(...),database_password: str=Form(...)):
    sess=session(request,True);require_book_owner(request);_,rec=_session_record(request);current_username=rec['username'];blob=await file.read(MAX_UPLOAD*5+1)
    if len(blob)>MAX_UPLOAD*5:raise HTTPException(413,"Backup-Datei ist zu groß")
    if len(blob)<33 or blob[:4] not in {b"HPB2",b"HPB3",b"HPB4"}:raise HTTPException(400,"Ungültiges Backup-Format")
    salt,nonce,encrypted=blob[4:20],blob[20:32],blob[32:];header=blob[:32]
    try:plain=AESGCM(derive_backup_key(backup_password,salt)).decrypt(nonce,encrypted,header)
    except Exception:raise HTTPException(400,"Backup-Passwort falsch oder Backup beschädigt")
    if blob[:4]==b"HPB4":
        try:payload=json.loads(plain.decode());data_bytes=base64.b64decode(payload['database'],validate=True);backup_auth=payload['auth']
        except Exception:raise HTTPException(400,"Backup-Inhalt ist beschädigt")
        user_key=current_username.casefold();entry=backup_auth.get('users',{}).get(user_key);book=next(iter(backup_auth.get('books',{}).values()),None)
        if not entry or not book:raise HTTPException(400,"Aktueller Benutzer ist im Backup nicht enthalten")
        try:ph.verify(entry['password_hash'],database_password);private=_unlock_private(database_password,entry['private_key']);member=book['members'][user_key];verify_key=_unwrap_master(private,member['wrapped_master'])
        except Exception:raise HTTPException(400,"Login-Passwort für die Backup-Datenbank ist falsch")
    else:
        # Legacy restore is supported only into the default household.
        if rec['book_id']!='default':raise HTTPException(400,"Altes Backup-Format kann nur in das ursprüngliche Haushaltsbuch eingespielt werden")
        if blob[:4]==b"HPB3":
            payload=json.loads(plain.decode());data_bytes=base64.b64decode(payload['database'],validate=True);legacy_auth=payload.get('auth');entry=legacy_auth.get('users',{}).get(current_username.casefold()) if legacy_auth else None
            if not entry:raise HTTPException(400,"Aktueller Benutzer fehlt im Backup")
            try:ph.verify(entry['password_hash'],database_password);private=_unlock_private(database_password,entry['private_key']);verify_key=_unwrap_master(private,entry['wrapped_master'])
            except Exception:raise HTTPException(400,"Login-Passwort für die Backup-Datenbank ist falsch")
        else:data_bytes=plain;verify_key=database_password
    target=db.active_path();temp=target.with_suffix('.restore.tmp');temp.write_bytes(data_bytes);os.chmod(temp,0o600)
    try:db.verify_database_file(temp,verify_key)
    except Exception as exc:temp.unlink(missing_ok=True);raise HTTPException(400,f"Backup-Datenbank konnte nicht verifiziert werden: {exc}")
    for suffix in ('-wal','-shm'):Path(str(target)+suffix).unlink(missing_ok=True)
    os.replace(temp,target)
    # HPB4 restores data only; current user/book access metadata stays intact.
    rec['book_master']=verify_key
    data=_auth_load_v2();book=data['books'][rec['book_id']]
    for member_key,member in book.get('members',{}).items():
        user=data.get('users',{}).get(member_key)
        if user: member['wrapped_master']=_wrap_master(user['public_key'],verify_key)
    _auth_save(data)
    with _app_session_lock:
        for token in list(_app_sessions):
            if token!=token_hash(request.cookies.get(COOKIE_NAME,'')) and _app_sessions[token].get('book_id')==rec['book_id']:_app_sessions.pop(token,None)
    delete_cookie(response);with_token=token_hash(request.cookies.get(COOKIE_NAME,''));_app_sessions.pop(with_token,None);return {'ok':True,'relogin_required':True}


class InvestmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    symbol: str | None = Field(default=None, max_length=24)
    asset_type: str = "stock"
    quantity: Decimal = Field(ge=0)
    purchase_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    current_price: Decimal = Field(default=Decimal("0.00"), ge=0)
    fees: Decimal = Field(default=Decimal("0.00"), ge=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)

    @field_validator("asset_type")
    @classmethod
    def investment_type_ok(cls, value):
        if value not in {"stock","etf","fund","crypto","p2p","fixed_deposit","manual"}:
            raise ValueError("Ungültiger Asset-Typ")
        return value

def require_investments(c):
    if setting_value(c, "investment_tracking", "false") != "true":
        raise HTTPException(404, "Investment Tracking ist deaktiviert")

def investment_row(r):
    item = dict(r)
    qty = Decimal(str(item.get("quantity") or 0))
    purchase_cents = int(item.get("purchase_price_cents") or 0)
    current_cents = int(item.get("manual_price_cents") or 0)
    fees_cents = int(item.get("fees_cents") or 0)
    cost_cents = int((qty * Decimal(purchase_cents)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) + fees_cents
    value_cents = int((qty * Decimal(current_cents)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    gain_cents = value_cents - cost_cents
    perf = (Decimal(gain_cents) / Decimal(cost_cents) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if cost_cents else Decimal("0")
    item.update({"quantity":str(qty.normalize()),"purchase_price":euros(purchase_cents),"current_price":euros(current_cents),"fees":euros(fees_cents),
                 "cost_basis":euros(cost_cents),"market_value":euros(value_cents),"gain":euros(gain_cents),"performance_pct":float(perf)})
    return item

@app.get("/api/investments")
def investments(request: Request):
    session(request)
    c = db.db(); require_investments(c)
    rows=[investment_row(r) for r in c.execute("SELECT * FROM investment_assets WHERE active=1 ORDER BY name").fetchall()]
    total_cost_cents=sum(cents(x["cost_basis"]) for x in rows); total_value_cents=sum(cents(x["market_value"]) for x in rows)
    for x in rows:
        x["allocation_pct"]=float((Decimal(cents(x["market_value"]))/Decimal(total_value_cents)*100).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)) if total_value_cents else 0
    gain_cents=total_value_cents-total_cost_cents
    perf=float((Decimal(gain_cents)/Decimal(total_cost_cents)*100).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)) if total_cost_cents else 0
    return {"assets":rows,"total_cost":euros(total_cost_cents),"total_value":euros(total_value_cents),"gain":euros(gain_cents),"performance_pct":perf}

@app.post("/api/investments")
def investment_create(x: InvestmentIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        require_investments(c)
        cur=c.execute("""INSERT INTO investment_assets(name,symbol,asset_type,quantity,purchase_price,manual_price,fees,purchase_price_cents,manual_price_cents,fees_cents,currency,active)
                         VALUES(?,?,?,?,0,NULL,0,?,?,?,?,1)""",
                      (x.name.strip(), clean_text(x.symbol,24), x.asset_type, str(x.quantity), cents(x.purchase_price), cents(x.current_price), cents(x.fees), x.currency.upper()))
        audit_append(c,sess[1],"investment.create","investment",cur.lastrowid,{"name":x.name.strip(),"added":{"name":x.name.strip(),"symbol":clean_text(x.symbol,24),"asset_type":x.asset_type,"quantity":str(x.quantity),"purchase_price_cents":cents(x.purchase_price),"manual_price_cents":cents(x.current_price),"fees_cents":cents(x.fees),"currency":x.currency.upper()}})
        return {"id":cur.lastrowid}

@app.put("/api/investments/{asset_id}")
def investment_update(asset_id: int, x: InvestmentIn, request: Request):
    sess=session(request, True)
    with db.transaction() as c:
        require_investments(c)
        old_row=c.execute("SELECT name,symbol,asset_type,quantity,purchase_price_cents,manual_price_cents,fees_cents,currency FROM investment_assets WHERE id=? AND active=1",(asset_id,)).fetchone()
        if not old_row: raise HTTPException(404, "Investment nicht gefunden")
        before=dict(old_row)
        cur=c.execute("UPDATE investment_assets SET name=?,symbol=?,asset_type=?,quantity=?,purchase_price=0,manual_price=NULL,fees=0,purchase_price_cents=?,manual_price_cents=?,fees_cents=?,currency=? WHERE id=? AND active=1",
                      (x.name.strip(), clean_text(x.symbol,24), x.asset_type, str(x.quantity), cents(x.purchase_price), cents(x.current_price), cents(x.fees), x.currency.upper(), asset_id))
        after=dict(c.execute("SELECT name,symbol,asset_type,quantity,purchase_price_cents,manual_price_cents,fees_cents,currency FROM investment_assets WHERE id=?",(asset_id,)).fetchone())
        audit_append(c,sess[1],"investment.update","investment",asset_id,{"name":after.get("name"),"changes":audit_changes(before,after,("name","symbol","asset_type","quantity","purchase_price_cents","manual_price_cents","fees_cents","currency")),"current":audit_pick(after,("name","symbol","asset_type","quantity","purchase_price_cents","manual_price_cents","fees_cents","currency"))})
    return {"ok":True}

@app.delete("/api/investments/{asset_id}")
def investment_delete(asset_id: int, request: Request):
    session(request, True)
    with db.transaction() as c:
        require_investments(c)
        c.execute("UPDATE investment_assets SET active=0 WHERE id=?", (asset_id,))
    return {"ok":True}
