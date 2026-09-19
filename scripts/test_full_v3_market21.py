"""Verify a REAL calibrated Market Engine 2.1 tick using a fake economy DB."""
import asyncio
import tempfile
import threading
from pathlib import Path

import discord
from discord.ext import commands

from lude import config
from lude.crypto_21_migration import migrate_crypto_21
from lude.database import DatabaseMixin
from lude.migrate_money_v3 import migrate_copy
from lude.money_v3 import cents


class Fixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


def run():
    original_path = config.DB_PATH
    with tempfile.TemporaryDirectory(prefix="lude-v3-market-") as folder:
        legacy = Path(folder) / "source.db"
        migrated = Path(folder) / "migrated.db"
        config.DB_PATH = str(legacy)
        fixture = Fixture()
        fixture.init_db()
        fixture.ensure_user(101)
        conn = fixture.connect()
        conn.execute("BEGIN IMMEDIATE")
        migrate_crypto_21(conn)
        conn.execute("UPDATE bank_accounts SET level=7,balance=25000 WHERE user_id=101 AND account_type='primary'")
        conn.execute("UPDATE crypto_market SET price=29.1234 WHERE symbol='FLX'")
        conn.execute("UPDATE crypto_engine_state SET fundamental=50,anchor=29.1234,anchor_reference=29.1234 WHERE symbol='FLX'")
        conn.commit()
        conn.close()
        migrate_copy(str(legacy), str(migrated))
        config.DB_PATH = str(migrated)
        from lude.core import LudeEconomy
        from lude.crypto_21_bridge import CryptoMixin21, state_schema_ready
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        cog = LudeEconomy(bot)
        ok, message = cog.crypto_buy(101, "FLX", cents("10,25"))
        assert ok, message
        conn = cog.connect()
        assert state_schema_ready(conn)
        before = conn.execute("SELECT price,buy_volume FROM crypto_market WHERE symbol='FLX'").fetchone()
        assert before["price"] == 29.1234
        assert abs(before["buy_volume"] - 10.25) < 0.00001, before["buy_volume"]
        user_before = conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0]
        bank_before = conn.execute("SELECT balance FROM bank_accounts WHERE user_id=101 AND account_type='primary'").fetchone()[0]
        holdings_before = conn.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=101 AND symbol='FLX'").fetchone()
        conn.execute("UPDATE crypto_market SET updated_at=0 WHERE symbol='FLX'")
        conn.commit(); conn.close()
        asyncio.run(CryptoMixin21.crypto_price_loop.coro(cog))
        conn = cog.connect()
        after = conn.execute("SELECT price,buy_volume,updated_at FROM crypto_market WHERE symbol='FLX'").fetchone()
        assert after["price"] > 0 and after["price"] != before["price"], (before["price"], after["price"])
        assert after["buy_volume"] == 0, after["buy_volume"]
        assert after["updated_at"] > 0
        assert conn.execute("SELECT wallet FROM economy_users WHERE user_id=101").fetchone()[0] == user_before
        assert conn.execute("SELECT balance FROM bank_accounts WHERE user_id=101 AND account_type='primary'").fetchone()[0] == bank_before
        holdings_after = conn.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=101 AND symbol='FLX'").fetchone()
        assert tuple(holdings_after) == tuple(holdings_before)
        assert conn.execute("SELECT value FROM lude_schema_meta WHERE key='money_unit'").fetchone()[0] == "cents_v3"
        conn.close()
        asyncio.run(bot.close())
    config.DB_PATH = original_path
    print("OK: Market Engine 2.1 live algorithm, INT$-scaled flow, no wallet/holding mutation")


if __name__ == "__main__":
    run()
