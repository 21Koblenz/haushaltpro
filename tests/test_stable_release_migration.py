"""Upgrade a real encrypted v0.21.8 database (schema 22) without a dev stopover."""
import importlib.util
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from app import db

spec = importlib.util.spec_from_file_location('db_v0218', root / 'tests/fixtures/db_v0218.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)

with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / 'stable-encrypted.db'
    key = 'disposable-stable-migration-test-key'
    c = old.connect(key, path)
    old.init_schema(c); old.migrate_schema(c)
    assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0] == '22'
    c.execute("INSERT INTO accounts(id,name,type,opening_balance,start_date,created_at) VALUES(1,'Giro','checking',123456,'2026-01-01','2026-01-01')")
    c.execute("INSERT INTO recurring(id,series_id,account_id,name,amount,next_date,frequency,created_at) VALUES(1,1,1,'Miete',-50000,'2026-09-20','monthly','2026-01-01')")
    c.execute("INSERT INTO transactions(id,account_id,name,payee,amount,direction,booking_date,recurring_id,created_at,updated_at) VALUES(1,1,'Miete','Vermieter',-50000,'expense','2026-08-20',1,'2026-08-20','2026-08-20')")
    c.execute("INSERT INTO recurring_overrides(series_id,due_date,amount,note,created_at,updated_at) VALUES(1,'2026-09-20',-45000,'Alte Betragsausnahme','2026-09-01','2026-09-01')")
    c.execute("INSERT INTO recurring_occurrences(recurring_id,due_date,transaction_id,status,created_at) VALUES(1,'2026-08-20',1,'executed','2026-08-20')")
    c.execute("INSERT INTO account_month_overrides(account_id,month,opening_balance,note,created_at) VALUES(1,'2026-09',73456,'Abgleich','2026-09-01')")
    c.commit();c.close()
    assert path.read_bytes()[:16] != b'SQLite format 3\x00'
    c = db.connect(key, path)
    db.migrate_schema(c);db.migrate_schema(c)
    assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0] == '28'
    assert tuple(c.execute('SELECT name,opening_balance FROM accounts WHERE id=1').fetchone()) == ('Giro',123456)
    assert tuple(c.execute('SELECT name,payee,amount,recurring_id FROM transactions WHERE id=1').fetchone()) == ('Miete','Vermieter',-50000,1)
    assert tuple(c.execute('SELECT amount,interval_count FROM recurring WHERE id=1').fetchone()) == (-50000,1)
    assert tuple(c.execute('SELECT amount,note,booking_date FROM recurring_overrides').fetchone()) == (-45000,'Alte Betragsausnahme',None)
    assert c.execute('SELECT COUNT(*) FROM recurring_occurrences').fetchone()[0] == 1
    assert c.execute('SELECT opening_balance FROM account_month_overrides').fetchone()[0] == 73456
    for table in ('open_items','open_item_payments','recurring_transfers','client_mutations'):
        assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] == 0
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    c.close()
print('Real SQLCipher v0.21.8 -> v0.21.9, schema 22 -> 28, data preservation and repeated migration: PASS')
