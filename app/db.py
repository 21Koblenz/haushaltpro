import os
import threading
from contextvars import ContextVar
from pathlib import Path
from contextlib import contextmanager
from sqlcipher3 import dbapi2 as sqlite

DB_PATH = Path(os.getenv("DB_PATH", "/data/haushaltpro.db"))
_ctx_path: ContextVar[Path | None] = ContextVar("haushaltpro_db_path", default=None)
_ctx_key: ContextVar[str | None] = ContextVar("haushaltpro_db_key", default=None)
_state_lock = threading.RLock()
_write_lock = threading.RLock()
_thread_local = threading.local()
_connections = set()
_master_key: str | None = None

# Compatibility hook for the existing isolated sqlite test suite. Production
# never assigns _conn; tests can inject one in-memory/plain sqlite connection.
_conn = None


class PaymentConflict(Exception):
    """A linked payment would no longer match its booking or open item."""


def _payment_conflict(exc):
    if str(exc).startswith("HP_PAYMENT:"):
        raise PaymentConflict(str(exc).split(":", 1)[1]) from exc


def _quoted(value: str) -> str:
    # PRAGMA key/rekey do not support normal DB-API bind parameters reliably.
    # SQLCipher accepts a quoted passphrase; doubled quotes keep this safe.
    return "'" + value.replace("'", "''") + "'"


def _configure_cipher(c, key: str) -> None:
    c.execute(f"PRAGMA key = {_quoted(key)}")
    c.execute("PRAGMA cipher_compatibility = 4")
    c.execute("PRAGMA kdf_iter = 256000")
    c.execute("PRAGMA cipher_page_size = 4096")
    c.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
    c.execute("PRAGMA cipher_kdf_algorithm = PBKDF2_HMAC_SHA512")


def _configure_runtime(c) -> None:
    c.execute("PRAGMA foreign_keys = ON")
    c.execute("PRAGMA busy_timeout = 5000")
    c.execute("PRAGMA synchronous = NORMAL")
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA cache_size = -65536")
    c.execute("PRAGMA temp_store = MEMORY")
    c.execute("PRAGMA wal_autocheckpoint = 1000")


