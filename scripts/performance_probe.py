"""Repeatable local/CI performance probe for read-heavy HaushaltPro views.

This is diagnostic, not a hard timing gate: runner speed varies. It prints raw
latency and SQL statement counts for representative large-household data.
"""
import sqlite3,sys,types,tempfile,time,statistics
from pathlib import Path
from datetime import date as real_date,timedelta

shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim
root=Path(__file__).resolve().parents[1]
Path('/app').mkdir(exist_ok=True); static=Path('/app/static')
if static.is_symlink() and static.resolve()!=(root/'static').resolve(): static.unlink()
if not static.exists(): static.symlink_to(root/'static',target_is_directory=True)
sys.path.insert(0,str(root))
from app import db
fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
db._conn=c; db.DB_PATH=Path(tmp); db.init_schema(c); db.migrate_schema(c)
from app import main
class FixedDate(real_date):
    @classmethod
    def today(cls): return cls(2026,9,15)
main.date=FixedDate; main.db._conn=c; main.session=lambda request,write=False:('perf',1,'csrf',0)
main.require_book_owner=lambda request:None; main.require_system_admin=lambda request:None
from fastapi.testclient import TestClient
client=TestClient(main.app)

# 8 accounts, 24 categories, 60k transactions over 24 months, 20% split rows.
ts='2026-01-01T00:00:00+00:00'
accounts=[]
for i in range(8):
    cur=c.execute("INSERT INTO accounts(name,type,iban,opening_balance,currency,active,start_date,created_at) VALUES(?,?,?,?,?,1,?,?)",
                  (f'Account {i}','checking',None,250000,'EUR','2025-01-01',ts)); accounts.append(cur.lastrowid)
categories=[]
for i in range(24):
    direction='income' if i<4 else ('savings' if i<6 else 'expense')
    cur=c.execute("INSERT INTO categories(parent_id,name,direction,active) VALUES(NULL,?,?,1)",(f'Category {i}',direction)); categories.append(cur.lastrowid)
rows=[]
start=real_date(2025,1,1)
for i in range(60000):
    d=start+timedelta(days=i%730)
    cat=categories[i%len(categories)]; direction='income' if i%24<4 else 'expense'
    amount=(150000 if direction=='income' else -((i%19000)+100))
    rows.append((accounts[i%8],amount,direction,d.isoformat(),f'Tx {i}',f'Payee {i%200}',cat,'executed',f'perf-{i}',0,ts,ts))
c.executemany("""INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,category_id,status,external_id,fixed_cost,created_at,updated_at)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",rows)
c.commit()
# Add split rows to every fifth transaction. Values sum to the transaction amount.
split_rows=[]
for r in c.execute("SELECT id,amount,category_id FROM transactions WHERE id%5=0").fetchall():
    a=int(r['amount']); a1=a//2; a2=a-a1
    split_rows.append((r['id'],r['category_id'],a1,'perf split A'))
    split_rows.append((r['id'],categories[(int(r['category_id'])+1)%len(categories)],a2,'perf split B'))
c.executemany("INSERT INTO splits(transaction_id,category_id,amount,note) VALUES(?,?,?,?)",split_rows)
# Representative future recurring rows.
for i in range(80):
    aid=accounts[i%8]; cid=categories[6+(i%18)]; amount=-(5000+(i%20)*100)
    c.execute("""INSERT INTO recurring(account_id,category_id,name,payee,amount,next_date,frequency,interval_count,kind,max_amount,active,series_id,anchor_date,valid_from,valid_until,confidence,fixed_cost,created_at)
                 VALUES(?,?,?,?,?,'2026-09-20','monthly',1,'direct_debit',NULL,1,NULL,'2026-09-20','2026-09-20','2027-09-20','fixed',1,?)""",
              (aid,cid,f'Recurring {i}',f'Provider {i}',amount,ts))
    rid=c.execute('SELECT last_insert_rowid()').fetchone()[0]; c.execute('UPDATE recurring SET series_id=? WHERE id=?',(rid,rid))
c.commit()


def probe(label,url,runs=3):
    timings=[]; counts=[]
    for _ in range(runs):
        n=[0]
        def trace(sql):
            if not sql.startswith('PRAGMA'): n[0]+=1
        c.set_trace_callback(trace)
        t0=time.perf_counter(); response=client.get(url); elapsed=(time.perf_counter()-t0)*1000
        c.set_trace_callback(None)
        assert response.status_code<300,(label,response.status_code,response.text[:500])
        timings.append(elapsed); counts.append(n[0])
    print(f'PERF {label}: median_ms={statistics.median(timings):.2f} min_ms={min(timings):.2f} sql={int(statistics.median(counts))}')

print(f'PERF DATA transactions=60000 splits={len(split_rows)} accounts={len(accounts)} recurring=80')
probe('reports-current-month','/api/reports/categories?period=month&anchor=2026-09-01')
probe('reports-year','/api/reports/categories?period=year&anchor=2026-01-01')
probe('transactions-page','/api/transactions/paged?period=month&month=2026-09&page=1&page_size=25')
probe('dashboard-month','/api/dashboard?month=2026-09')
probe('planning-month','/api/planning/overview?month=2026-09')
probe('planning-year','/api/planning/year?year=2026',runs=2)

c.close(); Path(tmp).unlink(missing_ok=True)
