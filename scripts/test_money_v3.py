"""Run offline with: python -m scripts.test_money_v3"""
import sqlite3
import tempfile
from decimal import Decimal
from pathlib import Path

from lude.money_v3 import cents, format_cents, quote_net_sale, quote_sale
from lude.migrate_money_v3 import migrate_copy


def test_money():
    assert cents("7.500,25".replace(".", "")) == 750025
    assert cents("7500.25") == 750025
    assert format_cents(750025) == "INT$ 7.500,25"
    for bad in ("1.234", "-1", "0", "NaN", "Infinity", "abc", "1e100"):
        try:
            cents(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid input accepted: {bad!r}")
    quote = quote_net_sale(requested_cents=750025, symbol="FLX", available_quantity=Decimal("1000"),
                           price=Decimal("30"), cost_basis_cents=1_000_000, fee_rate=Decimal("0.01"),
                           judicial_rate=Decimal("0.25"), judicial_debt_cents=100000,
                           destination="savings")
    assert quote.credited_cents >= 750025
    try:
        previous = quote_sale(symbol="FLX", quantity=quote.quantity - Decimal("0.00000001"),
                              available_quantity=Decimal("1000"), price=Decimal("30"),
                              cost_basis_cents=1_000_000, fee_rate=Decimal("0.01"),
                              judicial_rate=Decimal("0.25"), judicial_debt_cents=100000,
                              destination="savings")
    except ValueError:
        pass
    else:
        assert previous.credited_cents < 750025, (previous, quote)


def test_migration():
    with tempfile.TemporaryDirectory() as root:
        original = Path(root) / "source.db"
        copy = Path(root) / "migrated.db"
        conn = sqlite3.connect(original)
        conn.executescript("""
            CREATE TABLE economy_users (user_id INTEGER PRIMARY KEY, wallet INTEGER, bail_due INTEGER, judicial_debt INTEGER);
            CREATE TABLE bank_accounts (user_id INTEGER, account_type TEXT, level INTEGER, balance INTEGER,
                                        PRIMARY KEY (user_id, account_type));
            CREATE TABLE bank_history (id INTEGER PRIMARY KEY, user_id INTEGER, account_type TEXT, action TEXT,
                                       amount INTEGER, balance_after INTEGER, details TEXT, created_at INTEGER);
            CREATE TABLE crypto_holdings (user_id INTEGER, symbol TEXT, quantity REAL, cost_basis REAL,
                                          PRIMARY KEY (user_id, symbol));
            CREATE TABLE crypto_market (symbol TEXT PRIMARY KEY, price REAL, buy_volume REAL, sell_volume REAL, updated_at INTEGER);
            CREATE TABLE crypto_history (id INTEGER PRIMARY KEY, symbol TEXT, price REAL, created_at INTEGER);
            CREATE TABLE crypto_engine_state (symbol TEXT PRIMARY KEY, fundamental REAL, anchor REAL);
            CREATE TABLE crypto_global_state (id INTEGER PRIMARY KEY, sentiment REAL);
            CREATE TABLE casino_state (key TEXT PRIMARY KEY, value REAL);
            CREATE TABLE economy_settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE job_progress (user_id INTEGER, job_id TEXT, xp INTEGER);
            INSERT INTO economy_users VALUES(42, 12345, 20, 200);
            INSERT INTO bank_accounts VALUES(42,'primary',3,9999);
            INSERT INTO bank_history VALUES(1,42,'primary','deposit',42,9999,'test',1000);
            INSERT INTO crypto_holdings VALUES(42,'FLX',10000158.72044755,12500.25);
            INSERT INTO crypto_market VALUES('FLX',50.1234,15.5,12.25,1000);
            INSERT INTO crypto_history VALUES(1,'FLX',50.1234,1000);
            INSERT INTO crypto_engine_state VALUES('FLX',50,49.98);
            INSERT INTO crypto_global_state VALUES(1,0.2);
            INSERT INTO casino_state VALUES('slots_jackpot',10000);
        """)
        conn.commit()
        conn.close()
        first = migrate_copy(str(original), str(copy))
        assert first["savings_accounts"] == 1
        conn = sqlite3.connect(copy)
        assert conn.execute("SELECT wallet,bail_due,judicial_debt FROM economy_users").fetchone() == (1234500,2000,20000)
        assert conn.execute("SELECT balance FROM bank_accounts WHERE account_type='primary'").fetchone()[0] == 999900
        assert conn.execute("SELECT balance FROM bank_accounts WHERE account_type='savings'").fetchone()[0] == 0
        assert conn.execute("SELECT cost_basis_cents FROM crypto_holdings").fetchone()[0] == 1250025
        assert conn.execute("SELECT quantity FROM crypto_holdings").fetchone()[0] == 10000158.72044755
        assert conn.execute("SELECT price,buy_volume,sell_volume FROM crypto_market").fetchone() == (50.1234,15.5,12.25)
        assert conn.execute("SELECT fundamental,anchor FROM crypto_engine_state").fetchone() == (50,49.98)
        assert conn.execute("SELECT value FROM casino_state_cents WHERE key='slots_jackpot'").fetchone()[0] == 1000000
        conn.close()
        conn = sqlite3.connect(original)
        assert conn.execute("SELECT wallet FROM economy_users").fetchone()[0] == 12345
        conn.close()
        try:
            migrate_copy(str(copy), str(Path(root) / "twice.db"))
        except ValueError:
            pass
        else:
            raise AssertionError("Double migration was not rejected")


if __name__ == "__main__":
    test_money()
    test_migration()
    print("OK: money parsing, net quote and additive copy migration")
