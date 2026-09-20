"""Test the BisectHosting no-terminal boot hook using temporary SQLite only."""
import sqlite3
import tempfile
import threading
from pathlib import Path

from lude import config
from lude.crypto_21_migration import migrate_crypto_21
from lude.database import DatabaseMixin
from scripts.bisect_boot_v3 import prepare_from_bot_start
from scripts.prepare_full_v3 import verify_copy


class Fixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


def run():
    prior = config.DB_PATH
    try:
        with tempfile.TemporaryDirectory(prefix="lude-bisect-boot-") as directory:
            source = Path(directory) / "lude_economy.db"
            config.DB_PATH = str(source)
            cog = Fixture()
            cog.init_db()
            cog.ensure_user(201)
            conn = cog.connect()
            conn.execute("BEGIN IMMEDIATE")
            migrate_crypto_21(conn)
            conn.execute("UPDATE economy_users SET wallet=4321, judicial_debt=7 WHERE user_id=201")
            conn.execute("UPDATE bank_accounts SET balance=123 WHERE user_id=201 AND account_type='primary'")
            conn.commit()
            conn.close()
            report = prepare_from_bot_start(str(source))
            backup = source.with_name("lude_economy.pre-v3-backup.db")
            prepared = source.with_name("lude_economy.prepared-v3.db")
            assert report["status"] == "PREPARED_ONLY_NOT_ACTIVATED"
            assert backup.is_file() and prepared.is_file()
            assert report["backup_to_download_outside_hosting"]["sha256"]
            assert verify_copy(backup, prepared)["money_unit"] == "cents_v3"
            with sqlite3.connect(source) as conn:
                assert conn.execute("SELECT wallet,judicial_debt FROM economy_users WHERE user_id=201").fetchone() == (4321, 7)
            with sqlite3.connect(prepared) as conn:
                assert conn.execute("SELECT wallet,judicial_debt FROM economy_users WHERE user_id=201").fetchone() == (432100, 700)
            try:
                prepare_from_bot_start(str(source))
            except FileExistsError:
                pass
            else:
                raise AssertionError("Re-running preparation must never overwrite output files")
    finally:
        config.DB_PATH = prior
    print("OK: no-terminal bootstrap preserves original, creates verified backup/copy, refuses overwrite")


if __name__ == "__main__":
    run()
