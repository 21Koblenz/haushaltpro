import sqlite3
import sys
import tempfile
import types
from datetime import date as real_date
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
a.execute("PRAGMA foreign_keys=ON")
db._conn = c
db.DB_PATH = Path(tmp)
db.init_schema(c)

from app import main
main.db._conn = c
main.session = lambda request, write=False: ("test", 1, "csrf", 0)

class FixedDate(real_date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 20)

main.date = FixedDate

from fastapi.testclient import TestClient
client = TestClient(main.app)

payload = {
    "name": "Dispo ab Monatsmitte",
    "type": "checking",
    "opening_balance": "-1234.56",
    "currency": "EUR",
    "start_date": "2026-09-12",
}
r = client.post("/api/accounts", json=payload)
assert r.status_code == 200, (r.status_code, r.text)
account_id = r.json()["id"]

series = main.monthly_account_series(c, account_id, "2026-09")
by_date = {p["date"]: p["balance"] for p in series}
assert series[0]["opening_balance"] == 0.0, series[0]
assert by_date["2026-09-11"] == 0.0, by_date["2026-09-11"]
assert by_date["2026-09-12"] == -1234.56, by_date["2026-09-12"]
assert by_date["2026-09-30"] == -1234.56, by_date["2026-09-30"]

accounts = client.get("/api/accounts?month=2026-09")
assert accounts.status_code == 200, accounts.text
account = next(x for x in accounts.json() if x["id"] == account_id)
assert account["month_start_balance"] == 0.0, account
assert account["balance"] == -1234.56, account
assert account["month_end_balance"] == -1234.56, account

dash = client.get("/api/dashboard?month=2026-09")
assert dash.status_code == 200, dash.text
data = dash.json()
assert data["cutoff"] == "2026-09-20", data["cutoff"]
assert data["total_balance"] == -1234.56, data
assert data["month_end_balance"] == -1234.56, data
assert data["pending_outflows"] == 0.0, data
assert data["accounts"][0]["month_start_balance"] == 0.0, data["accounts"][0]
assert data["accounts"][0]["balance"] == -1234.56, data["accounts"][0]

r = client.put(
    f"/api/accounts/{account_id}/month-opening",
    json={"month": "2026-09", "opening_balance": "-2000.00", "note": "Korrektur"},
)
assert r.status_code == 200, (r.status_code, r.text)
dash2 = client.get("/api/dashboard?month=2026-09").json()
assert dash2["total_balance"] == -2000.0, dash2
assert dash2["month_end_balance"] == -2000.0, dash2

print("mid-month opening balance dashboard regression: PASS")
c.close()
Path(tmp).unlink(missing_ok=True)
