"""End-to-end offline v3 integration; never uses a production database."""
import asyncio
import os
import sqlite3
import tempfile
import threading
from decimal import Decimal
from pathlib import Path

import discord
from discord.ext import commands

from lude import config
from lude.database import DatabaseMixin
from lude.migrate_money_v3 import migrate_copy
from lude.money_v3 import cents, format_cents


class LegacyFixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


def run():
    original_path = config.DB_PATH
    with tempfile.TemporaryDirectory(prefix="lude-v3-offline-") as folder:
        source, migrated = Path(folder) / "legacy.db", Path(folder) / "cents.db"
        config.DB_PATH = str(source)
        legacy = LegacyFixture()
        legacy.init_db()
        legacy.ensure_user(101)
        legacy.ensure_user(202)
        conn = legacy.connect()
        conn.execute("UPDATE economy_users SET wallet=12000,judicial_debt=100 WHERE user_id=101")
        conn.execute("UPDATE bank_accounts SET level=7,balance=30000 WHERE user_id=101 AND account_type='primary'")
        conn.execute("INSERT INTO crypto_holdings(user_id,symbol,quantity,cost_basis) VALUES (101,'FLX',500,1000)")
        conn.execute("UPDATE crypto_market SET price=50.1234 WHERE symbol='FLX'")
        conn.commit(); conn.close()
        copied = migrate_copy(str(source), str(migrated))
        assert copied["savings_accounts"] == 2
        config.DB_PATH = str(migrated)
        from lude.core import LudeEconomy
        from lude.v3_features import NavigatorV3, SaleConfirmationV3
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        cog = LudeEconomy(bot)
        assert cog.v3_active
        assert config.CASINO_MIN_BET == 5000, config.CASINO_MIN_BET
        assert config.JOBS["changas"]["salary"][0] >= 100
        assert format_cents(cog.get_user(101)["wallet"]) == "INT$ 12.000,00"
        assert cog.get_bank(101, "savings")["balance"] == 0
        ok, text = cog.v3_move(101, "wallet", "savings", cents("10.25"))
        assert ok, text
        assert cog.get_bank(101, "savings")["balance"] == 1025
        ok, text = cog.v3_move(101, "savings", "primary", cents("2.25"))
        assert ok, text
        assert cog.get_bank(101, "savings")["balance"] == 800
        ok, text = cog.v3_move(101, "savings", "wallet", cents("8"))
        assert ok, text
        assert cog.get_bank(101, "savings")["balance"] == 0
        with cog.db_lock:
            conn = cog.connect()
            try:
                count = conn.execute("SELECT COUNT(*) FROM bank_history WHERE user_id=101 AND action='internal_move'").fetchone()[0]
                assert count == 3, count
            finally:
                conn.close()
        ok, text = cog.crypto_buy(101, "FLX", cents("100.25"))
        assert ok, text
        with cog.db_lock:
            conn = cog.connect()
            try:
                holdings = conn.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=101 AND symbol='FLX'").fetchone()
                assert holdings["quantity"] > 500 and holdings["cost_basis_cents"] == 110025
                assert 100.24 <= conn.execute("SELECT buy_volume FROM crypto_market WHERE symbol='FLX'").fetchone()[0] <= 100.26
                quote, fingerprint, free = cog._quote_v3(conn.cursor(), 101, "FLX", "net", "7500,25", "savings")
                assert quote.credited_cents >= 750025 and free >= quote.credited_cents
            finally:
                conn.close()
        confirmation = SaleConfirmationV3(cog, 101, "FLX", "net", "7500,25", "savings", quote, fingerprint)
        result, message, alternative = cog.execute_v3_sale(confirmation)
        assert result == "success", (result, message)
        again, message, _ = cog.execute_v3_sale(confirmation)
        assert again == "error" and "ya fue" in message.lower(), (again, message)
        assert cog.get_bank(101, "savings")["balance"] == quote.credited_cents
        with cog.db_lock:
            conn = cog.connect()
            try:
                count = conn.execute("SELECT COUNT(*) FROM crypto_sale_receipts WHERE user_id=101").fetchone()[0]
                assert count == 1
                sell_volume = conn.execute("SELECT sell_volume FROM crypto_market WHERE symbol='FLX'").fetchone()[0]
                assert abs(sell_volume - quote.gross_cents / 100) < 0.01
                price = conn.execute("SELECT price FROM crypto_market WHERE symbol='FLX'").fetchone()[0]
                assert price == 50.1234
            finally:
                conn.close()
        nav = NavigatorV3(cog, 101, "mercado")
        assert len(nav.children) == 9
        assert len(nav.render().fields) <= 25
        nav.page = "cartera"; nav.index = 1
        assert "Ganancia no realizada" in nav.render().description
        assert not nav.sell.disabled
        assert len(cog.lude.get_command("crypto").get_command("comprar")._params) == 2
        assert len({command.qualified_name for command in cog.lude.walk_commands()
                    if not isinstance(command, discord.app_commands.Group)}) >= 33
        asyncio.run(bot.close())
    config.DB_PATH = original_path
    print("OK: v3 migrated cog, savings transfers, cent purchase, exact net sale, no double credit, market units, UI")


if __name__ == "__main__":
    run()
