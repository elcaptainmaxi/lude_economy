import math
import random
import time

import discord

from . import config
from .groups import lude
from .utils import format_seconds, money, rob_bail_multiplier
from .views import ProtectionOfferView


class CrimeMixin:
    def buy_rob_protection(self, user_id: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        now = int(time.time())
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            user = cur.execute(
                "SELECT wallet, judicial_debt, protection_until FROM economy_users WHERE user_id = ?", (user_id,)
            ).fetchone()
            if user["protection_until"] > now:
                conn.rollback(); conn.close()
                return False, f"Ya tienes protección activa hasta <t:{user['protection_until']}:R>."
            surcharge = min(int(user["judicial_debt"]), int(round(config.ROB_PROTECTION_COST * config.JUDICIAL_RATE)))
            total = config.ROB_PROTECTION_COST + surcharge
            if user["wallet"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en Wallet para comprar la protección."
            until = now + config.ROB_PROTECTION_SECONDS
            cur.execute(
                "UPDATE economy_users SET wallet = wallet - ?, judicial_debt = judicial_debt - ?, protection_until = ? WHERE user_id = ?",
                (total, surcharge, until, user_id),
            )
            conn.commit(); conn.close()
            text = f"🛡️ Protección activada por **{format_seconds(config.ROB_PROTECTION_SECONDS)}**. Costo: **{money(config.ROB_PROTECTION_COST)}**."
            if surcharge:
                text += f" Recargo judicial: **{money(surcharge)}**."
            return True, text

    @lude.command(name="crime", description="Comete un crimen aleatorio contra el sistema.")
    async def crime(self, interaction: discord.Interaction):
        uid = interaction.user.id
        user = self.get_user(uid)
        if user["arrested"]:
            await interaction.response.send_message("🚔 Estás arrestado. Debes pagar tu fianza antes de cometer otro crimen.", ephemeral=False)
            return
        now = int(time.time())
        remaining = config.CRIME_COOLDOWN - (now - user["last_crime_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a usar `/lude crime` en **{format_seconds(remaining)}**.", ephemeral=False)
            return
        keys = list(config.CRIME_CATEGORIES)
        category_key = random.choices(keys, weights=[config.CRIME_CATEGORIES[key]["weight"] for key in keys], k=1)[0]
        category = config.CRIME_CATEGORIES[category_key]
        crime_name = random.choice(category["crimes"])
        salary = self.salary_reference(uid)
        with self.db_lock:
            conn = self.connect(); conn.execute("UPDATE economy_users SET last_crime_at = ? WHERE user_id = ?", (now, uid)); conn.commit(); conn.close()
        success = random.random() < category["success"]
        embed = discord.Embed(title=f"🚨 {crime_name}", color=config.COLOR_DANGER)
        embed.add_field(name="Categoría", value=category["name"], inline=True)
        embed.add_field(name="Salario de referencia", value=money(salary), inline=True)
        if success:
            reward = max(1, int(round(salary * random.uniform(*category["reward"]))))
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (reward, uid)); conn.commit(); conn.close()
            embed.description = f"✅ **El crimen salió bien.** Ganaste **{money(reward)}** en efectivo."
            embed.set_footer(text="Los ingresos de crime no sufren retención de Bank of Interlude.")
        else:
            fine = max(1, int(round(salary * random.uniform(*category["fine"]))))
            penalty = self.collect_penalty(uid, fine)
            arrested = random.random() < category["arrest_if_fail"]
            embed.description = f"❌ **El crimen fracasó.** Multa: **{money(fine)}**."
            if penalty["debt"]:
                embed.description += f"\n⚖️ **{money(penalty['debt'])}** de la multa pasó a Deuda Judicial por falta de fondos."
            if arrested:
                bail = max(1, int(round(salary * category["bail"])))
                self.arrest_user(uid, bail)
                embed.description += f"\n🚔 Además, fuiste **arrestado**. Fianza: **{money(bail)}**. Usa `/lude fianza`."
            else:
                embed.description += "\n🏃 Lograste evitar el arresto."
        await interaction.response.send_message(embed=embed)

    @lude.command(name="rob", description="Intenta robar una parte aleatoria del Wallet de otro usuario.")
    async def rob(self, interaction: discord.Interaction, usuario: discord.Member):
        thief_id, victim_id = interaction.user.id, usuario.id
        if usuario.bot or victim_id == thief_id:
            await interaction.response.send_message("Debes elegir a otro usuario real.", ephemeral=False)
            return
        thief, victim = self.get_user(thief_id), self.get_user(victim_id)
        if thief["arrested"]:
            await interaction.response.send_message("🚔 Estás arrestado. No puedes robar hasta pagar tu fianza.", ephemeral=False)
            return
        now = int(time.time())
        remaining = config.ROB_COOLDOWN - (now - thief["last_rob_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a robar en **{format_seconds(remaining)}**.", ephemeral=False)
            return
        if victim["protection_until"] > now:
            theft_percent = random.randint(int(config.ROB_THEFT_MIN_PERCENT), int(config.ROB_THEFT_MAX_PERCENT))
            bail = max(1, int(round(self.salary_reference(thief_id) * rob_bail_multiplier(theft_percent))))
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET last_rob_at = ? WHERE user_id = ?", (now, thief_id)); conn.commit(); conn.close()
            self.arrest_user(thief_id, bail)
            await interaction.response.send_message(f"🛡️ {usuario.mention} tenía **protección anti-robo activa**.\n🚔 Fuiste arrestado automáticamente. Fianza: **{money(bail)}**.")
            return
        min_wallet = int(round(self.salary_reference(victim_id) * config.ROB_MIN_WALLET_SALARY_MULTIPLIER))
        if victim["wallet"] < min_wallet:
            await interaction.response.send_message(
                f"💸 {usuario.mention} no puede ser robado ahora. Debe llevar al menos **{money(min_wallet)}** en Wallet.\nTu cooldown **no fue consumido**.",
                ephemeral=False,
            )
            return
        theft_percent = random.randint(int(config.ROB_THEFT_MIN_PERCENT), int(config.ROB_THEFT_MAX_PERCENT))
        success_chance = 100 if theft_percent == 1 else 100 - theft_percent
        attempted = max(1, int(math.floor(victim["wallet"] * theft_percent / 100)))
        with self.db_lock:
            conn = self.connect(); conn.execute("UPDATE economy_users SET last_rob_at = ? WHERE user_id = ?", (now, thief_id)); conn.commit(); conn.close()
        success = random.randint(1, 100) <= success_chance
        embed = discord.Embed(title="🔫 Intento de robo", color=config.COLOR_DANGER)
        embed.add_field(name="Objetivo", value=usuario.mention, inline=True)
        embed.add_field(name="Intento", value=f"{theft_percent}% · {money(attempted)}", inline=True)
        embed.add_field(name="Chance de éxito", value=f"{success_chance}%", inline=True)
        if success:
            with self.db_lock:
                conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                current_victim = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (victim_id,)).fetchone()["wallet"]
                actual = min(attempted, int(current_victim))
                if actual <= 0:
                    conn.rollback(); conn.close()
                    await interaction.response.send_message("El Wallet de la víctima cambió antes de resolver el robo.", ephemeral=False)
                    return
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (actual, victim_id))
                cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (actual, thief_id))
                conn.commit(); conn.close()
            embed.description = f"✅ Robo exitoso. <@{thief_id}> robó **{money(actual)}**."
            view = ProtectionOfferView(self, victim_id)
            await interaction.response.send_message(content=usuario.mention, embed=embed, view=view)
        else:
            fine = max(1, int(round(attempted * config.ROB_FAIL_FINE_RATE)))
            penalty = self.collect_penalty(thief_id, fine)
            protection_until = now + config.ROB_PROTECTION_SECONDS
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET protection_until = ? WHERE user_id = ?", (protection_until, victim_id)); conn.commit(); conn.close()
            embed.description = (
                f"❌ El robo falló. <@{thief_id}> fue multado con **{money(fine)}**.\n"
                f"🛡️ {usuario.mention} recibió **{format_seconds(config.ROB_PROTECTION_SECONDS)} de protección gratis**."
            )
            if penalty["debt"]:
                embed.description += f"\n⚖️ **{money(penalty['debt'])}** de la multa pasó a Deuda Judicial."
            await interaction.response.send_message(embed=embed)
