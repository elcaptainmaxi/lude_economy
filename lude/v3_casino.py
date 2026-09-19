"""Decimal-input casino commands for cents_v3; retains existing gameplay views."""
from __future__ import annotations

import random
from decimal import Decimal

import discord
from discord import app_commands

from . import config
from .bank import BankMixin
from .casino import CasinoMixin
from .groups import lude
from .money_v3 import cents, decimal, format_cents, round_cents, safe_add
from .views import BlackjackView, CoinflipView


def parse_bet(value):
    try:
        return cents(value)
    except ValueError as exc:
        raise ValueError(f"❌ {exc}") from exc


class CasinoCommandsV3:
    @lude.command(name="slots", description="Jugá Slots apostando INT$ con centavos.")
    async def slots_v3(self, interaction: discord.Interaction, apuesta: str):
        try:
            bet = parse_bet(apuesta)
            if bet < config.CASINO_MIN_BET:
                raise ValueError(f"La apuesta mínima es {format_cents(config.CASINO_MIN_BET)}.")
            symbols = list(config.SLOTS_SYMBOL_WEIGHTS)
            weights = [config.SLOTS_SYMBOL_WEIGHTS[s] for s in symbols]
            if sum(weights) <= 0:
                raise ValueError("Slots está deshabilitado por configuración administrativa.")
            self.ensure_user(interaction.user.id)
            reels = random.choices(symbols, weights=weights, k=3)
            result_name = "Sin premio"
            with self.db_lock:
                conn = self.connect()
                try:
                    cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                    user = cur.execute("SELECT wallet,judicial_debt FROM economy_users WHERE user_id=?", (interaction.user.id,)).fetchone()
                    if int(user["wallet"]) < bet:
                        raise ValueError("No tenés suficiente dinero en Wallet.")
                    row = cur.execute("SELECT value FROM casino_state_cents WHERE key='slots_jackpot'").fetchone()
                    if row is None:
                        raise ValueError("Falta el jackpot monetario v3. No se descontó la apuesta.")
                    contribution = max(100, round_cents(Decimal(bet) / 100 * decimal(config.SLOTS_JACKPOT_CONTRIBUTION)))
                    jackpot = safe_add(int(row["value"]), contribution)
                    returned = 0
                    if reels == ["7️⃣", "7️⃣", "7️⃣"]:
                        returned = safe_add(bet, jackpot)
                        jackpot = int(config.SLOTS_JACKPOT_BASE)
                        result_name = "🎉 JACKPOT GLOBAL"
                    else:
                        match = {"💎": "diamond_triple", "🔔": "bell_triple", "🍋": "lemon_triple", "🍒": "cherry_triple"}
                        if reels[0] == reels[1] == reels[2] and reels[0] in match:
                            key = match[reels[0]]
                            returned = round_cents(Decimal(bet) / 100 * decimal(config.SLOTS_PAYOUTS[key]))
                            result_name = f"{reels[0]} ×{config.SLOTS_PAYOUTS[key]:g}"
                        elif reels.count("🍒") >= 2:
                            returned = round_cents(Decimal(bet) / 100 * decimal(config.SLOTS_PAYOUTS["cherry_pair"]))
                            result_name = "🍒🍒"
                    net_gain = max(0, returned - bet)
                    withheld = min(int(user["judicial_debt"]), round_cents(Decimal(net_gain) / 100 * decimal(config.JUDICIAL_RATE)))
                    credited = returned - withheld
                    new_wallet = safe_add(int(user["wallet"]) - bet, credited)
                    cur.execute("UPDATE economy_users SET wallet=?,judicial_debt=judicial_debt-? WHERE user_id=?",
                                (new_wallet, withheld, interaction.user.id))
                    cur.execute("UPDATE casino_state_cents SET value=? WHERE key='slots_jackpot'", (jackpot,))
                    conn.commit()
                finally:
                    conn.close()
            embed = discord.Embed(title="🎰 Slots", description=" │ ".join(reels), color=config.COLOR_GOLD)
            embed.add_field(name="Resultado", value=result_name, inline=False)
            embed.add_field(name="Apuesta", value=format_cents(bet), inline=True)
            embed.add_field(name="Acreditado", value=format_cents(credited), inline=True)
            if withheld:
                embed.add_field(name="⚖️ Retención judicial", value=format_cents(withheld), inline=True)
            embed.set_footer(text=f"Jackpot actual: {format_cents(jackpot)}")
            await interaction.response.send_message(embed=embed, ephemeral=False)
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)

    @lude.command(name="blackjack", description="Jugá Blackjack con apuestas de hasta dos decimales.")
    async def blackjack_v3(self, interaction: discord.Interaction, apuesta: str):
        try:
            bet = parse_bet(apuesta)
            if bet < config.CASINO_MIN_BET:
                raise ValueError(f"La apuesta mínima es {format_cents(config.CASINO_MIN_BET)}.")
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        await CasinoMixin.blackjack.callback(self, interaction, bet)

    @lude.command(name="ruleta", description="Jugá Ruleta con apuestas de hasta dos decimales.")
    @app_commands.choices(color=[app_commands.Choice(name="🔴 Rojo", value="red"),
                                app_commands.Choice(name="⚫ Negro", value="black"),
                                app_commands.Choice(name="🟢 Verde (0)", value="green")])
    async def ruleta_v3(self, interaction: discord.Interaction, apuesta: str, color: app_commands.Choice[str]):
        try:
            bet = parse_bet(apuesta)
            if bet < config.CASINO_MIN_BET:
                raise ValueError(f"La apuesta mínima es {format_cents(config.CASINO_MIN_BET)}.")
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        await CasinoMixin.ruleta.callback(self, interaction, bet, color)

    @lude.command(name="coinflip", description="Desafiá a otro usuario con una apuesta decimal.")
    @app_commands.choices(eleccion=[app_commands.Choice(name="Cara", value="cara"),
                                   app_commands.Choice(name="Cruz", value="cruz")])
    async def coinflip_v3(self, interaction: discord.Interaction, usuario: discord.Member,
                          apuesta: str, eleccion: app_commands.Choice[str]):
        try:
            bet = parse_bet(apuesta)
            if bet < config.CASINO_MIN_BET:
                raise ValueError(f"La apuesta mínima es {format_cents(config.CASINO_MIN_BET)}.")
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        await CasinoMixin.coinflip.callback(self, interaction, usuario, bet, eleccion)

    def resolve_coinflip(self, creator_id: int, opponent_id: int, bet: int, creator_choice: str) -> dict:
        """Deduct both stakes and credit the winner in the same transaction."""
        self.ensure_user(creator_id); self.ensure_user(opponent_id)
        result = random.choice(("cara", "cruz"))
        winner_id = creator_id if result == creator_choice else opponent_id
        pool = safe_add(bet, bet)
        fee = max(100, round_cents(Decimal(pool) / 100 * decimal(config.COINFLIP_FEE_RATE)))
        returned = pool - fee
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                wallets = {row["user_id"]: int(row["wallet"]) for row in cur.execute(
                    "SELECT user_id,wallet FROM economy_users WHERE user_id IN (?,?)", (creator_id, opponent_id))}
                if wallets[creator_id] < bet:
                    return {"ok": False, "message": "El creador ya no tiene suficiente Wallet para cubrir la apuesta."}
                if wallets[opponent_id] < bet:
                    return {"ok": False, "message": "No tenés suficiente Wallet para aceptar."}
                judicial = int(cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id=?", (winner_id,)).fetchone()[0])
                gain = max(0, returned - bet)
                withheld = min(judicial, round_cents(Decimal(gain) / 100 * decimal(config.JUDICIAL_RATE)))
                credited = returned - withheld
                new_creator = wallets[creator_id] - bet
                new_opponent = wallets[opponent_id] - bet
                if winner_id == creator_id:
                    new_creator = safe_add(new_creator, credited)
                else:
                    new_opponent = safe_add(new_opponent, credited)
                cur.execute("UPDATE economy_users SET wallet=? WHERE user_id=?", (new_creator, creator_id))
                cur.execute("UPDATE economy_users SET wallet=? WHERE user_id=?", (new_opponent, opponent_id))
                if withheld:
                    cur.execute("UPDATE economy_users SET judicial_debt=judicial_debt-? WHERE user_id=?", (withheld, winner_id))
                conn.commit()
                return {"ok": True, "result": "Cara" if result == "cara" else "Cruz", "winner_id": winner_id,
                        "pool": pool, "fee": fee, "credited": credited, "withheld": withheld}
            finally:
                conn.close()

    @lude.command(name="pagar-deuda", description="Pagá deuda judicial en INT$ con centavos.")
    @app_commands.choices(origen=[app_commands.Choice(name="Wallet", value="wallet"),
                                  app_commands.Choice(name="Cuenta Principal", value="bank")])
    async def pagar_deuda_v3(self, interaction: discord.Interaction, cantidad: str, origen: app_commands.Choice[str]):
        try:
            amount = parse_bet(cantidad)
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        await BankMixin.pagar_deuda.callback(self, interaction, amount, origen)
