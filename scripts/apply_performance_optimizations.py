from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)

# 1) Splits are looked up by transaction_id in reports and transaction pages.
db_path=Path('app/db.py')
db=db_path.read_text(encoding='utf-8')
db=replace_once(
    db,
    '        CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id);\n',
    '        CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id);\n        CREATE INDEX IF NOT EXISTS idx_splits_tx ON splits(transaction_id);\n',
    'init split index',
)
db=replace_once(
    db,
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id)")\n',
    '    c.execute("CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id)")\n    c.execute("CREATE INDEX IF NOT EXISTS idx_splits_tx ON splits(transaction_id)")\n',
    'migration split index',
)
db_path.write_text(db,encoding='utf-8')

# 2) Recurring forecast lookups used to execute 3-4 SQL queries for every due
# occurrence. Preload completion, overrides and category semantics once per
# requested window instead. Chunk IN clauses to stay below SQLite variable limits.
main_path=Path('app/main.py')
main=main_path.read_text(encoding='utf-8')
start=main.index('def recurring_events(c, account_id: int | None, from_day: date, to_day: date):')
end=main.index('\n\ndef _materialize_recurring_window',start)
new='''def recurring_events(c, account_id: int | None, from_day: date, to_day: date):
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
'''
main=main[:start]+new+main[end:]

# 3) Planning deliberately counts the contract schedule even after an occurrence
# was executed, so it cannot reuse recurring_events(). It can still preload all
# category metadata and overrides instead of querying them inside every occurrence.
plan_start=main.index('def planned_month_category_totals(c, start: date, end: date)')
plan_end=main.index('\n\n@app.get("/api/planning/variance")',plan_start)
plan_new='''def _recurring_plan_context(c, rows, start: date, end: date):
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
'''
main=main[:plan_start]+plan_new+main[plan_end:]
main_path.write_text(main,encoding='utf-8')
print('performance patch applied')