def connect(key: str, path: Path | str | None = None):
    target = Path(path or DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite.connect(str(target), check_same_thread=False)
    c.row_factory = sqlite.Row
    try:
        _configure_cipher(c, key)
        version = c.execute("PRAGMA cipher_version").fetchone()
        if not version or not version[0] or not str(version[0]).startswith("4."):
            raise RuntimeError(f"SQLCipher 4 erforderlich, gefunden: {version[0] if version else 'unbekannt'}")
        c.execute("SELECT count(*) FROM sqlite_master").fetchone()
        _configure_runtime(c)
        return c
    except Exception:
        c.close()
        raise


def _register_connection(c):
    with _state_lock:
        _connections.add(c)
    return c


def _close_managed_connections() -> None:
    global _connections
    with _state_lock:
        conns = list(_connections)
        _connections.clear()
    for c in conns:
        try:
            c.close()
        except Exception:
            pass
    try:
        delattr(_thread_local, "conn")
    except AttributeError:
        pass


def active_path() -> Path:
    return Path(_ctx_path.get() or DB_PATH)


def current_key() -> str | None:
    return _ctx_key.get() or _master_key


def activate(path: Path | str, key: str) -> None:
    target=Path(path)
    previous=getattr(_thread_local, "active_path", None)
    previous_key=getattr(_thread_local, "active_key", None)
    if previous is not None and (Path(previous) != target or previous_key != key):
        c=getattr(_thread_local, "conn", None)
        if c is not None:
            try: c.close()
            except Exception: pass
            try: _connections.discard(c)
            except Exception: pass
            try: delattr(_thread_local, "conn")
            except AttributeError: pass
    _thread_local.active_path=str(target)
    _thread_local.active_key=key
    _ctx_path.set(target)
    _ctx_key.set(key)


def clear_context() -> None:
    _ctx_path.set(None)
    _ctx_key.set(None)

def close_all_connections() -> None:
    """Close all managed SQLCipher handles before deleting/replacing a database file."""
    _close_managed_connections()


def is_initialized(path: Path | str | None = None) -> bool:
    target=Path(path or active_path())
    return target.exists() and target.stat().st_size > 0


def is_unlocked() -> bool:
    return _conn is not None or current_key() is not None


def unlock(key: str, initialize: bool = False, path: Path | str | None = None, set_default: bool = True):
    """Validate the key once, then retain only the key in memory.

    Production read connections are thread-local and write transactions get a
    dedicated SQLCipher connection. This removes the old single global
    connection shared by every FastAPI worker thread.
    """
    global _master_key
    target=Path(path or active_path())
    if _conn is not None:  # injected test connection
        if initialize:
            init_schema(_conn)
        return _conn
    with _state_lock:
        if set_default and _master_key is not None and target == DB_PATH:
            return db()
        c = connect(key, target)
        try:
            if initialize:
                init_schema(c)
            else:
                row = c.execute("SELECT value FROM app_meta WHERE key=?", ("db_magic",)).fetchone()
                if not row or row[0] not in {"HAUSHALTPRO_V2_SQLCIPHER4", "HAUSHALTPRO_V3_SQLCIPHER4"}:
                    raise RuntimeError("Ungültige HaushaltPro-Datenbank")
                migrate_schema(c)
        finally:
            c.close()
        if set_default and target == DB_PATH:
            _master_key = key
        activate(target,key)
    return db()


def close() -> None:
    global _master_key, _conn
    if _conn is not None:
        try:
            _conn.commit()
        except Exception:
            pass
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
    _close_managed_connections()
    _master_key = None
    clear_context()


def db():
    """Return a read/session connection local to the current worker thread."""
    if _conn is not None:
        return _conn
    key=current_key()
    if key is None:
        raise RuntimeError("DATABASE_LOCKED")
    target=active_path()
    c = getattr(_thread_local, "conn", None)
    current_path=getattr(_thread_local,"active_path",None)
    current_active_key=getattr(_thread_local,"active_key",None)
    if c is None or current_path != str(target) or current_active_key != key:
        if c is not None:
            try: c.close()
            except Exception: pass
        c = _register_connection(connect(key,target))
        _thread_local.conn = c
        _thread_local.active_path=str(target)
        _thread_local.active_key=key
    return c


@contextmanager
def transaction():
    """Use an isolated write connection and an explicit IMMEDIATE transaction."""
    if _conn is not None:  # tests / injected sqlite connection
        with _write_lock:
            try:
                _conn.execute("BEGIN IMMEDIATE")
                yield _conn
                _conn.commit()
            except Exception as exc:
                _conn.rollback()
                _payment_conflict(exc)
                raise
        return
    key=current_key()
    if key is None:
        raise RuntimeError("DATABASE_LOCKED")
    target=active_path()
    with _write_lock:
        c = connect(key,target)
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception as exc:
            c.rollback()
            _payment_conflict(exc)
            raise
        finally:
            c.close()


def checkpoint(truncate: bool = True) -> None:
    if _conn is not None:
        _conn.execute("PRAGMA wal_checkpoint(TRUNCATE)" if truncate else "PRAGMA wal_checkpoint(PASSIVE)")
        _conn.commit()
        return
    key=current_key()
    if key is None:
        raise RuntimeError("DATABASE_LOCKED")
    c = connect(key,active_path())
    try:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)" if truncate else "PRAGMA wal_checkpoint(PASSIVE)")
        c.commit()
    finally:
        c.close()

