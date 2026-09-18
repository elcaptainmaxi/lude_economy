import random

import discord
from discord import app_commands

from . import config
from .groups import lude
from .utils import money
from .views import BlackjackView, CoinflipView


class CasinoMixin:
    def credit_casino_return(self, user_id: int, stake: int, total_return: int) -> tuple[int, int]:
        self.ensure_user(user_id)
        total_return = max(0, int(total_return))
        net_gain = max(0, total_return - int(stake))
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            withheld = 0
            if net_gain > 0:
                debt = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()["judicial_debt"]
                withheld = min(int(debt), int(round(net_gain * config.JUDICIAL_RATE)))
                if withheld:
                    cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (withheld, user_id))
            credited = total_return - withheld
            if credited:
                cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (credited, user_id))
            conn.commit(); conn.close()
            return credited, withheld

    def resolve_coinflip(self, creator_id: int, opponent_id: int, bet: int, creator_choice: str) -> dict:
        self.ensure_user(creator_id); self.ensure_user(opponent_id)
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            creator_wallet = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (creator_id,)).fetchone()["wallet"]
            opponent_wallet = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (opponent_id,)).fetchone()["wallet"]
            if creator_wallet < bet:
                conn.rollback(); conn.close()
                return {"ok": False, "message": "El creador ya no tiene suficiente Wallet para cubrir la apuesta."}
            if opponent_wallet < bet:
                conn.rollback(); conn.close()
                return {"ok": False, "message": "No tienes suficiente Wallet para cubrir la apuesta."}
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id IN (?, ?)", (bet, creator_id, opponent_id))
            conn.commit(); conn.close()
        result = random.choice(["cara", "cruz"])
        winner_id = creator_id if result == creator_choice else opponent_id
        pool = bet * 2
        fee = max(1, int(round(pool * config.COINFLIP_FEE_RATE)))
        credited, withheld = self.credit_casino_return(winner_id, bet, pool - fee)
        return {
            "ok": True, "result": "Cara" if result == "cara" else "Cruz", "winner_id": winner_id,
            "pool": pool, "fee": fee, "credited": credited, "withheld": withheld,
        }

    @lude.command(name="slots", description="Apuesta en Slots. Una parte alimenta el Jackpot Global.")
    async def slots(self, interaction: discord.Interaction, apuesta: int):
        uid = interaction.user.id
        if apuesta < config.CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(config.CASINO_MIN_BET)}**.", ephemeral=False)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=False)
            return
        symbols = list(config.SLOTS_SYMBOL_WEIGHTS.keys())
        weights = [config.SLOTS_SYMBOL_WEIGHTS[symbol] for symbol in symbols]
        if sum(weights) <= 0:
            await interaction.response.send_message("Slots está temporalmente deshabilitado por configuración administrativa.", ephemeral=False)
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (apuesta, uid)); conn.commit(); conn.close()
            return
        reels = random.choices(symbols, weights=weights, k=3)
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            jackpot = float(cur.execute("SELECT value FROM casino_state WHERE key = 'slots_jackpot'").fetchone()["value"])
            contribution = max(1, int(round(apuesta * config.SLOTS_JACKPOT_CONTRIBUTION)))
            jackpot += contribution
            cur.execute("UPDATE casino_state SET value = ? WHERE key = 'slots_jackpot'", (jackpot,))
            conn.commit(); conn.close()
        total_return, result_name = 0, "Sin premio"
        if reels == ["7️⃣", "7️⃣", "7️⃣"]:
            total_return = apuesta + int(round(jackpot)); result_name = "🎉 JACKPOT GLOBAL"
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE casino_state SET value = ? WHERE key = 'slots_jackpot'", (config.SLOTS_JACKPOT_BASE,)); conn.commit(); conn.close()
        elif reels[0] == reels[1] == reels[2] == "💎":
            total_return = int(round(apuesta * config.SLOTS_PAYOUTS["diamond_triple"]))
            result_name = f"💎 ×{config.SLOTS_PAYOUTS['diamond_triple']:g}"
        elif reels[0] == reels[1] == reels[2] == "🔔":
            total_return = int(round(apuesta * config.SLOTS_PAYOUTS["bell_triple"]))
            result_name = f"🔔 ×{config.SLOTS_PAYOUTS['bell_triple']:g}"
        elif reels[0] == reels[1] == reels[2] == "🍋":
            total_return = int(round(apuesta * config.SLOTS_PAYOUTS["lemon_triple"]))
            result_name = f"🍋 ×{config.SLOTS_PAYOUTS['lemon_triple']:g}"
        elif reels[0] == reels[1] == reels[2] == "🍒":
            total_return = int(round(apuesta * config.SLOTS_PAYOUTS["cherry_triple"]))
            result_name = f"🍒 ×{config.SLOTS_PAYOUTS['cherry_triple']:g}"
        elif reels.count("🍒") >= 2:
            total_return = int(round(apuesta * config.SLOTS_PAYOUTS["cherry_pair"]))
            result_name = f"🍒🍒 ×{config.SLOTS_PAYOUTS['cherry_pair']:g}"
        credited, withheld = (0, 0)
        if total_return:
            credited, withheld = self.credit_casino_return(uid, apuesta, total_return)
        embed = discord.Embed(title="🎰 Slots", description=" │ ".join(reels), color=config.COLOR_GOLD)
        embed.add_field(name="Resultado", value=result_name, inline=False)
        embed.add_field(name="Apuesta", value=money(apuesta), inline=True)
        embed.add_field(name="Acreditado", value=money(credited), inline=True)
        if withheld:
            embed.add_field(name="⚖️ Retención judicial", value=money(withheld), inline=True)
        with self.db_lock:
            conn = self.connect(); current_jackpot = conn.execute("SELECT value FROM casino_state WHERE key = 'slots_jackpot'").fetchone()["value"]; conn.close()
        embed.set_footer(text=f"Jackpot actual: {money(current_jackpot)}")
        await interaction.response.send_message(embed=embed)

    @lude.command(name="blackjack", description="Juega Blackjack contra el dealer.")
    async def blackjack(self, interaction: discord.Interaction, apuesta: int):
        uid = interaction.user.id
        if apuesta < config.CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(config.CASINO_MIN_BET)}**.", ephemeral=False)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=False)
            return
        view = BlackjackView(self, uid, apuesta)
        if view.is_natural(view.player) or view.is_natural(view.dealer):
            await interaction.response.send_message(embed=view.embed(), view=view)
            view.message = await interaction.original_response()
            await view.finish()
            return
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.message = await interaction.original_response()

    @lude.command(name="ruleta", description="Ruleta simple: Rojo, Negro o Verde.")
    @app_commands.choices(color=[
        app_commands.Choice(name="🔴 Rojo", value="red"),
        app_commands.Choice(name="⚫ Negro", value="black"),
        app_commands.Choice(name="🟢 Verde (0)", value="green"),
    ])
    async def ruleta(self, interaction: discord.Interaction, apuesta: int, color: app_commands.Choice[str]):
        uid = interaction.user.id
        if apuesta < config.CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(config.CASINO_MIN_BET)}**.", ephemeral=False)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=False)
            return
        red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
        number = random.randint(0, 36)
        result_color = "green" if number == 0 else ("red" if number in red_numbers else "black")
        won = color.value == result_color
        multiplier = config.ROULETTE_GREEN_RETURN if color.value == "green" else config.ROULETTE_EVEN_RETURN
        total_return = int(round(apuesta * multiplier)) if won else 0
        credited, withheld = self.credit_casino_return(uid, apuesta, total_return) if won else (0, 0)
        names = {"red": "🔴 Rojo", "black": "⚫ Negro", "green": "🟢 Verde"}
        embed = discord.Embed(title="🎡 Ruleta", color=config.COLOR_GOLD)
        embed.description = f"La ruleta cayó en **{number} · {names[result_color]}**."
        embed.add_field(name="Tu apuesta", value=f"{names[color.value]} · {money(apuesta)}", inline=True)
        embed.add_field(name="Resultado", value=f"✅ {money(credited)}" if won else "❌ Perdiste", inline=True)
        if withheld:
            embed.add_field(name="⚖️ Retención judicial", value=money(withheld), inline=True)
        await interaction.response.send_message(embed=embed)

    @lude.command(name="coinflip", description="Desafía a otro usuario a un Coinflip PvP 50/50.")
    @app_commands.choices(eleccion=[
        app_commands.Choice(name="Cara", value="cara"),
        app_commands.Choice(name="Cruz", value="cruz"),
    ])
    async def coinflip(self, interaction: discord.Interaction, usuario: discord.Member, apuesta: int, eleccion: app_commands.Choice[str]):
        if usuario.bot or usuario.id == interaction.user.id:
            await interaction.response.send_message("Debes desafiar a otro usuario real.", ephemeral=False)
            return
        if apuesta < config.CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(config.CASINO_MIN_BET)}**.", ephemeral=False)
            return
        creator, opponent = self.get_user(interaction.user.id), self.get_user(usuario.id)
        if creator["wallet"] < apuesta:
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=False); return
        if opponent["wallet"] < apuesta:
            await interaction.response.send_message(f"{usuario.mention} no tiene suficiente Wallet para aceptar esa apuesta.", ephemeral=False); return
        view = CoinflipView(self, interaction.user.id, usuario.id, apuesta, eleccion.value)
        embed = discord.Embed(title="🪙 Desafío Coinflip PvP", color=config.COLOR_GOLD)
        embed.description = (
            f"{interaction.user.mention} desafía a {usuario.mention}.\nApuesta por jugador: **{money(apuesta)}**\n"
            f"{interaction.user.mention} eligió **{eleccion.name}**.\nComisión del casino: **{config.COINFLIP_FEE_RATE * 100:g}% del pozo**."
        )
        embed.set_footer(text="El desafío expira en 60 segundos. El dinero se descuenta solo al aceptar.")
        await interaction.response.send_message(content=usuario.mention, embed=embed, view=view)
        view.message = await interaction.original_response()
