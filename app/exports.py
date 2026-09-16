"""Read-only CSV exports using the same booking and recurring plan semantics."""
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response

from . import db

router = APIRouter(prefix="/api/export")
MAX_EXPORT_ROWS = 100_000


def _core():
    from . import main
    return main


def safe_text(value):
    """Spreadsheet applications must treat user-controlled content as text."""
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def money(value):
    return format(Decimal(int(value)) / 100, ".2f").replace(".", ",")


def download(filename, header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return Response(("\ufeff" + output.getvalue()).encode("utf-8"),
                    media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/transactions.csv")
def transactions_csv(request: Request, from_date: date | None = None, to_date: date | None = None,
                     account_id: int | None = None, category_id: int | None = None,
                     q: str = Query(default="", max_length=100),
                     status: Literal["all", "executed", "planned"] = "all"):
    _core().session(request)
    if from_date and to_date and from_date > to_date:
        raise HTTPException(400, "Beginn darf nicht nach dem Ende liegen")
    c = db.db()
    where, args = ["t.status<>'cancelled'"], []
    for clause, value in (
        ("t.booking_date>=?", from_date.isoformat() if from_date else None),
        ("t.booking_date<=?", to_date.isoformat() if to_date else None),
        ("t.account_id=?", account_id),
        ("CASE WHEN s.id IS NULL THEN t.category_id ELSE s.category_id END=?", category_id),
        ("t.status=?", status if status != "all" else None),
    ):
        if value is not None:
            where.append(clause)
            args.append(value)
    if q:
        where.append("""(COALESCE(t.name,'') LIKE ? OR COALESCE(t.payee,'') LIKE ?
            OR COALESCE(t.note,'') LIKE ? OR COALESCE(cat.name,'') LIKE ?
            OR EXISTS(SELECT 1 FROM transaction_tags tt WHERE tt.transaction_id=t.id AND tt.tag LIKE ?))""")
        args.extend(["%" + q + "%"] * 5)
    rows = c.execute("""SELECT t.*,a.name account_name,cat.name category_name,
        s.id split_id,CASE WHEN s.id IS NULL THEN t.amount ELSE s.amount END export_amount,
        s.note split_note,tags.tags,
        COALESCE(r.series_id,r.id) series_id,tr.recurring_transfer_id
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        LEFT JOIN splits s ON s.transaction_id=t.id
        LEFT JOIN categories cat ON cat.id=CASE WHEN s.id IS NULL THEN t.category_id ELSE s.category_id END
        LEFT JOIN recurring r ON r.id=t.recurring_id LEFT JOIN transfers tr ON tr.id=t.transfer_id
        LEFT JOIN (SELECT transaction_id,GROUP_CONCAT(tag,' | ') tags
                   FROM (SELECT transaction_id,tag FROM transaction_tags ORDER BY tag)
                   GROUP BY transaction_id) tags ON tags.transaction_id=t.id
        WHERE """ + " AND ".join(where) + " ORDER BY t.booking_date,t.id,s.id LIMIT ?",
        [*args, MAX_EXPORT_ROWS + 1]).fetchall()
    if len(rows) > MAX_EXPORT_ROWS:
        raise HTTPException(413, "Export zu groß; bitte Zeitraum oder Konto eingrenzen")
    out = []
    for r in rows:
        typ = "Transfer" if r["transfer_id"] else ("Einnahme" if r["amount"] >= 0 else "Ausgabe")
        out.append([r["id"], r["split_id"] or "", r["booking_date"], r["value_date"] or "",
                    safe_text(r["name"]), safe_text(r["account_name"]), safe_text(r["payee"]),
                    safe_text(r["category_name"]), money(r["export_amount"]), typ,
                    "Gebucht" if r["status"] == "executed" else "Geplant",
                    "Ja" if r["series_id"] or r["recurring_transfer_id"] else "Nein",
                    safe_text(r["tags"]), safe_text(r["note"]), safe_text(r["split_note"])])
    return download("haushaltpro-buchungen.csv",
                    ["Buchungs-ID", "Teil-ID", "Datum", "Wertstellung", "Name", "Konto", "Empfänger",
                     "Kategorie", "Betrag (EUR)", "Buchungsart", "Status", "Wiederkehrend", "Tags", "Notiz", "Teilnotiz"], out)


@router.get("/fixed-costs.csv")
def fixed_costs_csv(request: Request, year: int = Query(ge=2000, le=2100),
                    account_id: int | None = None, category_id: int | None = None):
    m = _core()
    m.session(request)
    c = db.db()
    start, end = date(year, 1, 1), date(year, 12, 31)
    accounts = {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM accounts")}
    groups = {}

    def add(key, name, aid, cid, category, kind, booked, amount):
        if account_id is not None and aid != account_id:
            return
        if category_id is not None and cid != category_id:
            return
        item = groups.setdefault(key, {"name": name, "account": accounts.get(aid, ""),
                                      "category": category, "kind": kind, "months": [0] * 12})
        item["months"][booked.month - 1] += abs(int(amount))

    # Same semantics as planned_fixed_costs(): standalone fixed expenses plus
    # contractual recurring occurrences, each exactly once, at its effective date.
    rows = c.execute("""SELECT t.*,cat.name category_name FROM transactions t
        LEFT JOIN categories cat ON cat.id=t.category_id
        WHERE t.status<>'cancelled' AND t.transfer_id IS NULL AND t.recurring_id IS NULL AND t.fixed_cost=1
        AND COALESCE(cat.direction,CASE WHEN t.direction='income' THEN 'income' ELSE 'expense' END)='expense'
        AND t.booking_date BETWEEN ? AND ?""", (start.isoformat(), end.isoformat())).fetchall()
    for r in rows:
        add(("booking", r["id"]), r["name"] or "Buchung", r["account_id"], r["category_id"],
            r["category_name"], "Einzelbuchung", date.fromisoformat(r["booking_date"]), r["amount"])
    series = [r for r in m.recurring_rows_for_window(c, account_id, start, end) if r["fixed_cost"]]
    categories, overrides = m._recurring_plan_context(c, series, start, end)
    for r in series:
        cat = categories.get(r["category_id"])
        if (cat and cat["direction"] in {"income", "savings"}) or (not cat and r["kind"] == "income"):
            continue
        sid = r["series_id"] or r["id"]
        for due, booked, override in m._recurring_dates(r, start, end, overrides):
            add(("series", sid, r["account_id"], r["category_id"], r["name"]),
                r["name"], r["account_id"], r["category_id"], cat["name"] if cat else "",
                "Serie", booked, override["amount"] if override else r["amount"])
    out, totals = [], [0] * 12
    for item in sorted(groups.values(), key=lambda r: (r["name"].casefold(), r["account"])):
        values = item["months"]
        totals = [a + b for a, b in zip(totals, values)]
        out.append([safe_text(item["name"]), safe_text(item["account"]), safe_text(item["category"]),
                    item["kind"], *map(money, values), money(sum(values))])
    out.append(["GESAMT", "", "", "Summe", *map(money, totals), money(sum(totals))])
    return download(f"haushaltpro-fixkosten-plan-{year}.csv",
                    ["Name", "Konto", "Kategorie", "Typ",
                     *[f"{year}-{month:02d} (EUR)" for month in range(1, 13)], "Jahr (EUR)"], out)
