"""No production data: verify Lude v3 preflight and copy checks in temp files."""
import sqlite3
import tempfile
import threading
from pathlib import Path

from lude import config
from lude.crypto_21_migration import migrate_crypto_21
from lude.database import DatabaseMixin
from scripts.prepare_full_v3 import prepare, verify_copy


class Fixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


def run():
    original_db = config.DB_PATH
    with tempfile.TemporaryDirectory(prefix="lude-v3-preflight-") as folder:
        source, target = Path(folder) / "legacy.db", Path(folder) / "prepared.db"
        config.DB_PATH = str(source)
        fixture = Fixture()
        fixture.init_db()
        fixture.ensure_user(101)
        conn = fixture.connect()
        conn.execute("BEGIN IMMEDIATE")
        migrate_crypto_21(conn)
        conn.execute("UPDATE economy_users SET wallet=123456,judicial_debt=80 WHERE user_id=101")
        conn.execute("UPDATE bank_accounts SET balance=7890 WHERE user_id=101 AND account_type='primary'")
        conn.execute("INSERT INTO crypto_holdings(user_id,symbol,quantity,cost_basis) VALUES(101,'FLX',10000158.72044755,1234.56)")
        conn.commit(); conn.close()
        output = prepare(str(source), str(target))
        assert output["source_unchanged"] and output["verified"]["users"] == 1
        assert output["verified"]["savings"] == 1
        assert len(output["sha256"]) == 64
        assert verify_copy(source, target)["positions"] == 1
        conn = sqlite3.connect(source)
        assert conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == 123456
        conn.close()
        conn = sqlite3.connect(target)
        assert conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == 12345600
        conn.execute("UPDATE crypto_market SET price=price*2 WHERE symbol='FLX'")
        conn.commit(); conn.close()
        try:
            verify_copy(source, target)
        except AssertionError as exc:
            assert "crypto_market" in str(exc)
        else:
            raise AssertionError("Market tampering was not detected")
        try:
            prepare(str(source), str(target))
        except FileExistsError:
            pass
        else:
            raise AssertionError("An existing destination was overwritten")
    config.DB_PATH = original_db
    print("OK: verified offline v3 copy, immutable original, no overwrite, market-state tampering detected")


if __name__ == "__main__":
    run()
