import importlib.util, sqlite3, sys, types, tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
old_path=root/'tests/fixtures/db_v087.py'
assert old_path.exists(), old_path

# Both versions normally import sqlcipher3; plain sqlite is sufficient for a schema migration test.
shim=types.ModuleType('sqlcipher3'); shim.dbapi2=sqlite3; sys.modules['sqlcipher3']=shim

spec=importlib.util.spec_from_file_location('old_db_v087', old_path)
old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
sys.path.insert(0,str(root))
from app import db as new

fd,tmp=tempfile.mkstemp(suffix='.db'); Path(tmp).unlink(missing_ok=True)
c=sqlite3.connect(tmp,check_same_thread=False); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON')
old.init_schema(c); old.migrate_schema(c)
ver=c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]
assert ver=='21',ver

# Keep representative v0.8.7 data.
c.execute("INSERT INTO accounts(name,type,opening_balance,currency,active,start_date,created_at) VALUES('Giro','checking',123456,'EUR',1,'2026-01-01','2026-01-01T00:00:00+00:00')")
aid=c.execute("SELECT last_insert_rowid()").fetchone()[0]
c.execute("INSERT INTO transactions(account_id,amount,direction,booking_date,name,payee,status,external_id,confidence,fixed_cost,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
          (aid,-999,'expense','2026-02-03','Altbuchung','REWE','executed','legacy-test','fixed',0,'2026-02-03T12:00:00+00:00','2026-02-03T12:00:00+00:00'))
c.commit()

new.migrate_schema(c)
ver2=c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]
assert ver2=='28',ver2
cols={r[1] for r in c.execute('PRAGMA table_info(transactions)').fetchall()}
assert {'transfer_id','transfer_side'} <= cols, cols
rcols={r[1] for r in c.execute('PRAGMA table_info(recurring)').fetchall()}
assert 'interval_count' in rcols,rcols
assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transfers'").fetchone()
assert c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='payee_presets'").fetchone()
row=c.execute("SELECT name,payee,amount,transfer_id,transfer_side FROM transactions WHERE external_id='legacy-test'").fetchone()
assert row['name']=='Altbuchung' and row['payee']=='REWE' and row['amount']==-999
assert row['transfer_id'] is None and row['transfer_side'] is None
# Re-running migration must be idempotent.
new.migrate_schema(c)
assert c.execute("SELECT COUNT(*) FROM transactions WHERE external_id='legacy-test'").fetchone()[0]==1
print('v0.8.7 -> v0.9.0 schema migration: PASS')
c.close(); Path(tmp).unlink(missing_ok=True)
