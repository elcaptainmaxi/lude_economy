"""SQLite-only tests: no bot, no production DB, no discord imports.

Run from repository root: python -m scripts.test_crypto_21_migration
"""
import sqlite3
from lude.crypto_21_migration import migrate_crypto_21, NEW_COLUMNS


def make_db():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE crypto_market(symbol TEXT PRIMARY KEY, price REAL NOT NULL,
            buy_volume REAL NOT NULL DEFAULT 0, sell_volume REAL NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL);
        CREATE TABLE crypto_engine_state(symbol TEXT PRIMARY KEY,
            fundamental REAL NOT NULL, regime TEXT NOT NULL DEFAULT 'sideways',
            regime_ticks INTEGER NOT NULL DEFAULT 0,
            volatility REAL NOT NULL DEFAULT 0.35, pressure REAL NOT NULL DEFAULT 0,
            stable_ticks INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE bank_accounts(user_id INTEGER, account_type TEXT,
            level INTEGER, balance INTEGER, PRIMARY KEY(user_id,account_type));
        CREATE TABLE crypto_holdings(user_id INTEGER, symbol TEXT, quantity REAL,
            cost_basis REAL, PRIMARY KEY(user_id,symbol));
        CREATE TABLE crypto_history(id INTEGER PRIMARY KEY, symbol TEXT,
            price REAL, created_at INTEGER);
        INSERT INTO crypto_market VALUES ('FLX',.59,500,23,123456);
        INSERT INTO crypto_market VALUES ('NVA',885.31,0,100,123457);
        INSERT INTO crypto_market VALUES ('IC',1783.88,0,0,123458);
        INSERT INTO crypto_engine_state(symbol,fundamental) VALUES ('FLX',38),('NVA',274.60),('IC',1040);
        INSERT INTO bank_accounts VALUES (42,'primary',4,123456);
        INSERT INTO crypto_holdings VALUES (42,'FLX',4.5,100);
        INSERT INTO crypto_history VALUES (1,'FLX',.61,123450);
    ''')
    return conn


def run_tests():
    conn = make_db()
    try:
        protected = ('crypto_market','bank_accounts','crypto_holdings','crypto_history')
        before = {name: conn.execute('SELECT * FROM '+name).fetchall() for name in protected}
        initial_fundamentals = conn.execute('SELECT symbol,fundamental FROM crypto_engine_state ORDER BY symbol').fetchall()
        conn.execute('BEGIN EXCLUSIVE')
        migrate_crypto_21(conn)
        conn.commit()
        cols = {row[1] for row in conn.execute('PRAGMA table_info(crypto_engine_state)')}
        assert set(NEW_COLUMNS).issubset(cols)
        assert {s: (a, r, t, b) for s,a,r,t,b in conn.execute('''
           SELECT symbol,anchor,anchor_reference,anchor_ticks,flow_baseline
             FROM crypto_engine_state''')} == {
             'FLX':(.59,.59,0,0), 'NVA':(885.31,885.31,0,0),
             'IC':(1783.88,1783.88,0,0)}
        assert initial_fundamentals == conn.execute('SELECT symbol,fundamental FROM crypto_engine_state ORDER BY symbol').fetchall()
        assert before == {name: conn.execute('SELECT * FROM '+name).fetchall() for name in protected}
        conn.execute("UPDATE crypto_engine_state SET anchor=1.23, anchor_reference=1.3, anchor_ticks=18, flow_baseline=.3 WHERE symbol='FLX'")
        conn.commit()
        conn.execute('BEGIN EXCLUSIVE')
        migrate_crypto_21(conn)
        conn.commit()
        assert conn.execute("SELECT anchor,anchor_reference,anchor_ticks,flow_baseline FROM crypto_engine_state WHERE symbol='FLX'").fetchone() == (1.23,1.3,18,.3)
        assert before == {name: conn.execute('SELECT * FROM '+name).fetchall() for name in protected}
        print('PASS: additive schema, existing prices/holdings/balances/history, initial anchors, idempotency')
    finally:
        conn.close()

    bad = make_db()
    try:
        bad.execute("UPDATE crypto_market SET price=-1 WHERE symbol='FLX'")
        bad.commit()
        try:
            bad.execute('BEGIN EXCLUSIVE')
            migrate_crypto_21(bad)
        except RuntimeError:
            bad.rollback()
        else:
            raise AssertionError('Invalid price must reject migration')
        assert not set(NEW_COLUMNS).intersection(row[1] for row in bad.execute('PRAGMA table_info(crypto_engine_state)'))
        print('PASS: invalid data aborts and rolls back schema changes')
    finally:
        bad.close()


if __name__ == '__main__':
    run_tests()
