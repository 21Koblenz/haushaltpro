"""Exact CSV amounts, filters, split semantics and recurring dates across years."""
import csv
import io
import sqlite3
import sys
import tempfile
import types
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
    c = sqlite3.connect(Path(tmp) / "export.db", check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    db._conn = c
    db.init_schema(c)
    main.session = lambda request, write=False: ("test", 1, "csrf", 0)
    client = TestClient(main.app)
    def ok(r):
        assert r.status_code == 200, (r.status_code, r.text)
        return r.json()
    def rows(url):
        r = client.get(url)
        assert r.status_code == 200, r.text
        assert r.content.startswith(b"\xef\xbb\xbf")
        assert "no-store" in r.headers["cache-control"] and "attachment;" in r.headers["content-disposition"]
        return list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")), delimiter=";"))
    aid = ok(client.post("/api/accounts", json={"name": "Giro", "opening_balance": 1000, "start_date": "2025-01-01"}))["id"]
    other = ok(client.post("/api/accounts", json={"name": "Zweitkonto", "opening_balance": 0, "start_date": "2025-01-01"}))["id"]
    payload = dict(account_id=aid, amount="10.01", booking_date="2026-09-10",
                   name=" =1+2", payee='A;B "C"', category_id=1, note="Zeile 1\nZeile 2", tags=["tag"])
    first = ok(client.post("/api/transactions", json=payload))["id"]
    split = ok(client.post("/api/transactions", json={**payload, "name": "Split", "amount": "30",
                    "splits": [{"category_id": 1, "amount": "-10"}, {"category_id": 2, "amount": "-20"}]}))["id"]
    for i in range(30):
        ok(client.post("/api/transactions", json={**payload, "name": f"Buchung {i}", "amount": "1"}))
    gone = ok(client.post("/api/transactions", json={**payload, "amount": "999"}))["id"]
    ok(client.delete(f"/api/transactions/{gone}"))
    exported = rows("/api/export/transactions.csv?from_date=2026-09-01&to_date=2026-09-30")
    assert len(exported) == 33  # no pagination truncation; two rows for one split
    first_row = next(r for r in exported if r["Buchungs-ID"] == str(first))
    assert first_row["Name"].startswith("'=") and first_row["Betrag (EUR)"] == "-10,01"
    assert first_row["Empfänger"] == 'A;B "C"' and first_row["Notiz"] == "Zeile 1\nZeile 2"
    assert sum(main.cents(r["Betrag (EUR)"].replace(",", ".")) for r in exported) == -7001
    cat_rows = rows("/api/export/transactions.csv?category_id=2")
    assert len(cat_rows) == 1 and cat_rows[0]["Teil-ID"] and cat_rows[0]["Betrag (EUR)"] == "-20,00"
    assert rows(f"/api/export/transactions.csv?account_id={other}") == []
    assert len(rows("/api/export/transactions.csv?q=Split")) == 2
    assert client.get("/api/export/transactions.csv?from_date=2026-10-01&to_date=2026-09-01").status_code == 400
    assert client.get("/api/export/transactions.csv?status=invalid").status_code == 422
    # Recurring plans use schedule occurrences, never journal+schedule twice.
    rec = dict(account_id=aid, category_id=1, name="Miete", amount="100", next_date="2026-09-20",
               frequency="monthly", valid_until="2026-11-20", fixed_cost=True)
    rid = ok(client.post("/api/recurring", json=rec))["id"]
    ok(client.put(f"/api/recurring/{rid}/override", json={"due_date":"2026-09-20","booking_date":"2026-10-01","amount":"100"}))
    annual = ok(client.post("/api/recurring", json={**rec, "name": "Versicherung", "amount": "1200",
                   "next_date": "2026-12-20", "frequency": "yearly", "valid_until": "2026-12-20"}))["id"]
    ok(client.put(f"/api/recurring/{annual}/override", json={"due_date":"2026-12-20","booking_date":"2027-01-01","amount":"1200"}))
    ok(client.post("/api/transactions", json={**payload, "name":"Einmalige Fixkosten", "amount":"50", "fixed_cost":True}))
    costs = rows("/api/export/fixed-costs.csv?year=2026")
    rent = next(r for r in costs if r["Name"] == "Miete")
    assert rent["2026-09 (EUR)"] == "0,00" and rent["2026-10 (EUR)"] == "200,00"
    assert rent["2026-11 (EUR)"] == "100,00" and rent["Jahr (EUR)"] == "300,00"
    total = next(r for r in costs if r["Typ"] == "Summe")
    assert total["Jahr (EUR)"] == "350,00"
    for month in range(1, 13):
        key = f"2026-{month:02d}"
        assert main.cents(total[key+" (EUR)"].replace(",", ".")) == main.planned_fixed_costs(c, *main.month_bounds(key))
    costs_next = rows("/api/export/fixed-costs.csv?year=2027")
    insurance = next(r for r in costs_next if r["Name"] == "Versicherung")
    assert insurance["2027-01 (EUR)"] == "1200,00" and insurance["Jahr (EUR)"] == "1200,00"
    assert rows(f"/api/export/fixed-costs.csv?year=2026&account_id={other}")[-1]["Jahr (EUR)"] == "0,00"
    assert rows("/api/export/fixed-costs.csv?year=2026&category_id=2")[-1]["Jahr (EUR)"] == "0,00"
    c.close()
print("CSV exports: exact cents, full results, split/category/date/account filters, formula escaping and monthly/yearly fixed costs: PASS")