def init_schema(c) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS app_meta(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions(
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            csrf TEXT NOT NULL,
            trusted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS accounts(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL,
            iban TEXT,
            opening_balance INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'EUR',
            active INTEGER NOT NULL DEFAULT 1,
            start_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_iban
            ON accounts(iban) WHERE iban IS NOT NULL AND iban <> '';

        CREATE TABLE IF NOT EXISTS account_month_overrides(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            month TEXT NOT NULL,
            opening_balance INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            UNIQUE(account_id, month)
        );

        CREATE TABLE IF NOT EXISTS categories(
            id INTEGER PRIMARY KEY,
            parent_id INTEGER,
            name TEXT NOT NULL,
            direction TEXT NOT NULL DEFAULT 'expense',
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(parent_id) REFERENCES categories(id) ON DELETE SET NULL,
            UNIQUE(parent_id, name)
        );

        CREATE TABLE IF NOT EXISTS recurring_transfers(
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

        CREATE TABLE IF NOT EXISTS transfers(
            id INTEGER PRIMARY KEY,
            from_account_id INTEGER NOT NULL,
            to_account_id INTEGER NOT NULL,
            amount INTEGER NOT NULL CHECK(amount > 0),
            booking_date TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT 'Transfer',
            note TEXT,
            recurring_transfer_id INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
            FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
            FOREIGN KEY(recurring_transfer_id) REFERENCES recurring_transfers(id) ON DELETE SET NULL,
            CHECK(from_account_id <> to_account_id)
        );

        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            direction TEXT CHECK(direction IN ('expense','income')),
            booking_date TEXT NOT NULL,
            value_date TEXT,
            name TEXT,
            payee TEXT,
            note TEXT,
            category_id INTEGER,
            status TEXT NOT NULL DEFAULT 'executed' CHECK(status IN ('planned','executed','cancelled')),
            external_id TEXT,
            recurring_id INTEGER,
            transfer_id INTEGER,
            transfer_side TEXT CHECK(transfer_side IN ('out','in')),
            confidence TEXT NOT NULL DEFAULT 'fixed' CHECK(confidence IN ('fixed','likely','estimated')),
            fixed_cost INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL,
            FOREIGN KEY(recurring_id) REFERENCES recurring(id) ON DELETE SET NULL,
            FOREIGN KEY(transfer_id) REFERENCES transfers(id) ON DELETE SET NULL,
            UNIQUE(account_id, external_id)
        );

        CREATE TABLE IF NOT EXISTS transaction_tags(
            transaction_id INTEGER NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY(transaction_id, tag),
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS splits(
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            category_id INTEGER,
            amount INTEGER NOT NULL,
            note TEXT,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS recurring(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            category_id INTEGER,
            name TEXT NOT NULL,
            payee TEXT,
            amount INTEGER NOT NULL,
            next_date TEXT NOT NULL,
            frequency TEXT NOT NULL CHECK(frequency IN ('daily','weekly','monthly','yearly')),
            interval_count INTEGER NOT NULL DEFAULT 1 CHECK(interval_count >= 1),
            kind TEXT NOT NULL DEFAULT 'direct_debit' CHECK(kind IN ('direct_debit','standing_order','income')),
            max_amount INTEGER,
            active INTEGER NOT NULL DEFAULT 1,
            series_id INTEGER,
            anchor_date TEXT,
            valid_from TEXT,
            valid_until TEXT,
            confidence TEXT NOT NULL DEFAULT 'fixed' CHECK(confidence IN ('fixed','likely','estimated')),
            fixed_cost INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS recurring_overrides(
            id INTEGER PRIMARY KEY,
            series_id INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            booking_date TEXT,
            amount INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(series_id, due_date)
        );

        CREATE TABLE IF NOT EXISTS recurring_occurrences(
            id INTEGER PRIMARY KEY,
            recurring_id INTEGER NOT NULL,
            due_date TEXT NOT NULL,
            transaction_id INTEGER,
            status TEXT NOT NULL CHECK(status IN ('executed','skipped')),
            created_at TEXT NOT NULL,
            FOREIGN KEY(recurring_id) REFERENCES recurring(id) ON DELETE CASCADE,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE SET NULL,
            UNIQUE(recurring_id, due_date)
        );

        CREATE TABLE IF NOT EXISTS budgets(
            id INTEGER PRIMARY KEY,
            category_id INTEGER,
            month TEXT NOT NULL,
            amount INTEGER NOT NULL,
            strategy TEXT NOT NULL CHECK(strategy IN ('zero_based','envelope','50_30_20','pay_yourself_first','hybrid')),
            bucket TEXT NOT NULL DEFAULT 'free' CHECK(bucket IN ('free','needs','wants','savings')),
            note TEXT,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE,
            UNIQUE(category_id, month, strategy)
        );


        CREATE TABLE IF NOT EXISTS client_mutations(
            request_id TEXT PRIMARY KEY,
            endpoint TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS payee_presets(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            usage_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transaction_history(
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            snapshot_json TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        );


        CREATE TABLE IF NOT EXISTS attachments(
            id INTEGER PRIMARY KEY,
            transaction_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT,
            data BLOB NOT NULL,
            size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS account_reconciliations(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            checked_at TEXT NOT NULL,
            expected_balance INTEGER NOT NULL,
            actual_balance INTEGER NOT NULL,
            difference INTEGER NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS forecast_snapshots(
            id INTEGER PRIMARY KEY,
            month TEXT NOT NULL,
            captured_on TEXT NOT NULL,
            projected_end_balance INTEGER NOT NULL,
            UNIQUE(month,captured_on)
        );

        CREATE TABLE IF NOT EXISTS audit_log(
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            details_json TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS contracts(
            id INTEGER PRIMARY KEY,
            recurring_series_id INTEGER,
            title TEXT NOT NULL,
            provider TEXT,
            start_date TEXT,
            end_date TEXT,
            cancellation_deadline TEXT,
            notice_days INTEGER,
            notes TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS reconciliation_learning(
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('expense','income')),
            amount_cents INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT 'Kontokorrektur',
            accepted_count INTEGER NOT NULL DEFAULT 1,
            last_used_at TEXT NOT NULL,
            UNIQUE(account_id,direction,amount_cents,label),
            FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS finance_check_runs(
            id INTEGER PRIMARY KEY,
            checked_at TEXT NOT NULL,
            ok INTEGER NOT NULL,
            errors INTEGER NOT NULL,
            warnings INTEGER NOT NULL,
            result_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS investment_assets(
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            symbol TEXT,
            asset_type TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            manual_price REAL,
            purchase_price REAL NOT NULL DEFAULT 0,
            fees REAL NOT NULL DEFAULT 0,
            purchase_price_cents INTEGER NOT NULL DEFAULT 0,
            manual_price_cents INTEGER,
            fees_cents INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'EUR',
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE INDEX IF NOT EXISTS idx_account_override_month ON account_month_overrides(account_id, month);
        CREATE INDEX IF NOT EXISTS idx_tx_account_date ON transactions(account_id, booking_date);
        CREATE INDEX IF NOT EXISTS idx_tx_date_status ON transactions(booking_date, status);
        CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id);
        CREATE INDEX IF NOT EXISTS idx_splits_tx ON splits(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date, active);
        CREATE INDEX IF NOT EXISTS idx_recurring_transfer_active_date ON recurring_transfers(active, next_date);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_recurring_due ON transfers(recurring_transfer_id, booking_date) WHERE recurring_transfer_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_payee_usage ON payee_presets(usage_count DESC, last_used_at DESC);
        CREATE INDEX IF NOT EXISTS idx_client_mutations_created ON client_mutations(created_at);
        CREATE INDEX IF NOT EXISTS idx_recurring_account_date ON recurring(account_id, active, next_date);
        CREATE INDEX IF NOT EXISTS idx_occurrence_recurring_date ON recurring_occurrences(recurring_id, due_date);
        CREATE INDEX IF NOT EXISTS idx_recurring_override_date ON recurring_overrides(series_id, due_date);
        CREATE INDEX IF NOT EXISTS idx_occurrence_transaction ON recurring_occurrences(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_history_tx ON transaction_history(transaction_id, changed_at);
        CREATE INDEX IF NOT EXISTS idx_attachments_tx ON attachments(transaction_id);
        CREATE INDEX IF NOT EXISTS idx_reconcile_account_date ON account_reconciliations(account_id, checked_at);
        CREATE INDEX IF NOT EXISTS idx_forecast_snapshot_month ON forecast_snapshots(month, captured_on);
        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_contract_deadline ON contracts(active,cancellation_deadline);
        CREATE INDEX IF NOT EXISTS idx_reconcile_learning ON reconciliation_learning(account_id,direction,amount_cents);

        INSERT OR REPLACE INTO app_meta(key,value) VALUES('db_magic','HAUSHALTPRO_V3_SQLCIPHER4');
        INSERT OR REPLACE INTO app_meta(key,value) VALUES('schema_version','28');
        INSERT OR IGNORE INTO settings(key,value) VALUES('investment_tracking','false');
        INSERT OR IGNORE INTO settings(key,value) VALUES('autolock_minutes','15');
        INSERT OR IGNORE INTO settings(key,value) VALUES('budget_strategy','hybrid');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(1,NULL,'Wohnen','expense');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(2,NULL,'Lebensmittel','expense');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(3,NULL,'Transport','expense');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(4,NULL,'Freizeit','expense');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(5,NULL,'Einkommen','income');
        INSERT OR IGNORE INTO categories(id,parent_id,name,direction) VALUES(6,NULL,'Sparen & Rücklagen','savings');
        """
    )
    from .open_items import init_schema as init_open_items
    init_open_items(c)
    c.commit()



def migrate_schema(c) -> None:
    cols = {r[1] for r in c.execute("PRAGMA table_info(categories)").fetchall()}
    if "direction" not in cols:
        c.execute("ALTER TABLE categories ADD COLUMN direction TEXT NOT NULL DEFAULT 'expense'")
    c.execute("UPDATE categories SET direction='income' WHERE name='Einkommen'")
    c.execute("UPDATE categories SET direction='savings' WHERE name='Sparen & Rücklagen' AND direction='expense'")
    c.execute("UPDATE app_meta SET value='HAUSHALTPRO_V3_SQLCIPHER4' WHERE key='db_magic'")
    tcols = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
    if "direction" not in tcols:
        c.execute("ALTER TABLE transactions ADD COLUMN direction TEXT CHECK(direction IN ('expense','income'))")
    # Repair legacy v0.3.0/v0.3.1 manual bookings whose sign was stored incorrectly.
    c.execute("""UPDATE transactions SET direction=(SELECT direction FROM categories WHERE categories.id=transactions.category_id)
                 WHERE direction IS NULL AND category_id IS NOT NULL
                   AND external_id LIKE 'manual-%'""")
    c.execute("UPDATE transactions SET amount=-ABS(amount) WHERE direction='expense' AND amount>0")
    c.execute("UPDATE transactions SET amount= ABS(amount) WHERE direction='income' AND amount<0")
    acols = {r[1] for r in c.execute("PRAGMA table_info(accounts)").fetchall()}
    if "start_date" not in acols:
        c.execute("ALTER TABLE accounts ADD COLUMN start_date TEXT")
        # Existing accounts: first transaction date if available, otherwise account creation date/today.
        c.execute("""UPDATE accounts SET start_date=COALESCE(
            (SELECT MIN(booking_date) FROM transactions WHERE transactions.account_id=accounts.id),
            substr(created_at,1,10), date('now')) WHERE start_date IS NULL OR start_date=''""")
    tcols2 = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
    if "confidence" not in tcols2:
        c.execute("ALTER TABLE transactions ADD COLUMN confidence TEXT NOT NULL DEFAULT 'fixed'")
    if "fixed_cost" not in tcols2:
        c.execute("ALTER TABLE transactions ADD COLUMN fixed_cost INTEGER NOT NULL DEFAULT 0")
    rcols = {r[1] for r in c.execute("PRAGMA table_info(recurring)").fetchall()}
    if "series_id" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN series_id INTEGER")
    if "valid_from" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN valid_from TEXT")
    if "valid_until" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN valid_until TEXT")
    if "category_id" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN category_id INTEGER")
    if "anchor_date" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN anchor_date TEXT")
    c.execute("UPDATE recurring SET series_id=id WHERE series_id IS NULL")
    c.execute("UPDATE recurring SET valid_from=next_date WHERE valid_from IS NULL OR valid_from=''")
    c.execute("UPDATE recurring SET anchor_date=COALESCE(anchor_date,valid_from,next_date) WHERE anchor_date IS NULL OR anchor_date=''")
    c.execute("""CREATE TABLE IF NOT EXISTS recurring_overrides(
        id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL, due_date TEXT NOT NULL, amount INTEGER NOT NULL,
        note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(series_id,due_date))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_recurring_override_date ON recurring_overrides(series_id,due_date)")
    ocols = {r[1] for r in c.execute("PRAGMA table_info(recurring_overrides)").fetchall()}
    if "booking_date" not in ocols:
        c.execute("ALTER TABLE recurring_overrides ADD COLUMN booking_date TEXT")
    c.execute("CREATE INDEX IF NOT EXISTS idx_occurrence_transaction ON recurring_occurrences(transaction_id)")
    icols = {r[1] for r in c.execute("PRAGMA table_info(investment_assets)").fetchall()}
    if "purchase_price" not in icols:
        c.execute("ALTER TABLE investment_assets ADD COLUMN purchase_price REAL NOT NULL DEFAULT 0")
    if "fees" not in icols:
        c.execute("ALTER TABLE investment_assets ADD COLUMN fees REAL NOT NULL DEFAULT 0")
    c.execute("""CREATE TABLE IF NOT EXISTS account_month_overrides(
        id INTEGER PRIMARY KEY,
        account_id INTEGER NOT NULL,
        month TEXT NOT NULL,
        opening_balance INTEGER NOT NULL,
        note TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE,
        UNIQUE(account_id, month)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_account_override_month ON account_month_overrides(account_id, month)")
    bcols = {r[1] for r in c.execute("PRAGMA table_info(budgets)").fetchall()}
    if "bucket" not in bcols:
        c.execute("ALTER TABLE budgets ADD COLUMN bucket TEXT NOT NULL DEFAULT 'free'")

    rcols = {r[1] for r in c.execute("PRAGMA table_info(recurring)").fetchall()}
    if "confidence" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN confidence TEXT NOT NULL DEFAULT 'fixed'")
    if "fixed_cost" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN fixed_cost INTEGER NOT NULL DEFAULT 0")
    if "interval_count" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN interval_count INTEGER NOT NULL DEFAULT 1")
    if "payee" not in rcols:
        c.execute("ALTER TABLE recurring ADD COLUMN payee TEXT")
    c.execute("UPDATE recurring SET interval_count=1 WHERE interval_count IS NULL OR interval_count<1")
    c.execute("""UPDATE recurring SET payee=(
        SELECT t.payee FROM transactions t
        JOIN recurring rr ON rr.id=t.recurring_id
        WHERE COALESCE(rr.series_id,rr.id)=COALESCE(recurring.series_id,recurring.id)
          AND t.payee IS NOT NULL AND TRIM(t.payee)<>''
        ORDER BY t.booking_date,t.id LIMIT 1
    ) WHERE payee IS NULL OR TRIM(payee)=''""")
    c.execute("""CREATE TABLE IF NOT EXISTS attachments(
        id INTEGER PRIMARY KEY, transaction_id INTEGER NOT NULL, filename TEXT NOT NULL,
        content_type TEXT, data BLOB NOT NULL, size INTEGER NOT NULL, created_at TEXT NOT NULL,
        FOREIGN KEY(transaction_id) REFERENCES transactions(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS account_reconciliations(
        id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL, checked_at TEXT NOT NULL,
        expected_balance INTEGER NOT NULL, actual_balance INTEGER NOT NULL, difference INTEGER NOT NULL,
        note TEXT, created_at TEXT NOT NULL,
        FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS forecast_snapshots(
        id INTEGER PRIMARY KEY, month TEXT NOT NULL, captured_on TEXT NOT NULL,
        projected_end_balance INTEGER NOT NULL, UNIQUE(month,captured_on))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_attachments_tx ON attachments(transaction_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reconcile_account_date ON account_reconciliations(account_id,checked_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_forecast_snapshot_month ON forecast_snapshots(month,captured_on)")

    c.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY,user_id INTEGER,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT,
        details_json TEXT NOT NULL,prev_hash TEXT NOT NULL,entry_hash TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS contracts(
        id INTEGER PRIMARY KEY,recurring_series_id INTEGER,title TEXT NOT NULL,provider TEXT,start_date TEXT,end_date TEXT,
        cancellation_deadline TEXT,notice_days INTEGER,notes TEXT,active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS reconciliation_learning(
        id INTEGER PRIMARY KEY,account_id INTEGER NOT NULL,direction TEXT NOT NULL,amount_cents INTEGER NOT NULL,
        label TEXT NOT NULL DEFAULT 'Kontokorrektur',accepted_count INTEGER NOT NULL DEFAULT 1,last_used_at TEXT NOT NULL,
        UNIQUE(account_id,direction,amount_cents,label),FOREIGN KEY(account_id) REFERENCES accounts(id) ON DELETE CASCADE)""")
    c.execute("""CREATE TABLE IF NOT EXISTS finance_check_runs(
        id INTEGER PRIMARY KEY,checked_at TEXT NOT NULL,ok INTEGER NOT NULL,errors INTEGER NOT NULL,warnings INTEGER NOT NULL,result_json TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_contract_deadline ON contracts(active,cancellation_deadline)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_reconcile_learning ON reconciliation_learning(account_id,direction,amount_cents)")

    # Investment money fields migrate from REAL to integer cents without
    # destroying the legacy columns. New code exclusively uses *_cents.
    icols2 = {r[1] for r in c.execute("PRAGMA table_info(investment_assets)").fetchall()}
    if "purchase_price_cents" not in icols2:
        c.execute("ALTER TABLE investment_assets ADD COLUMN purchase_price_cents INTEGER NOT NULL DEFAULT 0")
        c.execute("UPDATE investment_assets SET purchase_price_cents=CAST(ROUND(COALESCE(purchase_price,0)*100) AS INTEGER)")
    if "manual_price_cents" not in icols2:
        c.execute("ALTER TABLE investment_assets ADD COLUMN manual_price_cents INTEGER")
        c.execute("UPDATE investment_assets SET manual_price_cents=CASE WHEN manual_price IS NULL THEN NULL ELSE CAST(ROUND(manual_price*100) AS INTEGER) END")
    if "fees_cents" not in icols2:
        c.execute("ALTER TABLE investment_assets ADD COLUMN fees_cents INTEGER NOT NULL DEFAULT 0")
        c.execute("UPDATE investment_assets SET fees_cents=CAST(ROUND(COALESCE(fees,0)*100) AS INTEGER)")

    tcols3 = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
    if "name" not in tcols3:
        c.execute("ALTER TABLE transactions ADD COLUMN name TEXT")
        c.execute("UPDATE transactions SET name=COALESCE(NULLIF(TRIM(payee),''),NULLIF(TRIM(note),''),'Buchung') WHERE name IS NULL OR TRIM(name)=''")
    c.execute("""CREATE TABLE IF NOT EXISTS recurring_transfers(
        id INTEGER PRIMARY KEY,from_account_id INTEGER NOT NULL,to_account_id INTEGER NOT NULL,
        amount INTEGER NOT NULL CHECK(amount > 0),next_date TEXT NOT NULL,
        frequency TEXT NOT NULL CHECK(frequency IN ('daily','weekly','monthly','yearly')),
        interval_count INTEGER NOT NULL DEFAULT 1 CHECK(interval_count >= 1),
        name TEXT NOT NULL DEFAULT 'Transfer',note TEXT,valid_until TEXT,active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        CHECK(from_account_id <> to_account_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS transfers(
        id INTEGER PRIMARY KEY,from_account_id INTEGER NOT NULL,to_account_id INTEGER NOT NULL,
        amount INTEGER NOT NULL CHECK(amount > 0),booking_date TEXT NOT NULL,name TEXT NOT NULL DEFAULT 'Transfer',
        note TEXT,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
        FOREIGN KEY(from_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        FOREIGN KEY(to_account_id) REFERENCES accounts(id) ON DELETE RESTRICT,
        CHECK(from_account_id <> to_account_id))""")
    transfer_cols = {r[1] for r in c.execute("PRAGMA table_info(transfers)").fetchall()}
    if "recurring_transfer_id" not in transfer_cols:
        c.execute("ALTER TABLE transfers ADD COLUMN recurring_transfer_id INTEGER")
    tcols4 = {r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()}
    if "transfer_id" not in tcols4:
        c.execute("ALTER TABLE transactions ADD COLUMN transfer_id INTEGER")
    if "transfer_side" not in tcols4:
        c.execute("ALTER TABLE transactions ADD COLUMN transfer_side TEXT")
    c.execute("""CREATE TABLE IF NOT EXISTS payee_presets(
        id INTEGER PRIMARY KEY,name TEXT NOT NULL COLLATE NOCASE UNIQUE,usage_count INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,last_used_at TEXT NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS client_mutations(
        request_id TEXT PRIMARY KEY,endpoint TEXT NOT NULL,response_json TEXT NOT NULL,created_at TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tx_transfer ON transactions(transfer_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_splits_tx ON splits(transaction_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_transfer_date ON transfers(booking_date,active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_recurring_transfer_active_date ON recurring_transfers(active,next_date)")
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_transfer_recurring_due ON transfers(recurring_transfer_id,booking_date) WHERE recurring_transfer_id IS NOT NULL")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payee_usage ON payee_presets(usage_count DESC,last_used_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_client_mutations_created ON client_mutations(created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tx_category_date ON transactions(category_id,booking_date,status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tags_tag_tx ON transaction_tags(tag,transaction_id)")
    from .open_items import init_schema as init_open_items
    init_open_items(c)
    c.execute("INSERT INTO app_meta(key,value) VALUES('schema_version','28') ON CONFLICT(key) DO UPDATE SET value='28'")
    c.commit()

def rekey(new_key: str) -> None:
    global _master_key
    if _conn is not None:
        _conn.execute(f"PRAGMA rekey = {_quoted(new_key)}")
        _conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        _conn.commit()
        return
    old_key=current_key()
    if old_key is None:
        raise RuntimeError("DATABASE_LOCKED")
    target=active_path()
    _close_managed_connections()
    with _write_lock:
        c=connect(old_key,target)
        try:
            c.execute(f"PRAGMA rekey = {_quoted(new_key)}")
            c.execute("SELECT count(*) FROM sqlite_master").fetchone()
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            c.commit()
        finally:
            c.close()
    if target == DB_PATH:
        _master_key=new_key
    activate(target,new_key)

def cipher_info() -> dict:
    c = db()
    return {
        "cipher_version": c.execute("PRAGMA cipher_version").fetchone()[0],
        "kdf_iter": int(c.execute("PRAGMA kdf_iter").fetchone()[0]),
        "page_size": int(c.execute("PRAGMA cipher_page_size").fetchone()[0]),
        "hmac_algorithm": c.execute("PRAGMA cipher_hmac_algorithm").fetchone()[0],
        "kdf_algorithm": c.execute("PRAGMA cipher_kdf_algorithm").fetchone()[0],
        "journal_mode": c.execute("PRAGMA journal_mode").fetchone()[0],
    }


def integrity_check() -> list[str]:
    c = db()
    return [str(r[0]) for r in c.execute("PRAGMA cipher_integrity_check").fetchall()]


def verify_database_file(path: Path | str, key: str) -> None:
    c = connect(key, path=path)
    try:
        row = c.execute("SELECT value FROM app_meta WHERE key=?", ("db_magic",)).fetchone()
        if not row or row[0] not in {"HAUSHALTPRO_V2_SQLCIPHER4", "HAUSHALTPRO_V3_SQLCIPHER4"}:
            raise RuntimeError("Backup enthält keine kompatible HaushaltPro-Datenbank")
        errors = [r[0] for r in c.execute("PRAGMA cipher_integrity_check").fetchall()]
        if errors:
            raise RuntimeError("SQLCipher-Integritätsprüfung fehlgeschlagen")
    finally:
        c.close()
