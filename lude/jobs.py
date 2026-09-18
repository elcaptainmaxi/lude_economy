import math
import random
import time

import discord
from discord import app_commands

from . import config
from .groups import lude
from .utils import job_level_progress, money, work_level_from_xp, work_level_progress, format_seconds
from .views import WorkView


class JobsMixin:
    def settle_work(self, user_id: int, job_id: str, grade: str) -> dict:
        self.ensure_user(user_id)
        job = config.JOBS[job_id]
        base = random.randint(*job["salary"])
        gross = max(1, int(round(base * config.GRADE_MULTIPLIERS[grade])))
        work_xp_gain = max(1, int(round(random.randint(18, 30) * config.GRADE_XP_MULTIPLIERS[grade])))
        job_xp_gain = max(1, int(round(random.randint(15, 25) * config.GRADE_XP_MULTIPLIERS[grade])))
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            before = cur.execute("SELECT work_xp FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            old_work_level = work_level_from_xp(before["work_xp"])
            net, withheld = self.apply_income_withholding(cur, user_id, gross)
            destination = job["payment"]
            if destination == "bank":
                account = cur.execute(
                    "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                    (user_id,),
                ).fetchone()
                capacity = config.BANK_LEVELS[account["level"]]["capacity"]
                if account["balance"] + net > capacity:
                    cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (net, user_id))
                    destination = "wallet-fallback"
                else:
                    new_balance = int(account["balance"]) + net
                    cur.execute(
                        "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                        (new_balance, user_id),
                    )
                    self.log_bank(cur, user_id, "primary", "salary", net, new_balance, f"Salario: {job['name']}")
            else:
                cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (net, user_id))
            cur.execute("UPDATE economy_users SET work_xp = work_xp + ? WHERE user_id = ?", (work_xp_gain, user_id))
            cur.execute("INSERT OR IGNORE INTO job_progress(user_id, job_id, xp) VALUES(?, ?, 0)", (user_id, job_id))
            cur.execute("UPDATE job_progress SET xp = xp + ? WHERE user_id = ? AND job_id = ?", (job_xp_gain, user_id, job_id))
            after = cur.execute("SELECT work_xp FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            new_work_level = work_level_from_xp(after["work_xp"])
            job_xp = cur.execute("SELECT xp FROM job_progress WHERE user_id = ? AND job_id = ?", (user_id, job_id)).fetchone()["xp"]
            job_level, job_progress, job_needed = job_level_progress(job_xp)
            conn.commit(); conn.close()
        self.active_work_users.discard(user_id)
        self.bank_reservations.pop(user_id, None)
        return {
            "job": job, "grade": grade, "gross": gross, "net": net, "withheld": withheld,
            "work_xp_gain": work_xp_gain, "job_xp_gain": job_xp_gain,
            "old_work_level": old_work_level, "new_work_level": new_work_level,
            "job_level": job_level, "job_progress": job_progress, "job_needed": job_needed,
            "destination": destination,
        }

    def build_work_result_embed(self, result: dict, correct: bool, timeout: bool = False):
        grade = result["grade"]
        embed = discord.Embed(
            title=f"💼 Turno terminado · Nota {grade}",
            color=config.COLOR_SUCCESS if grade in {"S", "A", "B"} else config.COLOR_GOLD,
        )
        if timeout:
            embed.description = "⏱️ No respondiste a tiempo. El turno se calificó como **F**."
        else:
            embed.description = "✅ Buena decisión." if correct else "⚠️ La decisión no fue la mejor."
        destination_text = "Wallet" if result["destination"].startswith("wallet") else "Bank of Interlude"
        embed.add_field(name="Trabajo", value=result["job"]["name"], inline=False)
        embed.add_field(name="Salario bruto", value=money(result["gross"]), inline=True)
        embed.add_field(name="Recibiste", value=f"{money(result['net'])}\n→ {destination_text}", inline=True)
        if result["withheld"]:
            embed.add_field(name="⚖️ Deuda Judicial", value=f"-{money(result['withheld'])}", inline=True)
        embed.add_field(name="Work XP", value=f"+{result['work_xp_gain']}", inline=True)
        embed.add_field(name="Job XP", value=f"+{result['job_xp_gain']} · Job Lv. {result['job_level']}", inline=True)
        if result["new_work_level"] > result["old_work_level"]:
            embed.add_field(name="🎉 Subida de nivel", value=f"Work Level **{result['old_work_level']} → {result['new_work_level']}**", inline=False)
        if result["destination"] == "wallet-fallback":
            embed.set_footer(text="Tu banco se quedó sin capacidad durante el turno; el pago fue enviado a Wallet.")
        return embed

    @lude.command(name="estado", description="Muestra tu estado económico general.")
    async def estado(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        primary = self.get_bank(interaction.user.id, "primary")
        additional = self.get_bank(interaction.user.id, "additional")
        level, progress, needed = work_level_progress(user["work_xp"])
        job = config.JOBS.get(user["current_job"], config.JOBS["changas"])
        embed = discord.Embed(title="🏙️ Interlude · Estado económico", color=config.COLOR)
        embed.add_field(name="💵 Wallet", value=money(user["wallet"]), inline=True)
        embed.add_field(name="🏦 Banco", value=money(primary["balance"]), inline=True)
        embed.add_field(name="⚖️ Deuda Judicial", value=money(user["judicial_debt"]), inline=True)
        embed.add_field(name="💼 Trabajo", value=job["name"], inline=True)
        embed.add_field(name="📈 Work Level", value=f"{level} · {progress}/{needed if needed else 'MAX'} XP", inline=True)
        embed.add_field(name="🚔 Estado", value="Arrestado" if user["arrested"] else "Libre", inline=True)
        if additional:
            embed.add_field(name="🏦 Cuenta adicional", value=money(additional["balance"]), inline=True)
        if user["protection_until"] > int(time.time()):
            embed.add_field(name="🛡️ Protección", value=f"Activa hasta <t:{user['protection_until']}:R>", inline=True)
        await interaction.response.send_message(embed=embed)

    @lude.command(name="trabajos", description="Muestra los trabajos y cuáles tienes desbloqueados.")
    async def trabajos(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        level = work_level_from_xp(user["work_xp"])
        lines = []
        for job_id, job in sorted(config.JOBS.items(), key=lambda item: (item[1]["level"], item[1]["name"])):
            unlocked = level >= job["level"]
            current = " ⭐" if user["current_job"] == job_id else ""
            pay = "Banco" if job["payment"] == "bank" else "Wallet"
            icon = "✅" if unlocked else "🔒"
            lines.append(f"{icon} **Lv.{job['level']} · {job['name']}** — {money(job['salary'][0])}–{money(job['salary'][1])} · {pay}{current}")
        embed = discord.Embed(title=f"💼 Mercado laboral · Work Level {level}", description="\n".join(lines), color=config.COLOR)
        await interaction.response.send_message(embed=embed)

    @lude.command(name="empleo", description="Cambia a un trabajo que tengas desbloqueado.")
    async def empleo(self, interaction: discord.Interaction, trabajo: str):
        trabajo = trabajo.lower()
        if trabajo not in config.JOBS:
            await interaction.response.send_message("Trabajo inválido.", ephemeral=False)
            return
        user = self.get_user(interaction.user.id)
        level = work_level_from_xp(user["work_xp"])
        job = config.JOBS[trabajo]
        if level < job["level"]:
            await interaction.response.send_message(f"Necesitas Work Level **{job['level']}**.", ephemeral=False)
            return
        with self.db_lock:
            conn = self.connect()
            conn.execute("UPDATE economy_users SET current_job = ? WHERE user_id = ?", (trabajo, interaction.user.id))
            conn.execute("INSERT OR IGNORE INTO job_progress(user_id, job_id, xp) VALUES(?, ?, 0)", (interaction.user.id, trabajo))
            conn.commit(); conn.close()
        await interaction.response.send_message(f"💼 Ahora trabajas como **{job['name']}**.")

    @empleo.autocomplete("trabajo")
    async def empleo_autocomplete(self, interaction: discord.Interaction, current: str):
        member = interaction.user
        tester_role = interaction.guild.get_role(config.TESTER_ROLE_ID) if interaction.guild else None
        if not isinstance(member, discord.Member) or tester_role is None or member.top_role.position < tester_role.position:
            return []
        user = self.get_user(interaction.user.id)
        level = work_level_from_xp(user["work_xp"])
        current_lower = current.lower()
        results = []
        for job_id, job in config.JOBS.items():
            if job["level"] <= level and (current_lower in job_id.lower() or current_lower in job["name"].lower()):
                results.append(app_commands.Choice(name=f"{job['name']} · Lv.{job['level']}", value=job_id))
            if len(results) >= 25:
                break
        return results

    @lude.command(name="work", description="Trabaja y completa una decisión de tu profesión.")
    async def work(self, interaction: discord.Interaction):
        uid = interaction.user.id
        user = self.get_user(uid)
        if user["arrested"]:
            await interaction.response.send_message("🚔 Estás arrestado. Debes pagar tu fianza antes de trabajar.", ephemeral=False)
            return
        if uid in self.active_work_users:
            await interaction.response.send_message("Ya tienes un turno de trabajo activo.", ephemeral=False)
            return
        now = int(time.time())
        remaining = config.WORK_COOLDOWN - (now - user["last_work_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a trabajar en **{format_seconds(remaining)}**.", ephemeral=False)
            return
        job_id = user["current_job"]
        job = config.JOBS.get(job_id, config.JOBS["changas"])
        if job["payment"] == "bank":
            max_salary = int(math.ceil(job["salary"][1] * config.GRADE_MULTIPLIERS["S"]))
            if self.bank_free(uid, "primary", include_reservation=False) < max_salary:
                await interaction.response.send_message(
                    f"🏦 Este empleo paga por Bank of Interlude. Necesitas al menos **{money(max_salary)}** de capacidad libre en tu Cuenta Principal antes de iniciar el turno.",
                    ephemeral=False,
                )
                return
            self.bank_reservations[uid] = max_salary
        self.active_work_users.add(uid)
        with self.db_lock:
            conn = self.connect()
            conn.execute("UPDATE economy_users SET last_work_at = ? WHERE user_id = ?", (now, uid))
            conn.commit(); conn.close()
        prompt, options, correct = random.choice(config.WORK_MINIGAMES.get(job["style"], config.WORK_MINIGAMES["general"]))
        view = WorkView(self, uid, job_id, prompt, options, correct)
        embed = discord.Embed(title=f"💼 {job['name']} · Turno", description=prompt, color=config.COLOR)
        embed.set_footer(text="Tienes 30 segundos para decidir.")
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()
