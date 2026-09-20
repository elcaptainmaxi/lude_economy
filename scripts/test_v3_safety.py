"""Offline regression checks for the complete Lude cents-v3 release."""
from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import threading
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import discord
from discord.ext import commands

from lude import config
from lude.database import DatabaseMixin
from lude.migrate_money_v3 import migrate_copy
from lude.money_v3 import cents, quote_net_sale, quote_sale


class Fixture(DatabaseMixin):
    def __init__(self):
        self.db_lock = threading.RLock()
        self.bank_reservations = {}


class Response:
    def __init__(self):
        self.text = None
        self.embed = None

    async def send_message(self, content=None, *, embed=None, ephemeral=False, **kwargs):
        self.text, self.embed = content, embed


class DummyInteraction:
    def __init__(self, user_id):
        self.user = type("FakeUser", (), {"id": user_id})()
        self.response = Response()


def check_quotes():
    # Exhaustively compare minimal achievable net to every smaller lot; this
    # catches gross-cent rounding discontinuities missed by naive binary search.
    quantum = Decimal("0.00000001")
    for price in ("0.01", "0.51", "1.99", "1234.5678"):
        for cost in (0, 100, 999999):
            kwargs = dict(symbol="IC", available_quantity=quantum * 300,
                          price=Decimal(price), cost_basis_cents=cost,
                          fee_rate=Decimal("0.01"), judicial_rate=Decimal("0.25"),
                          judicial_debt_cents=500, destination="savings")
            quotes = []
            for lot in range(1, 301):
                try:
                    quotes.append(quote_sale(quantity=quantum * lot, **kwargs))
                except ValueError:
                    continue
            if not quotes:
                continue
            targets = sorted({q.credited_cents for q in quotes})
            for target in targets:
                chosen = quote_net_sale(requested_cents=target, **kwargs)
                earlier = [q for q in quotes if q.credited_cents >= target]
                assert chosen.quantity == earlier[0].quantity, (price, cost, target, chosen, earlier[0])


def check_integration():
    previous_db = config.DB_PATH
    with tempfile.TemporaryDirectory(prefix="lude-v3-safety-") as directory:
        original = Path(directory) / "legacy.db"
        converted = Path(directory) / "converted.db"
        config.DB_PATH = str(original)
        fixture = Fixture()
        fixture.init_db()
        fixture.ensure_user(101)
        fixture.ensure_user(202)
        conn = fixture.connect()
        conn.execute("UPDATE economy_users SET wallet=200000,judicial_debt=1000 WHERE user_id=101")
        conn.execute("UPDATE bank_accounts SET level=7,balance=150000 WHERE user_id=101 AND account_type='primary'")
        conn.execute("INSERT INTO crypto_holdings(user_id,symbol,quantity,cost_basis) VALUES(101,'IC',25,100)")
        conn.commit(); conn.close()
        migrate_copy(str(original), str(converted))
        config.DB_PATH = str(converted)
        from lude.core import LudeEconomy
        from lude.v3_features import SaleConfirmationV3
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        cog = LudeEconomy(bot)

        async def check_registration():
            await bot.add_cog(cog)
            root = bot.tree.get_command("lude", guild=discord.Object(id=config.GUILD_ID))
            assert root is not None
            assert len(root.commands) <= 25
            assert root.get_command("mover-fondos") is not None
            assert root.get_command("ahorro") is not None
            assert root.get_command("crypto").get_command("vender") is not None
            await bot.remove_cog("LudeEconomy")
            await bot.close()

        asyncio.run(check_registration())
        bank_before = int(cog.get_bank(101, "savings")["balance"])
        with cog.db_lock:
            conn = cog.connect()
            try:
                quote, fingerprint, free = cog._quote_v3(conn.cursor(), 101, "IC", "units", "1", "savings")
            finally:
                conn.close()
        view = SaleConfirmationV3(cog, 101, "IC", "units", "1", "savings", quote, fingerprint)
        # A market update invalidates the pending confirmation. No balances or
        # positions should change as a result of the rejected confirmation.
        with cog.db_lock:
            conn = cog.connect()
            conn.execute("UPDATE crypto_market SET price=price+1 WHERE symbol='IC'")
            conn.commit(); conn.close()
        status, msg, repl = cog.execute_v3_sale(view)
        assert status == "error" and "Cambió" in msg, (status, msg)
        assert cog.get_bank(101, "savings")["balance"] == bank_before
        with cog.db_lock:
            conn = cog.connect()
            try:
                assert conn.execute("SELECT quantity FROM crypto_holdings WHERE user_id=101 AND symbol='IC'").fetchone()[0] == 25
                assert conn.execute("SELECT COUNT(*) FROM crypto_sale_receipts").fetchone()[0] == 0
            finally:
                conn.close()
        # Slots loss: only a single stake is debited, and the jackpot gets the
        # contribution in exact cents. No Discord network request is made.
        before_wallet = int(cog.get_user(101)["wallet"])
        before_debt = int(cog.get_user(101)["judicial_debt"])
        conn = cog.connect()
        before_jackpot = int(conn.execute("SELECT value FROM casino_state_cents WHERE key='slots_jackpot'").fetchone()[0])
        conn.close()
        interaction = DummyInteraction(101)
        with patch("lude.v3_casino.random.choices", return_value=["🍒", "🍋", "💎"]):
            asyncio.run(cog.slots_v3.callback(cog, interaction, "100,25"))
        assert interaction.response.embed is not None
        assert cog.get_user(101)["wallet"] == before_wallet - cents("100,25")
        assert cog.get_user(101)["judicial_debt"] == before_debt
        conn = cog.connect()
        after_jackpot = int(conn.execute("SELECT value FROM casino_state_cents WHERE key='slots_jackpot'").fetchone()[0])
        conn.close()
        assert after_jackpot >= before_jackpot
    config.DB_PATH = previous_db


if __name__ == "__main__":
    check_quotes()
    check_integration()
    print("OK: minimum-net quotes, stale-sale rejection, slots atomic debit and guild slash commands")
