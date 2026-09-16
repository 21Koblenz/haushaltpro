"""Schema-26 upgrade with the actual SQLCipher runtime, preserving existing data."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import db
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'encrypted.db'
    c=db.connect('disposable-migration-test-key',path)
    db.init_schema(c)
    # Simulate the schema before open items existed, including its missing triggers.
    for name in ('guard_allocated_transaction','unlink_cancelled_payment','guard_open_item_update'):
        c.execute('DROP TRIGGER '+name)
    c.execute('DROP TABLE open_item_payments')
    c.execute('DROP TABLE open_items')
    c.execute('ALTER TABLE recurring_overrides DROP COLUMN booking_date')
    c.execute("UPDATE app_meta SET value='26' WHERE key='schema_version'")
    c.execute("INSERT INTO recurring_overrides(series_id,due_date,amount,note,created_at,updated_at) VALUES(1,'2026-09-20',-12345,'Vorhandene Ausnahme','2026-09-01','2026-09-01')")
    c.commit();c.close()
    assert path.read_bytes()[:16]!=b'SQLite format 3\x00'
    c=db.connect('disposable-migration-test-key',path)
    db.migrate_schema(c);db.migrate_schema(c)
    row=c.execute('SELECT amount,note,booking_date FROM recurring_overrides').fetchone()
    assert tuple(row)==(-12345,'Vorhandene Ausnahme',None),tuple(row)
    assert c.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()[0]=='28'
    assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert c.execute("SELECT COUNT(*) FROM open_items").fetchone()[0]==0
    c.execute("INSERT INTO open_items(kind,name,payee,amount,created_at,updated_at) VALUES('receivable','Test','Max',20000,'2026-09-16','2026-09-16')")
    c.commit()
    db.migrate_schema(c)
    assert c.execute('SELECT amount FROM open_items').fetchone()[0]==20000
    c.close()
print('SQLCipher schema 26 -> 28 with existing data and repeat migration: PASS')
