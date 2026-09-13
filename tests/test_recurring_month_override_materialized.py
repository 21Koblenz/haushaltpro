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
c.execute("PRAGMA foreign_keys=ON")
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

account = client.post("/api/accounts", json={
    "name": "Girokonto",
    "type": "checking",
    "opening_balance": "0",
    "currency": "EUR",
    "start_date": "2026-09-01",
})
assert account.status_code == 200, account.text
account_id = account.json()["id"]

created = client.post("/api/transactions", json={
    "account_id": account_id,
    "amount": "1000.00",
    "booking_date": "2026-09-10",
    "name": "Gehalt",
    "category_id": 5,
    "recurring": True,
    "recurring_frequency": "monthly",
    "confidence": "fixed",
    "fixed_cost": False,
})
assert created.status_code == 200, created.text
transaction_id = created.json()["id"]
recurring_id = created.json()["recurring_id"]
assert recurring_id

before = c.execute("SELECT amount FROM transactions WHERE id=?", (transaction_id,)).fetchone()
assert before["amount"] == 100000, before["amount"]
assert client.get("/api/dashboard?month=2026-09").json()["total_balance"] == 1000.0

override = client.put(f"/api/recurring/{recurring_id}/override", json={
    "due_date": "2026-09-10",
    "amount": "1200.00",
    "note": "Diesen Monat angepasst",
})
assert override.status_code == 200, override.text
assert override.json()["amount"] == 1200.0, override.json()

stored_override = c.execute(
    "SELECT amount FROM recurring_overrides WHERE series_id=? AND due_date=?",
    (recurring_id, "2026-09-10"),
).fetchone()
assert stored_override["amount"] == 120000, stored_override["amount"]
materialized = c.execute("SELECT amount,direction FROM transactions WHERE id=?", (transaction_id,)).fetchone()
assert materialized["amount"] == 120000, dict(materialized)
assert materialized["direction"] == "income", dict(materialized)
assert client.get("/api/dashboard?month=2026-09").json()["total_balance"] == 1200.0

removed = client.delete(f"/api/recurring/{recurring_id}/override?due_date=2026-09-10")
assert removed.status_code == 200, removed.text
assert c.execute(
    "SELECT 1 FROM recurring_overrides WHERE series_id=? AND due_date=?",
    (recurring_id, "2026-09-10"),
).fetchone() is None
reverted = c.execute("SELECT amount,direction FROM transactions WHERE id=?", (transaction_id,)).fetchone()
assert reverted["amount"] == 100000, dict(reverted)
assert reverted["direction"] == "income", dict(reverted)
assert client.get("/api/dashboard?month=2026-09").json()["total_balance"] == 1000.0

history = c.execute(
    "SELECT action FROM transaction_history WHERE transaction_id=? ORDER BY id",
    (transaction_id,),
).fetchall()
actions = [row["action"] for row in history]
assert "recurring_override" in actions, actions
assert "recurring_override_delete" in actions, actions

print("materialized recurring monthly override + revert regression: PASS")
c.close()
Path(tmp).unlink(missing_ok=True)
