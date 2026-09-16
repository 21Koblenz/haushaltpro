"""Independent cash/remaining-balance checks, retries and destructive booking edits."""
import sqlite3
import sys
import tempfile
import types
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

shim = types.ModuleType("sqlcipher3")
shim.dbapi2 = sqlite3
sys.modules["sqlcipher3"] = shim
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
Path("/app").mkdir(exist_ok=True)
mount = Path("/app/static")
if mount.is_symlink() and mount.resolve() != root / "static":
    mount.unlink()
if not mount.exists():
    mount.symlink_to(root / "static", target_is_directory=True)
from app import db, main
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory() as tmp:
    c = sqlite3.connect(Path(tmp) / "items.db", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    db._conn = c
    db.init_schema(c)
    main.session = lambda request, write=False: ("test", 1, "csrf", 0)
    client = TestClient(main.app)
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    def ok(r):
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()

    aid = ok(client.post("/api/accounts", json={"name": "Giro", "opening_balance": "1000", "start_date": "2025-01-01"}))["id"]

    def create(kind="receivable", amount="200", **extra):
        body = dict(kind=kind, name="Privatdarlehen", payee="Max", amount=amount, due_date=yesterday, **extra)
        return ok(client.post("/api/open-items", json=body))["id"], body

    def item(i):
        return ok(client.get(f"/api/open-items/{i}"))

    def pay(i, amount, **extra):
        return client.post(f"/api/open-items/{i}/payments", json={"amount": amount, **extra})

    def new_payment(i, amount="50", **extra):
        body = dict(amount=amount, account_id=aid, booking_date=today, category_id=5)
        body.update(extra)
        return client.post(f"/api/open-items/{i}/payments", json=body)

    def cash():
        return main.account_balance(c, aid, date.today())

    oid, body = create()
    assert item(oid)["remaining"] == 200 and item(oid)["overdue"] and cash() == 100000
    first = ok(new_payment(oid))
    assert item(oid)["paid"] == 50 and item(oid)["remaining"] == 150
    assert item(oid)["status"] == "partial" and cash() == 105000
    txbody = dict(account_id=aid, amount="75", booking_date=today, name="Rückzahlung", category_id=5)
    tid = ok(client.post("/api/transactions", json=txbody))["id"]
    second = ok(pay(oid, "50", transaction_id=tid))
    assert cash() == 112500 and item(oid)["remaining"] == 100
    assert pay(oid, "1", transaction_id=tid).status_code == 409
    other, _ = create(amount="40")
    assert pay(other, "26", transaction_id=tid).status_code == 409
    ok(pay(other, "25", transaction_id=tid))
    assert item(other)["remaining"] == 15
    assert client.put(f"/api/transactions/{tid}", json={**txbody, "amount": "74.99"}).status_code == 409
    assert client.put(f"/api/transactions/{tid}", json={**txbody, "category_id": 1}).status_code == 409
    assert client.put(f"/api/transactions/{tid}", json={**txbody, "booking_date": tomorrow}).status_code == 409
    ok(client.put(f"/api/transactions/{tid}", json={**txbody, "name": "Korrigierter Text"}))
    assert client.put(f"/api/open-items/{oid}", json={**body, "amount": "99.99"}).status_code == 409
    assert client.put(f"/api/open-items/{oid}", json={**body, "kind": "payable"}).status_code == 409
    ok(client.delete(f"/api/open-items/{oid}/payments/{second['id']}"))
    assert cash() == 112500 and item(oid)["remaining"] == 150
    ok(client.delete(f"/api/transactions/{tid}"))
    assert item(other)["remaining"] == 40 and item(other)["payments"] == []
    assert cash() == 105000
    ok(client.delete(f"/api/transactions/{first['transaction_id']}?hard=true"))
    assert item(oid)["remaining"] == 200 and cash() == 100000

    # A settled item disappears from outstanding; overpayment and bad requests
    # never leave a new cash booking behind.
    count = c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    assert new_payment(oid, "201").status_code == 409
    assert new_payment(oid, category_id=1).status_code == 400
    assert new_payment(oid, booking_date=tomorrow).status_code == 400
    assert new_payment(oid, account_id=99999).status_code == 400
    assert new_payment(oid, "0.001").status_code == 422
    assert c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == count
    ok(new_payment(oid, "200"))
    assert item(oid)["status"] == "paid" and not item(oid)["overdue"]
    assert oid not in [x["id"] for x in ok(client.get("/api/open-items"))["items"]]
    assert oid in [x["id"] for x in ok(client.get("/api/open-items?state=paid"))["items"]]

    # Same write intent, concurrent sends and a replay after a lost reply.
    concurrent, _ = create(amount="100")
    payload = dict(amount="60", account_id=aid, booking_date=today, category_id=5)
    def send(_):
        return ok(TestClient(main.app).post(f"/api/open-items/{concurrent}/payments",
                  json=payload, headers={"X-Idempotency-Key": "same-payment-intent"}))
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(send, range(4)))
    assert len({r["id"] for r in responses}) == 1
    assert item(concurrent)["paid"] == 60 and len(item(concurrent)["payments"]) == 1
    assert client.post(f"/api/open-items/{other}/payments", json=payload,
                       headers={"X-Idempotency-Key": "same-payment-intent"}).status_code == 409
    cancelled, cancel_body = create(amount="100")
    ok(new_payment(cancelled, "25"))
    ok(client.put(f"/api/open-items/{cancelled}", json={**cancel_body, "cancelled": True}))
    assert item(cancelled)["status"] == "cancelled" and item(cancelled)["paid"] == 25
    assert new_payment(cancelled, "10").status_code == 409
    ok(client.put(f"/api/open-items/{cancelled}", json=cancel_body))
    assert item(cancelled)["status"] == "partial"

    # Payables use negative cash flow and exclude transfers/future/planned rows.
    payable, _ = create("payable", "90.01")
    paid = ok(new_payment(payable, "30.01", category_id=1))
    assert item(payable)["remaining"] == 60
    assert c.execute("SELECT amount FROM transactions WHERE id=?", (paid["transaction_id"],)).fetchone()[0] == -3001
    assert pay(other, "1", transaction_id=paid["transaction_id"]).status_code == 409
    future = ok(client.post("/api/transactions", json={**txbody, "booking_date": tomorrow}))["id"]
    assert pay(other, "1", transaction_id=future).status_code == 409
    candidate_ids = {x["id"] for x in ok(client.get(f"/api/open-items/{other}/candidates"))["items"]}
    assert future not in candidate_ids and paid["transaction_id"] not in candidate_ids
    # Imported legacy foreign-currency accounts cannot mix currencies into EUR items.
    fx = ok(client.post("/api/accounts", json={"name": "Legacy USD", "start_date": "2025-01-01"}))["id"]
    foreign_tx = ok(client.post("/api/transactions", json={**txbody, "account_id": fx}))["id"]
    c.execute("UPDATE accounts SET currency='USD' WHERE id=?", (fx,))
    c.commit()
    assert pay(other, "1", transaction_id=foreign_tx).status_code == 400
    assert new_payment(other, "1", account_id=fx).status_code == 400
    assert foreign_tx not in {x["id"] for x in ok(client.get(f"/api/open-items/{other}/candidates"))["items"]}
    due_today, today_body = create(amount="10")
    ok(client.put(f"/api/open-items/{due_today}", json={**today_body, "due_date": today}))
    assert not item(due_today)["overdue"]
    assert ok(client.get("/api/open-items?q=Privatdarlehen"))["total"] > 0
    assert main.audit_verify(c)[0]
    db.migrate_schema(c)
    db.migrate_schema(c)
    assert item(payable)["remaining"] == 60 and item(concurrent)["paid"] == 60
    assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.close()
print("open items: partial payments, cash neutrality, allocation bounds, edits, cancellation, retry concurrency and migration: PASS")
