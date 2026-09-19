import threading

import discord
from discord.ext import commands

from . import config, utils
from .admin import AdminMixin
from .bank import BankMixin
from .casino import CasinoMixin
from .crime import CrimeMixin
from .crypto_21_bridge import CryptoMixin21
from .database import DatabaseMixin
from .embeds import EmbedsMixin
from .groups import admin_group, crypto_group, lude
from .jobs import JobsMixin
from .money_runtime_v3 import activate, has_cents_schema

# Replace the old whole-INT$ slash handlers with v3 cent-aware commands.
# /lude estado is consolidated into the richer /lude panel to respect
# Discord's limit of 25 direct subcommands per application-command group.
for _name in ("depositar", "retirar", "transferir", "mover-banco", "historial",
              "slots", "blackjack", "ruleta", "coinflip", "pagar-deuda", "estado"):
    lude.remove_command(_name)
for _name in ("comprar", "vender"):
    crypto_group.remove_command(_name)

from .v3_features import FullV3Mixin  # noqa: E402
from .v3_casino import CasinoCommandsV3  # noqa: E402


class LudeEconomy(
    FullV3Mixin, CasinoCommandsV3, DatabaseMixin, AdminMixin, EmbedsMixin,
    JobsMixin, BankMixin, CrimeMixin, CasinoMixin, CryptoMixin21, commands.Cog,
):
    """Single v3 cog; refuses old-unit DBs rather than silently corrupting balances."""

    lude = lude
    crypto_group = crypto_group
    admin_group = admin_group

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_lock = threading.RLock()
        self.active_work_users: set[int] = set()
        self.bank_reservations: dict[int, int] = {}
        # A copy must be migrated offline and explicitly installed while stopped.
        conn = self.connect()
        try:
            if not has_cents_schema(conn):
                raise RuntimeError("Lude v3 requiere una base migrada a cents_v3. No se modificó ningún saldo. Restaurá el bot anterior hasta completar la migración offline.")
        finally:
            conn.close()
        activate(config, utils)
        self.v3_active = True
        self.init_db()
        with self.db_lock:
            conn = self.connect()
            try:
                conn.execute("""CREATE TABLE IF NOT EXISTS crypto_sale_receipts (
                    operation_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL, credited_cents INTEGER NOT NULL,
                    created_at INTEGER NOT NULL)""")
                conn.commit()
            finally:
                conn.close()
        self.load_runtime_settings()

    async def cog_load(self):
        if not self.crypto_price_loop.is_running():
            self.crypto_price_loop.start()

    def cog_unload(self):
        self.crypto_price_loop.cancel()

    def salary_reference(self, user_id: int) -> int:
        user = self.get_user(user_id)
        job = config.JOBS.get(user["current_job"], config.JOBS["changas"])
        low, high = job["salary"]
        return int(round((low + high) / 2))

    def apply_income_withholding(self, cur, user_id: int, gross_income: int) -> tuple[int, int]:
        row = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
        debt = int(row["judicial_debt"])
        if debt <= 0 or gross_income <= 0:
            return gross_income, 0
        from .money_v3 import decimal, round_cents
        withheld = min(debt, round_cents(decimal(gross_income) / 100 * decimal(config.JUDICIAL_RATE)))
        cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (withheld, user_id))
        return gross_income - withheld, withheld

    def purchase_surcharge(self, cur, user_id: int, base_price: int) -> int:
        row = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
        debt = int(row["judicial_debt"])
        if debt <= 0:
            return 0
        from .money_v3 import decimal, round_cents
        return min(debt, round_cents(decimal(base_price) / 100 * decimal(config.JUDICIAL_RATE)))

    def try_debit_wallet(self, user_id: int, amount: int) -> bool:
        self.ensure_user(user_id)
        if amount <= 0:
            return False
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                row = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
                if row["wallet"] < amount:
                    return False
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))
                conn.commit()
                return True
            finally:
                conn.close()

    def collect_penalty(self, user_id: int, amount: int) -> dict:
        """Collect Wallet -> Primary -> Judicial Debt, all in integer cents."""
        self.ensure_user(user_id)
        amount = max(0, int(amount))
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                user = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
                bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (user_id,)).fetchone()
                remaining = amount
                from_wallet = min(int(user["wallet"]), remaining)
                if from_wallet:
                    cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (from_wallet, user_id))
                    remaining -= from_wallet
                from_bank = min(int(bank["balance"]), remaining)
                if from_bank:
                    new_balance = int(bank["balance"]) - from_bank
                    cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (new_balance, user_id))
                    self.log_bank(cur, user_id, "primary", "judicial_penalty", from_bank, new_balance, "Cobro de multa judicial")
                    remaining -= from_bank
                if remaining:
                    from .money_v3 import safe_add
                    current_debt = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id=?", (user_id,)).fetchone()[0]
                    cur.execute("UPDATE economy_users SET judicial_debt=? WHERE user_id=?", (safe_add(current_debt, remaining), user_id))
                conn.commit()
                return {"wallet": from_wallet, "bank": from_bank, "debt": remaining}
            finally:
                conn.close()

    def arrest_user(self, user_id: int, bail: int):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            try:
                conn.execute("UPDATE economy_users SET arrested = 1, bail_due = ? WHERE user_id = ?", (max(100, int(bail)), user_id))
                conn.commit()
            finally:
                conn.close()

    def is_arrested(self, user_id: int) -> bool:
        return bool(self.get_user(user_id)["arrested"])

    @lude.command(name="panel", description="Tu economía, inversiones y cooldowns en un solo panel.")
    async def panel(self, interaction: discord.Interaction):
        await self.show_qol(interaction, "panel")


async def setup(bot: commands.Bot):
    cog = LudeEconomy(bot)
    await bot.add_cog(cog)
    try:
        await bot.tree.sync(guild=discord.Object(id=config.GUILD_ID))
    except discord.HTTPException as exc:
        print(f"[LudeEconomy] No se pudo sincronizar /lude: {exc}")
