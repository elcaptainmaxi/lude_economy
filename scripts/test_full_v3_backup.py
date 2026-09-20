"""Verify independent backup and SQLite financial overflow guards offline."""
from __future__ import annotations

import sqlite3
import tempfile
import threading
from pathlib import Path

from lude import config
from lude.crypto_21_migration import migrate_crypto_21
from lude.database import DatabaseMixin
from lude.migrate_money_v3 import migrate_copy
from lude.money_v3 import MAX_SQLITE_INT
from lude.v3_guards import install_guards
from scripts.backup_lude_v3 import create_backup


class Fixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


def run():
    previous = config.DB_PATH
    with tempfile.TemporaryDirectory(prefix="lude-backup-test-") as directory:
        source = Path(directory) / "legacy.db"
        backup = Path(directory) / "independent-backup.db"
        target = Path(directory) / "converted.db"
        config.DB_PATH = str(source)
        fixture = Fixture()
        fixture.init_db()
        fixture.ensure_user(101)
        conn = fixture.connect()
        conn.execute("BEGIN IMMEDIATE")
        migrate_crypto_21(conn)
        conn.execute("UPDATE economy_users SET wallet=50 WHERE user_id=101")
        conn.commit(); conn.close()
        output = create_backup(str(source), str(backup))
        assert output["integrity_check"] == "ok" and len(output["sha256"]) == 64
        conn = sqlite3.connect(backup)
        assert conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == 50
        conn.close()
        try:
            create_backup(str(source), str(backup))
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing backup was overwritten")
        migrate_copy(str(source), str(target))
        conn = sqlite3.connect(target)
        conn.execute("BEGIN IMMEDIATE")
        install_guards(conn)
        conn.commit()
        conn.execute("UPDATE economy_users SET wallet=? WHERE user_id=101", (MAX_SQLITE_INT,))
        conn.commit()
        try:
            conn.execute("UPDATE economy_users SET wallet=wallet+1 WHERE user_id=101")
        except sqlite3.IntegrityError:
            conn.rollback()
        else:
            raise AssertionError("SQLite promoted a cent balance to REAL without rejection")
        assert conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == MAX_SQLITE_INT
        assert conn.execute("SELECT typeof(wallet) FROM economy_users WHERE user_id=101").fetchone()[0] == "integer"
        try:
            conn.execute("UPDATE bank_accounts SET balance=-1 WHERE user_id=101 AND account_type='primary'")
        except sqlite3.IntegrityError:
            conn.rollback()
        else:
            raise AssertionError("Negative bank balance was accepted")
        conn.close()
        assert sqlite3.connect(backup).execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == 50
    config.DB_PATH = previous
    print("OK: independent backup, no overwrite, overflow and negative balance rejected, backup unchanged")


if __name__ == "__main__":
    run()
