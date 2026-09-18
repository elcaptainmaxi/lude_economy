"""Validación local y no destructiva del refactor de Lude Economy."""

import asyncio
import os
import tempfile

import discord
from discord.ext import commands

from lude import config
from lude.core import LudeEconomy, setup
from lude.views import LudeAdminPanel, LudeNavigator


EXPECTED_COMMANDS = {
    "lude panel", "lude estado", "lude trabajos", "lude empleo", "lude work",
    "lude banco", "lude depositar", "lude retirar", "lude transferir",
    "lude mejorar-banco", "lude abrir-adicional", "lude mover-banco",
    "lude historial", "lude deuda", "lude pagar-deuda", "lude fianza",
    "lude crime", "lude rob", "lude slots", "lude blackjack", "lude ruleta",
    "lude coinflip", "lude crypto mercado", "lude crypto comprar",
    "lude crypto vender", "lude crypto cartera", "lude admin listar",
    "lude admin ver", "lude admin cambiar", "lude admin restaurar",
    "lude admin panel", "lude admin historial",
}

EXPECTED_TABLES = {
    "economy_users", "job_progress", "bank_accounts", "bank_history",
    "economy_settings", "economy_admin_audit", "casino_state", "crypto_market",
    "crypto_holdings", "crypto_history", "crypto_engine_state", "crypto_global_state",
}


class FakeTree:
    def __init__(self):
        self.synced_guild = None

    async def sync(self, *, guild):
        self.synced_guild = guild.id


class FakeBot:
    def __init__(self):
        self.tree = FakeTree()
        self.cog = None

    async def add_cog(self, cog):
        self.cog = cog

    async def wait_until_ready(self):
        return None


async def validate_setup():
    bot = FakeBot()
    await setup(bot)
    assert isinstance(bot.cog, LudeEconomy)
    assert bot.tree.synced_guild == config.GUILD_ID


async def validate_real_registration():
    bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
    cog = LudeEconomy(bot)
    await bot.add_cog(cog)
    guild = discord.Object(id=config.GUILD_ID)
    root = bot.tree.get_command("lude", guild=guild)
    assert root is not None
    assert len([command for command in bot.tree.get_commands(guild=guild) if command.name == "lude"]) == 1
    await bot.remove_cog("LudeEconomy")
    await bot.close()


async def validate_views(cog):
    assert len(LudeNavigator(cog, 42).children) == 5
    assert len(LudeAdminPanel(cog, config.ADMIN_OWNER_ID).children) >= 7


def main():
    handle, path = tempfile.mkstemp(prefix="lude-validation-", suffix=".db")
    os.close(handle)
    os.unlink(path)
    previous_path = config.DB_PATH
    config.DB_PATH = path
    try:
        bot = commands.Bot(command_prefix="!", intents=discord.Intents.none())
        cog = LudeEconomy(bot)

        assert config.GUILD_ID == 1545821075525603358
        assert config.ADMIN_OWNER_ID == 1006704642618568735
        assert config.CRYPTO_UP_EMOJI_ID == 1550285735305941022
        assert config.CRYPTO_DOWN_EMOJI_ID == 1550285765584625845

        assert len(LudeEconomy.__cog_app_commands__) == 1
        assert LudeEconomy.__cog_app_commands__[0].name == "lude"
        commands_found = {
            command.qualified_name
            for command in cog.lude.walk_commands()
            if not isinstance(command, discord.app_commands.Group)
        }
        assert commands_found == EXPECTED_COMMANDS, (commands_found ^ EXPECTED_COMMANDS)
        assert all(
            command.binding is cog
            for command in cog.lude.walk_commands()
            if not isinstance(command, discord.app_commands.Group)
        )

        conn = cog.connect()
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == EXPECTED_TABLES, tables ^ EXPECTED_TABLES
        conn.execute(
            "INSERT INTO economy_users(user_id, wallet, created_at) VALUES(?, ?, ?)",
            (42, 123_456, 1),
        )
        conn.execute(
            "INSERT INTO bank_accounts(user_id, account_type, level, balance) VALUES(?, 'primary', 3, ?)",
            (42, 45_678),
        )
        conn.execute(
            "INSERT INTO crypto_holdings(user_id, symbol, quantity, cost_basis) VALUES(?, 'IC', ?, ?)",
            (42, 2.5, 2_000),
        )
        conn.commit(); conn.close()

        cog.init_db()
        conn = cog.connect()
        user = conn.execute("SELECT wallet FROM economy_users WHERE user_id = 42").fetchone()
        bank = conn.execute("SELECT level, balance FROM bank_accounts WHERE user_id = 42 AND account_type = 'primary'").fetchone()
        holding = conn.execute("SELECT quantity, cost_basis FROM crypto_holdings WHERE user_id = 42 AND symbol = 'IC'").fetchone()
        assert user["wallet"] == 123_456
        assert (bank["level"], bank["balance"]) == (3, 45_678)
        assert (holding["quantity"], holding["cost_basis"]) == (2.5, 2_000)
        conn.close()

        portfolio = cog.build_portfolio_embed(42)
        market = cog.build_market_embed()
        overview = cog.build_overview_embed(42)
        assert "Ganancia no realizada" in (portfolio.description or "")
        assert "Precio promedio" in portfolio.fields[0].value
        assert "Comisión de venta estimada" in portfolio.fields[0].value
        assert all("Régimen" in field.value and "Próximo tick" in field.value for field in market.fields)
        assert any(field.name == "⏱️ Actividades" for field in overview.fields)
        asyncio.run(validate_views(cog))

        original = config.setting_display_value(config.SETTING_SPECS["work.cooldown_min"])
        cog.update_runtime_setting("work.cooldown_min", original + 1, config.ADMIN_OWNER_ID)
        cog.reset_runtime_setting("work.cooldown_min", config.ADMIN_OWNER_ID)
        conn = cog.connect()
        audit_count = conn.execute("SELECT COUNT(*) FROM economy_admin_audit").fetchone()[0]
        override_count = conn.execute("SELECT COUNT(*) FROM economy_settings").fetchone()[0]
        conn.close()
        assert audit_count == 2
        assert override_count == 0
        assert config.setting_display_value(config.SETTING_SPECS["work.cooldown_min"]) == original

        asyncio.run(validate_setup())
        asyncio.run(validate_real_registration())
        print(f"OK: {len(commands_found)} comandos, {len(tables)} tablas, setup, registro único y migración aditiva")
    finally:
        config.DB_PATH = previous_path
        if os.path.exists(path):
            os.unlink(path)


if __name__ == "__main__":
    main()
