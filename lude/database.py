import sqlite3
import time

from . import config


class DatabaseMixin:
    """Único punto de acceso a la base SQLite de Lude Economy."""

    def connect(self):
        conn = sqlite3.connect(config.DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_users (
                    user_id INTEGER PRIMARY KEY,
                    wallet INTEGER NOT NULL DEFAULT 0,
                    work_xp INTEGER NOT NULL DEFAULT 0,
                    current_job TEXT NOT NULL DEFAULT 'changas',
                    last_work_at INTEGER NOT NULL DEFAULT 0,
                    last_crime_at INTEGER NOT NULL DEFAULT 0,
                    last_rob_at INTEGER NOT NULL DEFAULT 0,
                    arrested INTEGER NOT NULL DEFAULT 0,
                    bail_due INTEGER NOT NULL DEFAULT 0,
                    judicial_debt INTEGER NOT NULL DEFAULT 0,
                    protection_until INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_progress (
                    user_id INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, job_id)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bank_accounts (
                    user_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, account_type)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bank_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    balance_after INTEGER NOT NULL DEFAULT 0,
                    details TEXT,
                    created_at INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_by INTEGER,
                    updated_at INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_admin_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setting_key TEXT NOT NULL,
                    action TEXT NOT NULL,
                    previous_value TEXT NOT NULL,
                    new_value TEXT NOT NULL,
                    changed_by INTEGER NOT NULL,
                    changed_at INTEGER NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_economy_admin_audit_recent ON economy_admin_audit(id DESC)")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS casino_state (
                    key TEXT PRIMARY KEY,
                    value REAL NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_market (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    buy_volume REAL NOT NULL DEFAULT 0,
                    sell_volume REAL NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_holdings (
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0,
                    cost_basis REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, symbol)
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            cur.execute(
                "INSERT OR IGNORE INTO casino_state(key, value) VALUES('slots_jackpot', ?)",
                (config.SLOTS_JACKPOT_BASE,),
            )

            now = int(time.time())
            for symbol, values in config.CRYPTO_CONFIG.items():
                cur.execute(
                    "INSERT OR IGNORE INTO crypto_market(symbol, name, price, updated_at) VALUES(?, ?, ?, ?)",
                    (symbol, values["name"], values["initial"], now),
                )
                exists = cur.execute(
                    "SELECT 1 FROM crypto_history WHERE symbol = ? LIMIT 1", (symbol,)
                ).fetchone()
                if not exists:
                    cur.execute(
                        "INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)",
                        (symbol, values["initial"], now),
                    )

            # Migraciones estrictamente aditivas; no modifican saldos, precios ni tenencias.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_engine_state (
                    symbol TEXT PRIMARY KEY,
                    fundamental REAL NOT NULL,
                    regime TEXT NOT NULL DEFAULT 'sideways',
                    regime_ticks INTEGER NOT NULL DEFAULT 0,
                    volatility REAL NOT NULL DEFAULT 0.35,
                    pressure REAL NOT NULL DEFAULT 0,
                    stable_ticks INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_global_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    sentiment REAL NOT NULL DEFAULT 0
                )
            """)
            cur.execute("INSERT OR IGNORE INTO crypto_global_state(id, sentiment) VALUES(1, 0)")
            for symbol, values in config.CRYPTO_CONFIG.items():
                cur.execute(
                    "INSERT OR IGNORE INTO crypto_engine_state(symbol, fundamental) VALUES(?, ?)",
                    (symbol, float(values["initial"])),
                )
            conn.commit()
            conn.close()

    def ensure_user(self, user_id: int):
        now = int(time.time())
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO economy_users(user_id, created_at) VALUES(?, ?)",
                (user_id, now),
            )
            cur.execute(
                "INSERT OR IGNORE INTO bank_accounts(user_id, account_type, level, balance) VALUES(?, 'primary', 1, 0)",
                (user_id,),
            )
            cur.execute(
                "INSERT OR IGNORE INTO job_progress(user_id, job_id, xp) VALUES(?, 'changas', 0)",
                (user_id,),
            )
            conn.commit()
            conn.close()

    def get_user(self, user_id: int):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            row = conn.execute(
                "SELECT * FROM economy_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            conn.close()
            return row

    def get_bank(self, user_id: int, account_type: str = "primary"):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            row = conn.execute(
                "SELECT * FROM bank_accounts WHERE user_id = ? AND account_type = ?",
                (user_id, account_type),
            ).fetchone()
            conn.close()
            return row

    def bank_capacity(self, account) -> int:
        return config.BANK_LEVELS[int(account["level"])]["capacity"]

    def bank_free(self, user_id: int, account_type: str = "primary", include_reservation: bool = True) -> int:
        account = self.get_bank(user_id, account_type)
        if not account:
            return 0
        free = self.bank_capacity(account) - int(account["balance"])
        if account_type == "primary" and include_reservation:
            free -= self.bank_reservations.get(user_id, 0)
        return max(0, free)

    def log_bank(self, cur, user_id: int, account_type: str, action: str, amount: int, balance_after: int, details: str = ""):
        now = int(time.time())
        cur.execute(
            """INSERT INTO bank_history
               (user_id, account_type, action, amount, balance_after, details, created_at)
               VALUES(?, ?, ?, ?, ?, ?, ?)""",
            (user_id, account_type, action, int(amount), int(balance_after), details, now),
        )
        cur.execute("""
            DELETE FROM bank_history
            WHERE user_id = ?
              AND id NOT IN (
                  SELECT id FROM bank_history
                  WHERE user_id = ?
                  ORDER BY created_at DESC, id DESC
                  LIMIT ?
              )
        """, (user_id, user_id, int(config.BANK_HISTORY_KEEP)))
