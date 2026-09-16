"""Receivables/payables and cent-exact allocations to real account bookings."""
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from . import db

router = APIRouter(prefix="/api/open-items")
Money = Decimal


def _core():
    from . import main
    return main


def init_schema(c):
    # execute(), not executescript(): an upgrade stays within its transaction.
    c.execute("""CREATE TABLE IF NOT EXISTS open_items(
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('payable','receivable')),
        name TEXT NOT NULL, payee TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
        due_date TEXT, note TEXT, cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0,1)),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS open_item_payments(
        id INTEGER PRIMARY KEY, open_item_id INTEGER NOT NULL,
        transaction_id INTEGER NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
        created_at TEXT NOT NULL,
        FOREIGN KEY(open_item_id) REFERENCES open_items(id) ON DELETE CASCADE,
        FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
        UNIQUE(open_item_id,transaction_id))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_open_item_due ON open_items(cancelled,due_date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payment_transaction ON open_item_payments(transaction_id)")
    # Protect every mutation path, including recurring overrides, cancellation,
    # bulk deletion and account deletion. The UI must never show a false paid total.
    c.execute("""CREATE TRIGGER IF NOT EXISTS guard_allocated_transaction
        BEFORE UPDATE OF amount,status,transfer_id,booking_date ON transactions
        WHEN NEW.status='executed' AND EXISTS(
            SELECT 1 FROM open_item_payments WHERE transaction_id=OLD.id)
        BEGIN
          SELECT CASE WHEN NEW.transfer_id IS NOT NULL
            OR NEW.booking_date>date('now','localtime')
            OR ABS(NEW.amount)<(SELECT SUM(amount) FROM open_item_payments WHERE transaction_id=OLD.id)
            OR EXISTS(SELECT 1 FROM open_item_payments p JOIN open_items o ON o.id=p.open_item_id
                WHERE p.transaction_id=OLD.id AND
                ((o.kind='payable' AND NEW.amount>=0) OR (o.kind='receivable' AND NEW.amount<=0)))
          THEN RAISE(ABORT,'HP_PAYMENT:Zahlungszuordnung zuerst lösen: Betrag, Richtung oder Datum passt nicht mehr zum offenen Posten.') END;
        END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS unlink_cancelled_payment
        AFTER UPDATE OF status ON transactions WHEN NEW.status<>'executed'
        BEGIN DELETE FROM open_item_payments WHERE transaction_id=NEW.id; END""")
    c.execute("""CREATE TRIGGER IF NOT EXISTS guard_open_item_update
        BEFORE UPDATE OF amount,kind ON open_items
        WHEN NEW.amount<(SELECT COALESCE(SUM(amount),0) FROM open_item_payments WHERE open_item_id=OLD.id)
          OR (NEW.kind<>OLD.kind AND EXISTS(SELECT 1 FROM open_item_payments WHERE open_item_id=OLD.id))
        BEGIN SELECT RAISE(ABORT,'HP_PAYMENT:Gesamtbetrag oder Art widerspricht bereits zugeordneten Zahlungen.'); END""")


class OpenItemIn(BaseModel):
    kind: Literal["payable", "receivable"]
    name: str = Field(min_length=1, max_length=160)
    payee: str = Field(min_length=1, max_length=200)
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=1000)
    cancelled: bool = False

    @field_validator("name", "payee")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Name und Empfänger dürfen nicht leer sein")
        return value.strip()


class PaymentIn(BaseModel):
    amount: Money = Field(gt=0, max_digits=14, decimal_places=2)
    transaction_id: int | None = Field(default=None, gt=0)
    account_id: int | None = Field(default=None, gt=0)
    booking_date: date | None = None
    category_id: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=1000)


BALANCES = """SELECT o.*,COALESCE(p.paid,0) paid,
    o.amount-COALESCE(p.paid,0) remaining,
    CASE WHEN o.cancelled=1 THEN 'cancelled'
         WHEN COALESCE(p.paid,0)>=o.amount THEN 'paid'
         WHEN COALESCE(p.paid,0)>0 THEN 'partial' ELSE 'open' END status
    FROM open_items o LEFT JOIN
    (SELECT open_item_id,SUM(amount) paid FROM open_item_payments GROUP BY open_item_id) p
    ON p.open_item_id=o.id"""


def _item(c, item_id):
    row = c.execute("SELECT * FROM (" + BALANCES + ") WHERE id=?", (item_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Offener Posten nicht gefunden")
    return row


def _serialize(row):
    m = _core()
    item = dict(row)
    item["overdue"] = bool(not row["cancelled"] and row["remaining"] > 0
                           and row["due_date"] and row["due_date"] < date.today().isoformat())
    for key in ("amount", "paid", "remaining"):
        item[key] = m.euros(row[key])
    item["cancelled"] = bool(row["cancelled"])
    return item


@router.get("")
def list_items(request: Request, kind: Literal["payable", "receivable"] | None = None,
               state: Literal["outstanding", "all", "open", "partial", "paid", "cancelled", "overdue"] = "outstanding",
               q: str = Query(default="", max_length=100), page: int = Query(default=1, ge=1)):
    _core().session(request)
    c = db.db()
    where, args = ["1=1"], []
    if kind:
        where.append("kind=?")
        args.append(kind)
    if q:
        where.append("(name LIKE ? OR payee LIKE ? OR COALESCE(note,'') LIKE ?)")
        args.extend(["%" + q + "%"] * 3)
    base_where = " AND ".join(where)
    totals = c.execute("""SELECT
        COALESCE(SUM(CASE WHEN kind='payable' AND cancelled=0 THEN remaining ELSE 0 END),0) payable,
        COALESCE(SUM(CASE WHEN kind='receivable' AND cancelled=0 THEN remaining ELSE 0 END),0) receivable,
        SUM(CASE WHEN cancelled=0 AND remaining>0 AND due_date<? THEN 1 ELSE 0 END) overdue
        FROM (""" + BALANCES + ") WHERE " + base_where, [date.today().isoformat(), *args]).fetchone()
    if state in {"outstanding", "overdue"}:
        where.append("cancelled=0 AND remaining>0")
        if state == "overdue":
            where.append("due_date<?")
            args.append(date.today().isoformat())
    elif state != "all":
        where.append("status=?")
        args.append(state)
    sql = " FROM (" + BALANCES + ") WHERE " + " AND ".join(where)
    count = c.execute("SELECT COUNT(*)" + sql, args).fetchone()[0]
    pages = max(1, (count + 24) // 25)
    page = min(page, pages)
    rows = c.execute("SELECT *" + sql + """ ORDER BY
        CASE WHEN cancelled=0 AND remaining>0 THEN 0 ELSE 1 END,
        COALESCE(due_date,'9999-12-31'),id DESC LIMIT 25 OFFSET ?""", [*args, (page - 1) * 25]).fetchall()
    return {"items": [_serialize(r) for r in rows], "total": count, "page": page, "pages": pages,
            "totals": {"payable": _core().euros(totals["payable"]),
                       "receivable": _core().euros(totals["receivable"]), "overdue": totals["overdue"] or 0}}


@router.get("/{item_id}")
def get_item(item_id: int, request: Request):
    _core().session(request)
    c = db.db()
    result = _serialize(_item(c, item_id))
    rows = c.execute("""SELECT p.id,p.transaction_id,p.amount,t.booking_date,t.name,
        t.account_id,a.name account_name FROM open_item_payments p
        JOIN transactions t ON t.id=p.transaction_id JOIN accounts a ON a.id=t.account_id
        WHERE p.open_item_id=? ORDER BY t.booking_date DESC,p.id DESC""", (item_id,)).fetchall()
    result["payments"] = [{**dict(r), "amount": _core().euros(r["amount"])} for r in rows]
    return result


@router.post("")
def create_item(x: OpenItemIn, request: Request):
    m = _core()
    sess = m.session(request, True)
    key, endpoint = m.client_request_id(request), "POST /api/open-items"
    with db.transaction() as c:
        replay = m.client_mutation_replay(c, key, endpoint)
        if replay is not None:
            return replay
        ts = m.iso(m.utcnow())
        cur = c.execute("""INSERT INTO open_items(kind,name,payee,amount,due_date,note,cancelled,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?)""",
            (x.kind, x.name, x.payee, m.cents(x.amount), x.due_date.isoformat() if x.due_date else None,
             m.clean_text(x.note, 1000), int(x.cancelled), ts, ts))
        result = {"id": cur.lastrowid}
        m.audit_append(c, sess[1], "open_item.create", "open_item", cur.lastrowid, dict(_item(c, cur.lastrowid)))
        m.client_mutation_store(c, key, endpoint, result)
        return result


@router.put("/{item_id}")
def update_item(item_id: int, x: OpenItemIn, request: Request):
    m = _core()
    sess = m.session(request, True)
    with db.transaction() as c:
        before = dict(_item(c, item_id))
        c.execute("""UPDATE open_items SET kind=?,name=?,payee=?,amount=?,due_date=?,note=?,cancelled=?,updated_at=?
                     WHERE id=?""",
                  (x.kind, x.name, x.payee, m.cents(x.amount), x.due_date.isoformat() if x.due_date else None,
                   m.clean_text(x.note, 1000), int(x.cancelled), m.iso(m.utcnow()), item_id))
        m.audit_append(c, sess[1], "open_item.update", "open_item", item_id,
                       {"before": before, "current": dict(_item(c, item_id))})
    return {"ok": True}


@router.get("/{item_id}/candidates")
def payment_candidates(item_id: int, request: Request, q: str = Query(default="", max_length=100),
                       page: int = Query(default=1, ge=1)):
    _core().session(request)
    c = db.db()
    item = _item(c, item_id)
    sign = "<" if item["kind"] == "payable" else ">"
    rows = c.execute(f"""SELECT t.id,t.booking_date,t.name,t.payee,a.name account_name,t.amount,
        ABS(t.amount)-COALESCE(p.allocated,0) available
        FROM transactions t JOIN accounts a ON a.id=t.account_id
        LEFT JOIN (SELECT transaction_id,SUM(amount) allocated FROM open_item_payments GROUP BY transaction_id) p ON p.transaction_id=t.id
        WHERE t.status='executed' AND t.transfer_id IS NULL AND t.amount{sign}0 AND a.currency='EUR'
        AND t.booking_date<=? AND ABS(t.amount)>COALESCE(p.allocated,0)
        AND NOT EXISTS(SELECT 1 FROM open_item_payments own WHERE own.transaction_id=t.id AND own.open_item_id=?)
        AND (COALESCE(t.name,'') LIKE ? OR COALESCE(t.payee,'') LIKE ? OR a.name LIKE ? OR COALESCE(t.note,'') LIKE ?)
        ORDER BY t.booking_date DESC,t.id DESC LIMIT 26 OFFSET ?""",
        [date.today().isoformat(), item_id, *["%" + q + "%"] * 4, (page - 1) * 25]).fetchall()
    return {"items": [{**dict(r), "amount": _core().euros(r["amount"]),
                       "available": _core().euros(r["available"])} for r in rows[:25]],
            "page": page, "has_more": len(rows) > 25}


@router.post("/{item_id}/payments")
def pay_item(item_id: int, x: PaymentIn, request: Request):
    m = _core()
    sess = m.session(request, True)
    key, endpoint = m.client_request_id(request), f"POST /api/open-items/{item_id}/payments"
    with db.transaction() as c:
        replay = m.client_mutation_replay(c, key, endpoint)
        if replay is not None:
            return replay
        item = _item(c, item_id)
        amount = m.cents(x.amount)
        if item["cancelled"] or amount > item["remaining"]:
            raise HTTPException(409, "Betrag übersteigt den offenen Rest oder der Posten ist storniert")
        direction = "expense" if item["kind"] == "payable" else "income"
        ts = m.iso(m.utcnow())
        transaction_id = x.transaction_id
        if transaction_id is not None:
            tx = c.execute("""SELECT t.*,a.currency FROM transactions t
                              JOIN accounts a ON a.id=t.account_id WHERE t.id=?""", (transaction_id,)).fetchone()
            if not tx:
                raise HTTPException(404, "Buchung nicht gefunden")
            if tx["currency"] != "EUR":
                raise HTTPException(400, "Offene Zahlungen werden derzeit in EUR geführt")
            if (tx["status"] != "executed" or tx["transfer_id"] or
                    tx["booking_date"] > date.today().isoformat() or
                    (tx["amount"] >= 0 if direction == "expense" else tx["amount"] <= 0)):
                raise HTTPException(409, "Nur passende, bereits gebuchte Ein- oder Ausgaben können zugeordnet werden")
            if c.execute("SELECT 1 FROM open_item_payments WHERE open_item_id=? AND transaction_id=?",
                         (item_id, transaction_id)).fetchone():
                raise HTTPException(409, "Diese Buchung ist dem Posten bereits zugeordnet")
            allocated = c.execute("SELECT COALESCE(SUM(amount),0) FROM open_item_payments WHERE transaction_id=?",
                                  (transaction_id,)).fetchone()[0]
            if amount > abs(tx["amount"]) - allocated:
                raise HTTPException(409, "Der freie Betrag dieser Buchung reicht nicht aus")
        else:
            if not x.account_id or not x.booking_date or not x.category_id:
                raise HTTPException(400, "Für eine neue Zahlung Konto, Datum und Kategorie angeben")
            account = c.execute("SELECT * FROM accounts WHERE id=? AND active=1", (x.account_id,)).fetchone()
            if not account:
                raise HTTPException(400, "Aktives Konto nicht gefunden")
            if account["currency"] != "EUR":
                raise HTTPException(400, "Offene Zahlungen werden derzeit in EUR geführt")
            if x.booking_date > date.today() or x.booking_date.isoformat() < account["start_date"]:
                raise HTTPException(400, "Zahlungsdatum muss zwischen Kontostart und heute liegen")
            cat = c.execute("SELECT direction FROM categories WHERE id=? AND active=1", (x.category_id,)).fetchone()
            if not cat or ("income" if cat["direction"] == "income" else "expense") != direction:
                raise HTTPException(400, "Kategorie passt nicht zur Zahlungsrichtung")
            signed = -amount if direction == "expense" else amount
            cur = c.execute("""INSERT INTO transactions(account_id,amount,direction,booking_date,value_date,
                name,payee,note,category_id,status,external_id,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,'executed',?,?,?)""",
                (x.account_id, signed, direction, x.booking_date.isoformat(), x.booking_date.isoformat(),
                 item["name"], item["payee"], m.clean_text(x.note, 1000), x.category_id,
                 "payment-" + m.secrets.token_hex(16), ts, ts))
            transaction_id = cur.lastrowid
            m.audit_append(c, sess[1], "transaction.create", "transaction", transaction_id,
                           {"name": item["name"], "amount": signed, "open_item_id": item_id})
        cur = c.execute("""INSERT INTO open_item_payments(open_item_id,transaction_id,amount,created_at)
                           VALUES(?,?,?,?)""", (item_id, transaction_id, amount, ts))
        result = {"id": cur.lastrowid, "transaction_id": transaction_id,
                  "created_transaction": x.transaction_id is None}
        m.audit_append(c, sess[1], "open_item.payment", "open_item", item_id, {**result, "amount": amount})
        m.client_mutation_store(c, key, endpoint, result)
        return result


@router.delete("/{item_id}/payments/{payment_id}")
def unlink_payment(item_id: int, payment_id: int, request: Request):
    m = _core()
    sess = m.session(request, True)
    with db.transaction() as c:
        row = c.execute("SELECT * FROM open_item_payments WHERE id=? AND open_item_id=?",
                        (payment_id, item_id)).fetchone()
        if not row:
            raise HTTPException(404, "Zahlungszuordnung nicht gefunden")
        c.execute("DELETE FROM open_item_payments WHERE id=?", (payment_id,))
        m.audit_append(c, sess[1], "open_item.unlink", "open_item", item_id, dict(row))
    return {"ok": True}
