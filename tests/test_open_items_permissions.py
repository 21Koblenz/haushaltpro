"""Exercise actual authentication, CSRF, roles and book boundaries on new routes."""
import sqlite3
import sys
import tempfile
import types
from datetime import date
from pathlib import Path

shim = types.ModuleType("sqlcipher3")
shim.dbapi2 = sqlite3
sys.modules["sqlcipher3"] = shim
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
Path("/app").mkdir(exist_ok=True)
mount = Path("/app/static")
if not mount.exists():
    mount.symlink_to(root / "static", target_is_directory=True)
from app import db, main
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    def plain_connect(key, path=None):
        target = Path(path or db.DB_PATH)
        target.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(target, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c
    db.close()
    db._conn = None
    db.connect = plain_connect
    db.DB_PATH = base / "household.db"
    main.AUTH_PATH = base / "auth.json"
    main.BOOKS_DIR = base / "books"
    main.BACKUP_DIR = base / "backups"
    main._app_sessions.clear()
    admin, viewer, editor, anon = [TestClient(main.app) for _ in range(4)]
    def ok(r):
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()
    def write(client, method, path, data=None, headers=None):
        token = ok(client.get("/api/me"))["csrf"]
        return client.request(method, path, json=data, headers={"X-CSRF-Token": token, **(headers or {})})
    ok(admin.post("/api/setup", json={"username":"admin","password":"DisposableTestPass123!"}))
    for client, name, role in [(viewer, "reader", "viewer"), (editor, "editor", "editor")]:
        ok(write(admin, "POST", "/api/users", {"username":name,"password":"DisposableTestPass456!","role":role}))
        ok(client.post("/api/login", json={"username":name,"password":"DisposableTestPass456!"}))
    body = {"kind":"receivable","name":"Privatdarlehen","payee":"Test","amount":"200"}
    oid = ok(write(editor, "POST", "/api/open-items", body))["id"]
    assert ok(viewer.get(f"/api/open-items/{oid}"))["remaining"] == 200
    assert write(viewer, "POST", "/api/open-items", body).status_code == 403
    assert write(viewer, "PUT", f"/api/open-items/{oid}", body).status_code == 403
    assert write(viewer, "POST", f"/api/open-items/{oid}/payments", {"amount":"1","transaction_id":1}).status_code == 403
    assert write(viewer, "DELETE", f"/api/open-items/{oid}/payments/1").status_code == 403
    assert editor.post("/api/open-items", json=body).status_code == 403
    for path in ["/api/open-items", f"/api/open-items/{oid}", f"/api/open-items/{oid}/candidates",
                 "/api/export/transactions.csv", "/api/export/fixed-costs.csv?year=2026"]:
        assert anon.get(path).status_code == 401, path
        assert viewer.get(path).status_code == 200, path
    book = ok(write(admin, "POST", "/api/books", {"name":"Separate Test Book"}))["id"]
    ok(write(admin, "POST", f"/api/books/{book}/switch"))
    assert ok(admin.get("/api/open-items"))["total"] == 0
    assert admin.get(f"/api/open-items/{oid}").status_code == 404
    assert write(admin, "POST", "/api/open-items", body,
                 {"X-HaushaltPro-Book":"default"}).status_code == 409
    db.close()
print("open items and exports: authentication, CSRF, viewer/editor permissions and household isolation: PASS")
