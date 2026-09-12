import sqlite3
import sys
import tempfile
import types
from pathlib import Path

shim = types.ModuleType("sqlcipher3")
shim.dbapi2 = sqlite3
sys.modules["sqlcipher3"] = shim
root = Path(__file__).resolve().parents[1]
Path("/app").mkdir(exist_ok=True)
static_mount = Path("/app/static")
if static_mount.is_symlink() and static_mount.resolve() != (root / "static").resolve():
    static_mount.unlink()
if not static_mount.exists():
    static_mount.symlink_to(root / "static", target_is_directory=True)
sys.path.insert(0, str(root))

from app import db
fd, tmp = tempfile.mkstemp(suffix=".db")
Path(tmp).unlink(missing_ok=True)
c = sqlite3.connect(tmp, check_same_thread=False)
c.row_factory = sqlite3.Row
c.execute("PRAGMA foreign_keys=ON")
db._conn = c
db.DB_PATH = Path(tmp)
db.init_schema(c)

from app import main
main.db._conn = c
main.session = lambda request, write=False: ("test", 1, "csrf", 0)
from fastapi.testclient import TestClient
client = TestClient(main.app)

payload = {
    "name": "Dispo Test",
    "type": "checking",
    "opening_balance": "-1234.56",
    "currency": "EUR",
    "start_date": "2026-09-01",
}
r = client.post("/api/accounts", json=payload)
assert r.status_code == 200, (r.status_code, r.text)
account_id = r.json()["id"]
row = c.execute("SELECT opening_balance FROM accounts WHERE id=?", (account_id,)).fetchone()
assert row["opening_balance"] == -123456, row["opening_balance"]
accounts = client.get("/api/accounts?month=2026-09").json()
account = next(x for x in accounts if x["id"] == account_id)
assert account["opening_balance"] == -1234.56, account
assert account["month_start_balance"] == -1234.56, account
assert account["balance"] == -1234.56, account
assert account["month_end_balance"] == -1234.56, account

enhancements = (root / "static/ui-enhancements.js").read_text(encoding="utf-8")
assert "function normalizeSignedMoneyInput" in enhancements
assert "new Set(['opening_balance', 'actual_balance'])" in enhancements
assert "input.type = 'text'" in enhancements
assert "input.inputMode = 'decimal'" in enhancements
assert "toggle.textContent = '±'" in enhancements
assert "value = value.replace(',', '.')" in enhancements
assert "Guthaben positiv, Soll/Dispo negativ" in enhancements

index = (root / "static/index.html").read_text(encoding="utf-8")
style = (root / "static/ui-enhancements.css").read_text(encoding="utf-8")
assert "/assets/ui-enhancements.js" in index and "/assets/ui-enhancements.css" in index
assert index.count("lightning:creamowl25@primal.net") >= 2
assert "/assets/lightning-qr-black.svg" in index
assert "filter:invert(1)" in style
assert 'html[data-theme="light"] .footer-lightning-qr{filter:none}' in style
qr = root / "static/lightning-qr-black.svg"
assert qr.exists() and qr.stat().st_size > 1000
qr_content = qr.read_text(encoding="utf-8")
assert "<svg" in qr_content and "#000000" in qr_content

print("negative account opening balance + mobile signed input + V4V footer: PASS")
c.close()
Path(tmp).unlink(missing_ok=True)
