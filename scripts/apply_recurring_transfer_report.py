from pathlib import Path
import json
import re


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


# --- Database schema / migration ---
p = Path("app/db.py")
db = p.read_text(encoding="utf-8")

recurring_transfer_table = """        CREATE TABLE IF NOT EXISTS recurring_transfers(
            id INTEGER PRIMARY KEY,
            from_account_id INTEGER NOT NULL,
            to_account_id INTEGER NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            next_date TEXT NOT NULL,
            frequency TEXT NOT NULL CHECK(frequency IN ('daily','weekly','monthly','yearly')),
            interval_count INTEGER NOT NULL DEFAULT 1 CHECK(interval_count >= 1),
            name TEXT NOT NULL DEFAULT 'Transfer',
            note TEXT,
            valid_until TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
            FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
            CHECK(from_account_id <> to_account_id)
        );

"""
db = replace_once(
    db,
    "        CREATE TABLE IF NOT EXISTS transfers(\n",
    recurring_transfer_table + "        CREATE TABLE IF NOT EXISTS transfers(\n",
    "initial recurring_transfers table",
)
db = replace_once(
    db,
    "            note TEXT,\n            active INTEGER NOT NULL DEFAULT 1,\n            created_at TEXT NOT NULL,\n            updated_at TEXT NOT NULL,\n            FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,\n            FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,\n            CHECK(from_account_id <> to_account_id)\n        );",
    "            note TEXT,\n            recurring_transfer_id INTEGER,\n            active INTEGER NOT NULL DEFAULT 1,\n            created_at TEXT NOT NULL,\n            updated_at TEXT NOT NULL,\n            FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,\n            FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,\n            FOREIGN KEY(recurring_transfer_id) REFERENCES recurring_transfers(id) ON DELETE SET NULL,\n            CHECK(from_account_id <> to_account_id)\n        );",
    "initial transfers recurrence link",
)
db = replace_once(
    db,
    "        CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date, active);\n",
    "        CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date, active);\n"
    "        CREATE INDEX IF NOT EXISTS idx_recurring_transfer_active_date ON recurring_transfers(active, next_date);\n"
    "        CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_recurring_due ON transfers(recurring_transfer_id, booking_date) WHERE recurring_transfer_id IS NOT NULL;\n",
    "initial recurring transfer indexes",
)

migration_table = """    c.execute(\"\"\"CREATE TABLE IF NOT EXISTS recurring_transfers(
        id INTEGER PRIMARY KEY,from_account_id INTEGER NOT NULL,to_account_id INTEGER NOT NULL,
        amount INTEGER NOT NULL CHECK(amount > 0),next_date TEXT NOT NULL,
        frequency TEXT NOT NULL CHECK(frequency IN ('daily','weekly','monthly','yearly')),
        interval_count INTEGER NOT NULL DEFAULT 1 CHECK(interval_count >= 1),
        name TEXT NOT NULL DEFAULT 'Transfer',note TEXT,valid_until TEXT,active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        CHECK(from_account_id <> to_account_id))\"\"\")
"""
db = replace_once(
    db,
    '    c.execute("""CREATE TABLE IF NOT EXISTS transfers(\n',
    migration_table + '    c.execute("""CREATE TABLE IF NOT EXISTS transfers(\n',
    "migration recurring_transfers table",
)
db = replace_once(
    db,
    '    tcols4 = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}\n',
    '    transfer_cols = {r[1] for r in c.execute("PRAGMA table_info(transfers)").fetchall()}\n'
    '    if "recurring_transfer_id" not in transfer_cols:\n'
    '        c.execute("ALTER TABLE transfers ADD COLUMN recurring_transfer_id INTEGER")\n'
    '    tcols4 = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}\n',
    "migration transfers recurrence column",
)
db = replace_once(
    db,
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date,active)")\n',
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date,active)")\n'
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_recurring_transfer_active_date ON recurring_transfers(active,next_date)")\n'
    '    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_recurring_due ON transfers(recurring_transfer_id,booking_date) WHERE recurring_transfer_id IS NOT NULL")\n',
    "migration recurring transfer indexes",
)
db = db.replace("'schema_version','24'", "'schema_version','25'")
p.write_text(db, encoding="utf-8")


# --- Backend models, recurring-transfer engine, current-month report ---
p = Path("app/main.py")
main = p.read_text(encoding="utf-8")

transfer_model = '''class TransferIn(BaseModel):
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
'''
main, n = re.subn(
    r"class TransferIn\(BaseModel\):.*?\n\nclass RecurringIn",
    transfer_model + "\n\nclass RecurringIn",
    main,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("failed to patch TransferIn")

transfer_block = r'''def recurring_transfer_snapshot(c, recurring_transfer_id: int) -> dict:
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
    sess=session(request,True);amount=abs(cents(x.amount));ts=iso(utcnow())
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
    return {"id":tid,"recurring_transfer_id":recurring_transfer_id,"generated_transfers":generated}


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

'''
pattern = r'@app\.get\("/api/transfers/\{transfer_id\}"\).*?\n    return \{"ok":True\}\n\n(?=@app\.)'
main, n = re.subn(pattern, transfer_block, main, count=1, flags=re.S)
if n != 1:
    raise SystemExit("failed to replace transfer API block")

old_report = '''    today=date.today()
    actual_end=min(end,today)
    # Reports are documentary: future-dated manual/planned entries are not Ist yet.
    query_end=actual_end if actual_end>=start else start-timedelta(days=1)
    rows = c.execute("""
        SELECT category_id, category_name, direction, SUM(amount) amount FROM (
          SELECT s.category_id, COALESCE(c.name,'Nicht kategorisiert') category_name,
                 COALESCE(c.direction, CASE WHEN s.amount>=0 THEN 'income' ELSE 'expense' END) direction, s.amount amount
          FROM splits s JOIN transactions t ON t.id=s.transaction_id
          LEFT JOIN categories c ON c.id=s.category_id
          WHERE t.status='executed' AND t.transfer_id IS NULL AND t.booking_date BETWEEN ? AND ?
          UNION ALL
          SELECT t.category_id, COALESCE(c.name,'Nicht kategorisiert') category_name,
                 COALESCE(c.direction, CASE WHEN t.amount>=0 THEN 'income' ELSE 'expense' END) direction, t.amount amount
          FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
          WHERE t.status='executed' AND t.transfer_id IS NULL AND t.booking_date BETWEEN ? AND ?
            AND NOT EXISTS (SELECT 1 FROM splits s WHERE s.transaction_id=t.id)
        ) GROUP BY category_id,category_name,direction ORDER BY direction,ABS(SUM(amount)) DESC
    """, (start.isoformat(), query_end.isoformat(), start.isoformat(), query_end.isoformat())).fetchall()
'''
new_report = '''    today=date.today()
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
'''
main = replace_once(main, old_report, new_report, "category report current-month forecast")
main = replace_once(
    main,
    '    result={"period":period,"start":start.isoformat(),"end":end.isoformat(),"actual_through":actual_end.isoformat() if actual_end>=start else None,\n',
    '    result={"period":period,"start":start.isoformat(),"end":end.isoformat(),"actual_through":actual_end.isoformat() if actual_end>=start else None,\n'
    '            "mode":"forecast" if forecast_mode else "actual","includes_planned":bool(forecast_mode),\n',
    "category report mode",
)
p.write_text(main, encoding="utf-8")


# --- Web UI ---
p = Path("static/app.js")
js = p.read_text(encoding="utf-8")
js = replace_once(
    js,
    '''async function materializeRecurringDue({month=null,year=null}={}){
  const params=new URLSearchParams();
  if(month)params.set('month',month);else if(year)params.set('year',String(year));
  const suffix=params.toString()?'?'+params.toString():'';
  return api('/api/recurring/materialize-due'+suffix,{method:'POST'});
}''',
    '''async function materializeRecurringDue({month=null,year=null}={}){
  const params=new URLSearchParams();
  if(month)params.set('month',month);else if(year)params.set('year',String(year));
  const suffix=params.toString()?'?'+params.toString():'';
  const [bookings,transfers]=await Promise.all([
    api('/api/recurring/materialize-due'+suffix,{method:'POST'}),
    api('/api/recurring-transfers/materialize-due'+suffix,{method:'POST'})
  ]);
  return {bookings,transfers};
}''',
    "materialize recurring transfers in UI",
)

new_transfer_dialog = r'''async function transferDialog(transferId=null){
  if(accountsCache.length<2)return toast('Für einen Transfer werden mindestens zwei aktive Konten benötigt.');
  let tr=null;if(transferId)tr=await api('/api/transfers/'+transferId);
  const today=new Date().toISOString().slice(0,10),from=tr?.from_account_id||accountsCache[0]?.id,to=tr?.to_account_id||accountsCache.find(a=>a.id!==from)?.id;
  const repeatFields=!tr?`<label class="check"><input id="transferRecurring" name="recurring" type="checkbox"> ${esc(hpText('Wiederholen'))}</label><div id="transferRecurringFields" hidden>${recurrenceRuleFields('transferRecurrence','monthly',1,'recurring_frequency','recurring_interval_count')}<label>${esc(hpText('Enddatum (optional)'))}<input name="recurring_until" type="date"><small>${esc(hpText('Leer lassen für unbegrenzt.'))}</small></label></div>`:'';
  const seriesNote=tr?.recurring_transfer_id?`<p class="muted">${esc(hpText('Dieser Termin gehört zu einer wiederkehrenden Transfer-Serie. Hier änderst du nur diesen einzelnen Transfer; die Serie verwaltest du unter „Wiederkehrende Buchungen“.'))}</p>`:'';
  openModal(`<h2>${tr?'Transfer bearbeiten':'Transfer anlegen'}</h2><p class="muted">Interne Umbuchung zwischen deinen eigenen Konten. Sie verändert die Kontostände, zählt aber nicht als Einnahme oder Ausgabe des Haushalts.</p>${seriesNote}<label>Von Konto<select name="from_account_id">${accountOptions(from)}</select></label><label>Auf Konto<select name="to_account_id">${accountOptions(to)}</select></label><label>Betrag EUR<input name="amount" type="number" min="0.01" step="0.01" required value="${tr?Number(tr.amount).toFixed(2):''}"></label><label>Datum<input name="booking_date" type="date" required value="${tr?.booking_date||today}"></label><label>Name<input name="name" maxlength="160" required value="${esc(tr?.name||'Interner Transfer')}"></label><label>Notiz<input name="note" value="${esc(tr?.note||'')}"></label>${repeatFields}`,async f=>{
    const recurring=!tr&&f.get('recurring')==='on';
    const body={from_account_id:Number(f.get('from_account_id')),to_account_id:Number(f.get('to_account_id')),amount:String(f.get('amount')),booking_date:f.get('booking_date'),name:f.get('name')||'Interner Transfer',note:f.get('note')||null,recurring,recurring_frequency:recurring?f.get('recurring_frequency'):null,recurring_interval_count:recurring?Number(f.get('recurring_interval_count')||1):1,recurring_until:recurring?(f.get('recurring_until')||null):null};
    if(body.from_account_id===body.to_account_id)throw new Error('Quell- und Zielkonto müssen verschieden sein.');
    await api(tr?'/api/transfers/'+tr.id:'/api/transfers',{method:tr?'PUT':'POST',body:JSON.stringify(body)});await loadTransactions();await loadRecurring();await loadDashboard();
  });
  if(!tr){
    bindRecurrencePreset('transferRecurrence','recurring_frequency','recurring_interval_count');
    const cb=$('transferRecurring'),fields=$('transferRecurringFields');if(cb)cb.onchange=()=>{fields.hidden=!cb.checked};
  }
}
'''
js, n = re.subn(
    r"async function transferDialog\(transferId=null\)\{.*?\n\}\n(?=\$\('quickTx'\))",
    new_transfer_dialog,
    js,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("failed to patch transferDialog")

recurring_transfer_dialog = r'''async function recurringTransferDialog(seriesId){
  const r=await api('/api/recurring-transfers/'+seriesId);
  const today=new Date().toISOString().slice(0,10),intervalCount=Math.max(1,Number(r.interval_count||1));
  openModal(`<h2>${esc(hpText('Wiederkehrenden Transfer bearbeiten'))}</h2><p class="muted">${esc(hpText('Die Transfer-Serie verschiebt Geld zwischen deinen eigenen Konten und bleibt in der Einnahmen-/Ausgaben-Auswertung neutral. Änderungen bauen nur noch nicht ausgeführte zukünftige Termine neu auf.'))}</p><label>${esc(hpText('Von Konto'))}<select name="from_account_id">${accountOptions(r.from_account_id)}</select></label><label>${esc(hpText('Auf Konto'))}<select name="to_account_id">${accountOptions(r.to_account_id)}</select></label><label>${esc(hpText('Betrag EUR'))}<input name="amount" type="number" min="0.01" step="0.01" required value="${Number(r.amount).toFixed(2)}"></label><label>${esc(hpText('Nächster offener Termin'))}<input name="booking_date" type="date" required value="${esc(r.next_date||today)}"></label><label>${esc(hpText('Name'))}<input name="name" maxlength="160" required value="${esc(r.name||'Interner Transfer')}"></label><label>${esc(hpText('Notiz'))}<input name="note" value="${esc(r.note||'')}"></label>${recurrenceRuleFields('transferSeriesRecurrence',r.frequency||'monthly',intervalCount,'recurring_frequency','recurring_interval_count')}<label>${esc(hpText('Enddatum (optional)'))}<input name="recurring_until" type="date" value="${esc(r.valid_until||'')}"><small>${esc(hpText('Leer lassen für unbegrenzt.'))}</small></label>`,async f=>{
    const body={from_account_id:Number(f.get('from_account_id')),to_account_id:Number(f.get('to_account_id')),amount:String(f.get('amount')),booking_date:f.get('booking_date'),name:f.get('name')||'Interner Transfer',note:f.get('note')||null,recurring:true,recurring_frequency:f.get('recurring_frequency'),recurring_interval_count:Number(f.get('recurring_interval_count')||1),recurring_until:f.get('recurring_until')||null};
    if(body.from_account_id===body.to_account_id)throw new Error('Quell- und Zielkonto müssen verschieden sein.');
    await api('/api/recurring-transfers/'+seriesId,{method:'PUT',body:JSON.stringify(body)});await loadRecurring();await loadTransactions();await loadDashboard();
  });
  bindRecurrencePreset('transferSeriesRecurrence','recurring_frequency','recurring_interval_count');
}
'''
js = replace_once(js, "async function loadRecurring(){", recurring_transfer_dialog + "\nasync function loadRecurring(){", "recurring transfer series dialog")
js = replace_once(
    js,
    "    const rows=await api('/api/recurring');\n",
    "    const [rows,transferRows]=await Promise.all([api('/api/recurring'),api('/api/recurring-transfers')]);\n",
    "load recurring transfers",
)
js = replace_once(
    js,
    "    if($('txRecurringCount'))$('txRecurringCount').textContent=String(rows.length);\n",
    "    if($('txRecurringCount'))$('txRecurringCount').textContent=String(rows.length+transferRows.length);\n",
    "recurring combined count",
)
insert_marker = "    document.querySelectorAll('[data-redit]').forEach"
transfer_render = r'''    const transferHtml=transferRows.map(r=>`<tr><td>${esc(formatDateValue(r.next_date))}</td><td class="recurring-name-cell"><b>↔ ${esc(r.name)}</b><small class="recurring-series-meta">${esc(hpText('Transfer-Serie'))} #${r.id} · ${esc(formatDateValue(r.first_date))}</small></td><td>${esc(r.from_account_name)} → ${esc(r.to_account_name)}</td><td>${esc(recurrenceLabel(r.frequency,r.interval_count))}</td><td>${r.valid_until?esc(formatDateValue(r.valid_until)):hpText('Unbegrenzt')}</td><td class="right amount">${fmt(r.amount)}</td><td class="actions"><button data-rtedit="${r.id}">${esc(hpText('Serie bearbeiten'))}</button><button class="ghost" data-rtstop="${r.id}">${esc(hpText('Stoppen'))}</button><button class="ghost danger-outline" data-rtdel="${r.id}">${esc(hpText('Serie löschen'))}</button></td></tr>`).join('');
    if(transferRows.length&&!rows.length)$('recBody').innerHTML='';
    if(transferHtml)$('recBody').insertAdjacentHTML('beforeend',transferHtml);
    document.querySelectorAll('[data-rtedit]').forEach(b=>b.onclick=()=>recurringTransferDialog(Number(b.dataset.rtedit)));
    document.querySelectorAll('[data-rtstop]').forEach(b=>b.onclick=async()=>{if(hpConfirm(hpText('Transfer-Serie stoppen? Noch nicht ausgeführte zukünftige Transfers werden entfernt.'))){await api('/api/recurring-transfers/'+b.dataset.rtstop,{method:'DELETE'});await loadRecurring();await loadTransactions();await loadDashboard()}});
    document.querySelectorAll('[data-rtdel]').forEach(b=>b.onclick=async()=>{if(hpConfirm(hpText('Transfer-Serie endgültig löschen? Bereits ausgeführte Transfers bleiben als Historie bestehen.'))){await api('/api/recurring-transfers/'+b.dataset.rtdel+'?hard=true',{method:'DELETE'});await loadRecurring();await loadTransactions();await loadDashboard()}});
'''
if insert_marker not in js:
    raise SystemExit("missing recurring handler marker")
js = js.replace(insert_marker, transfer_render + insert_marker, 1)

js = replace_once(
    js,
    "  const period=$('reportPeriod').value,anchor=period==='month'?monthValue('reportMonthName','reportYear')+'-01':$('reportYear').value+'-01-01';$('reportMonthName').hidden=period!=='month';\n  const r=await cachedApi('/api/reports/categories?period='+period+'&anchor='+encodeURIComponent(anchor),25000);",
    "  const period=$('reportPeriod').value,anchor=period==='month'?monthValue('reportMonthName','reportYear')+'-01':$('reportYear').value+'-01-01';$('reportMonthName').hidden=period!=='month';\n  if(period==='month')await materializeRecurringDue({month:anchor.slice(0,7)});\n  const r=await cachedApi('/api/reports/categories?period='+period+'&anchor='+encodeURIComponent(anchor),25000);",
    "report materialization",
)
js = replace_once(
    js,
    "  const income=Number(r.income||0),expense=Number(r.expense||0),savings=Number(r.savings||0),net=Number(r.net??(income-expense-savings));\n",
    "  const income=Number(r.income||0),expense=Number(r.expense||0),savings=Number(r.savings||0),net=Number(r.net??(income-expense-savings));\n"
    "  const reportTitle=r.mode==='forecast'?hpText('Monatsprognose inklusive bereits bekannter/geplanter Buchungen bis Monatsende.'):hpText('Ist-Auswertung der tatsächlich gebuchten Werte.');\n"
    "  ['reportIncome','reportExpense','reportSavings','reportNet'].forEach(id=>{const el=$(id)?.closest('.metric');if(el)el.title=reportTitle});\n",
    "report forecast hint",
)
p.write_text(js, encoding="utf-8")


# Cache-bust the updated frontend.
p = Path("static/index.html")
html = p.read_text(encoding="utf-8")
html, n = re.subn(r'app\.js\?v=[^"\']+', 'app.js?v=0.21.8-recurring-transfer1', html, count=1)
if n != 1:
    raise SystemExit("failed to bump app.js cache key")
p.write_text(html, encoding="utf-8")


# English legacy strings for the new UI.
p = Path("static/i18n/en.json")
data = json.loads(p.read_text(encoding="utf-8"))
legacy = data.setdefault("legacy", {})
legacy.update({
    "Wiederholen": "Repeat",
    "Dieser Termin gehört zu einer wiederkehrenden Transfer-Serie. Hier änderst du nur diesen einzelnen Transfer; die Serie verwaltest du unter „Wiederkehrende Buchungen“.": "This occurrence belongs to a recurring transfer series. Here you only edit this individual transfer; manage the series under ‘Recurring transactions’.",
    "Wiederkehrenden Transfer bearbeiten": "Edit recurring transfer",
    "Die Transfer-Serie verschiebt Geld zwischen deinen eigenen Konten und bleibt in der Einnahmen-/Ausgaben-Auswertung neutral. Änderungen bauen nur noch nicht ausgeführte zukünftige Termine neu auf.": "The transfer series moves money between your own accounts and stays neutral in income/expense reports. Changes rebuild only future occurrences that have not been executed.",
    "Nächster offener Termin": "Next open occurrence",
    "Transfer-Serie": "Transfer series",
    "Transfer-Serie stoppen? Noch nicht ausgeführte zukünftige Transfers werden entfernt.": "Stop transfer series? Future transfers that have not been executed will be removed.",
    "Transfer-Serie endgültig löschen? Bereits ausgeführte Transfers bleiben als Historie bestehen.": "Permanently delete transfer series? Already executed transfers remain in history.",
    "Monatsprognose inklusive bereits bekannter/geplanter Buchungen bis Monatsende.": "Month forecast including known/planned bookings through month end.",
    "Ist-Auswertung der tatsächlich gebuchten Werte.": "Actual report of executed bookings.",
})
p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# Changelog
p = Path("CHANGELOG.md")
ch = p.read_text(encoding="utf-8")
ch = replace_once(
    ch,
    "## Unreleased\n",
    "## Unreleased\n\n### Fixed\n\n- The current-month analysis now includes known/planned bookings through month end, including materialized recurring expenses and income. Historical months and yearly analysis remain actual-only.\n",
    "changelog current month forecast",
)
ch = replace_once(
    ch,
    "### Added\n\n",
    "### Added\n\n- Transfers can now repeat with the same calendar interval model as recurring bookings (daily, weekly, monthly, quarterly, half-yearly, yearly or custom). Recurring transfers remain neutral in income/expense analysis while moving the source and destination account forecasts.\n\n",
    "changelog recurring transfer",
)
p.write_text(ch, encoding="utf-8")


# Regression test
Path("tests/test_recurring_transfers_and_current_report.py").write_text(r'''import sqlite3,sys,types,tempfile
from pathlib import Path
from datetime import date as real_date

shim=types.ModuleType('sqlcipher3');shim.dbapi2=sqlite3;sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True);static=Path('/app/static')
if static.is_symlink() and static.resolve()!=(root/'static').resolve(): static.unlink()
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db');Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
db._conn=c;db.DB_PATH=Path(tmp);db.init_schema(c);db.migrate_schema(c)
from app import main
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,15)
main.date=FixedDate;main.db._conn=c;main.session=lambda request,write=False:('test',1,'csrf',0)
main.require_book_owner=lambda request:None;main.require_system_admin=lambda request:None
from fastapi.testclient import TestClient
client=TestClient(main.app)
def ok(r):
    assert r.status_code<300,(r.status_code,r.text)
    return r.json()

src=ok(client.post('/api/accounts',json={'name':'Giro','type':'checking','opening_balance':'1000','currency':'EUR','start_date':'2026-09-01'}))['id']
dst=ok(client.post('/api/accounts',json={'name':'Tagesgeld','type':'savings','opening_balance':'0','currency':'EUR','start_date':'2026-09-01'}))['id']
cat=ok(client.post('/api/categories',json={'name':'Versicherung','direction':'expense'}))['id']

ok(client.post('/api/transactions',json={'account_id':src,'amount':'50','booking_date':'2026-09-10','category_id':cat,'name':'Gebucht','status':'executed','tags':[],'splits':[]}))
ok(client.post('/api/recurring',json={'account_id':src,'category_id':cat,'name':'Versicherung','amount':'100','next_date':'2026-09-20','frequency':'monthly','interval_count':1,'kind':'direct_debit','active':True,'valid_until':'2026-09-20','confidence':'fixed','fixed_cost':True}))
report=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report['mode']=='forecast',report
assert report['expense']==150.0,report
assert report['includes_planned'] is True,report

tr=ok(client.post('/api/transfers',json={
    'from_account_id':src,'to_account_id':dst,'amount':'200','booking_date':'2026-09-15',
    'name':'Rücklage','note':'intern','recurring':True,'recurring_frequency':'monthly',
    'recurring_interval_count':3,'recurring_until':'2027-03-15'
}))
rid=tr['recurring_transfer_id'];assert rid
trs=c.execute("SELECT id,booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()
assert [r['booking_date'] for r in trs]==['2026-09-15','2026-12-15','2027-03-15'],[dict(r) for r in trs]
statuses=[]
for r in trs:
    statuses.append(sorted(x['status'] for x in c.execute("SELECT status FROM transactions WHERE transfer_id=?",(r['id'],)).fetchall()))
assert statuses==[['executed','executed'],['planned','planned'],['planned','planned']],statuses

series=ok(client.get('/api/recurring-transfers'))
rt=next(x for x in series if x['id']==rid)
assert rt['next_date']=='2026-12-15',rt
assert rt['frequency']=='monthly' and rt['interval_count']==3,rt

report2=ok(client.get('/api/reports/categories?period=month&anchor=2026-09-01'))
assert report2['expense']==150.0 and report2['income']==0.0,report2
sept_src=main.account_month_metrics(c,src,'2026-09')
sept_dst=main.account_month_metrics(c,dst,'2026-09')
assert sept_src['month_end_balance']==650.0,sept_src
assert sept_dst['month_end_balance']==200.0,sept_dst

ok(client.put(f'/api/recurring-transfers/{rid}',json={
    'from_account_id':src,'to_account_id':dst,'amount':'250','booking_date':'2026-10-01',
    'name':'Rücklage neu','note':None,'recurring':True,'recurring_frequency':'monthly',
    'recurring_interval_count':2,'recurring_until':'2027-02-01'
}))
dates=[r['booking_date'] for r in c.execute("SELECT booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()]
assert dates==['2026-09-15','2026-10-01','2026-12-01','2027-02-01'],dates
first=c.execute("SELECT amount FROM transfers WHERE recurring_transfer_id=? AND booking_date='2026-09-15'",(rid,)).fetchone()
assert first['amount']==20000,first

ok(client.delete(f'/api/recurring-transfers/{rid}'))
remaining=c.execute("SELECT booking_date FROM transfers WHERE recurring_transfer_id=? ORDER BY booking_date",(rid,)).fetchall()
assert [r['booking_date'] for r in remaining]==['2026-09-15'],[dict(r) for r in remaining]

past=ok(client.get('/api/reports/categories?period=month&anchor=2026-08-01'))
assert past['mode']=='actual' and past['includes_planned'] is False,past

print('recurring transfers + current-month report forecast: PASS')
c.close();Path(tmp).unlink(missing_ok=True)
''', encoding="utf-8")

print("patch prepared")
