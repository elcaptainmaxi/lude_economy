import time

import discord
from discord import app_commands

from . import config
from .groups import lude
from .utils import money


class BankMixin:
    def deposit(self, user_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            user = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            account = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (user_id,)
            ).fetchone()
            reserved = self.bank_reservations.get(user_id, 0)
            free = config.BANK_LEVELS[account["level"]]["capacity"] - account["balance"] - reserved
            if user["wallet"] < amount:
                conn.rollback(); conn.close()
                return False, "No tienes suficiente dinero en Wallet."
            if free < amount:
                conn.rollback(); conn.close()
                return False, f"Tu Cuenta Principal no tiene capacidad suficiente. Espacio disponible: **{money(max(0, free))}**."
            new_balance = account["balance"] + amount
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (new_balance, user_id))
            self.log_bank(cur, user_id, "primary", "deposit", amount, new_balance, "Depósito desde Wallet")
            conn.commit(); conn.close()
            return True, f"🏦 Depositaste **{money(amount)}** en tu Cuenta Principal."

    def withdraw(self, user_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            account = cur.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (user_id,)
            ).fetchone()
            if account["balance"] < amount:
                conn.rollback(); conn.close()
                return False, "No tienes suficiente dinero en tu Cuenta Principal."
            new_balance = account["balance"] - amount
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (new_balance, user_id))
            cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (amount, user_id))
            self.log_bank(cur, user_id, "primary", "withdraw", amount, new_balance, "Retiro hacia Wallet")
            conn.commit(); conn.close()
            return True, f"💵 Retiraste **{money(amount)}** hacia tu Wallet."

    def transfer(self, sender_id: int, receiver_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(sender_id); self.ensure_user(receiver_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        fee = max(1, int(round(amount * config.TRANSFER_FEE_RATE)))
        total = amount + fee
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            sender = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (sender_id,)
            ).fetchone()
            receiver = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (receiver_id,)
            ).fetchone()
            receiver_free = config.BANK_LEVELS[receiver["level"]]["capacity"] - receiver["balance"] - self.bank_reservations.get(receiver_id, 0)
            if sender["balance"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en tu Cuenta Principal ({money(amount)} + {money(fee)} de comisión)."
            if receiver_free < amount:
                conn.rollback(); conn.close()
                return False, "La Cuenta Principal del destinatario no tiene capacidad para recibir la transferencia completa."
            sender_new = sender["balance"] - total
            net_received, withheld = self.apply_income_withholding(cur, receiver_id, amount)
            receiver_new = receiver["balance"] + net_received
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (sender_new, sender_id))
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (receiver_new, receiver_id))
            self.log_bank(cur, sender_id, "primary", "transfer_sent", amount, sender_new, f"Transferencia a {receiver_id}")
            self.log_bank(cur, sender_id, "primary", "transfer_fee", fee, sender_new, f"Comisión {config.TRANSFER_FEE_RATE * 100:g}% por transferencia a {receiver_id}")
            self.log_bank(cur, receiver_id, "primary", "transfer_received", amount, receiver_new, f"Transferencia de {sender_id}; retención {withheld}")
            conn.commit(); conn.close()
            text = f"✅ Transferiste **{money(amount)}** a <@{receiver_id}>. Comisión: **{money(fee)}**."
            if withheld:
                text += f"\n⚖️ Al destinatario se le retuvieron **{money(withheld)}** para su Deuda Judicial."
            return True, text

    @lude.command(name="banco", description="Muestra tus cuentas de Bank of Interlude.")
    async def banco(self, interaction: discord.Interaction):
        await self.show_qol(interaction, "banco")

    @lude.command(name="depositar", description="Deposita Wallet en tu Cuenta Principal.")
    async def depositar(self, interaction: discord.Interaction, cantidad: int):
        ok, text = self.deposit(interaction.user.id, cantidad)
        await interaction.response.send_message(text, ephemeral=False)

    @lude.command(name="retirar", description="Retira dinero de tu Cuenta Principal a Wallet.")
    async def retirar(self, interaction: discord.Interaction, cantidad: int):
        ok, text = self.withdraw(interaction.user.id, cantidad)
        await interaction.response.send_message(text, ephemeral=False)

    @lude.command(name="transferir", description="Transfiere desde tu Cuenta Principal a otro usuario.")
    async def transferir(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if usuario.bot or usuario.id == interaction.user.id:
            await interaction.response.send_message("El destinatario debe ser otro usuario real.", ephemeral=False)
            return
        ok, text = self.transfer(interaction.user.id, usuario.id, cantidad)
        await interaction.response.send_message(text, ephemeral=False)

    @lude.command(name="mejorar-banco", description="Mejora una cuenta de Bank of Interlude.")
    @app_commands.choices(cuenta=[
        app_commands.Choice(name="Principal", value="primary"),
        app_commands.Choice(name="Adicional", value="additional"),
    ])
    async def mejorar_banco(self, interaction: discord.Interaction, cuenta: app_commands.Choice[str]):
        uid, account_type = interaction.user.id, cuenta.value
        account = self.get_bank(uid, account_type)
        if not account:
            await interaction.response.send_message("No tienes esa cuenta bancaria.", ephemeral=False)
            return
        level = int(account["level"])
        if level >= 7:
            await interaction.response.send_message("Esa cuenta ya está en Nivel 7.", ephemeral=False)
            return
        next_level = level + 1
        cost = config.BANK_LEVELS[next_level]["upgrade_cost"] if account_type == "primary" else config.ADDITIONAL_UPGRADE_COSTS[next_level]
        user = self.get_user(uid)
        if user["wallet"] < cost:
            await interaction.response.send_message(f"Necesitas **{money(cost)}** en Wallet.", ephemeral=False)
            return
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (cost, uid))
            cur.execute("UPDATE bank_accounts SET level = ? WHERE user_id = ? AND account_type = ?", (next_level, uid, account_type))
            current_balance = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, account_type)).fetchone()["balance"]
            self.log_bank(cur, uid, account_type, "bank_upgrade", cost, current_balance, f"Mejora a Nivel {next_level}")
            conn.commit(); conn.close()
        await interaction.response.send_message(f"🏦 **{cuenta.name}** mejorada a **Nivel {next_level}**. Nueva capacidad: **{money(config.BANK_LEVELS[next_level]['capacity'])}**.")

    @lude.command(name="abrir-adicional", description="Abre tu Cuenta Adicional al alcanzar Principal Nivel 7.")
    async def abrir_adicional(self, interaction: discord.Interaction):
        uid = interaction.user.id
        primary = self.get_bank(uid, "primary")
        if int(primary["level"]) < 7:
            await interaction.response.send_message("Tu Cuenta Principal debe estar en **Nivel 7**.", ephemeral=False)
            return
        if self.get_bank(uid, "additional"):
            await interaction.response.send_message("Ya tienes una Cuenta Adicional.", ephemeral=False)
            return
        user = self.get_user(uid)
        if user["wallet"] < config.ADDITIONAL_OPEN_COST:
            await interaction.response.send_message(f"Necesitas **{money(config.ADDITIONAL_OPEN_COST)}** en Wallet.", ephemeral=False)
            return
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (config.ADDITIONAL_OPEN_COST, uid))
            cur.execute("INSERT INTO bank_accounts(user_id, account_type, level, balance) VALUES(?, 'additional', ?, 0)", (uid, config.ADDITIONAL_OPEN_LEVEL))
            self.log_bank(cur, uid, "additional", "additional_open", config.ADDITIONAL_OPEN_COST, 0, "Apertura de Cuenta Adicional Nivel 4")
            conn.commit(); conn.close()
        await interaction.response.send_message("🏦 Cuenta Adicional abierta en **Nivel 4**, con capacidad de **INT$ 100.000**.")

    @lude.command(name="mover-banco", description="Mueve dinero entre Principal y Adicional sin comisión.")
    @app_commands.choices(destino=[
        app_commands.Choice(name="Principal → Adicional", value="p2a"),
        app_commands.Choice(name="Adicional → Principal", value="a2p"),
    ])
    async def mover_banco(self, interaction: discord.Interaction, destino: app_commands.Choice[str], cantidad: int):
        uid = interaction.user.id
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser mayor que 0.", ephemeral=False)
            return
        if not self.get_bank(uid, "additional"):
            await interaction.response.send_message("No tienes Cuenta Adicional.", ephemeral=False)
            return
        src, dst = ("primary", "additional") if destino.value == "p2a" else ("additional", "primary")
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            src_row = cur.execute("SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, src)).fetchone()
            dst_row = cur.execute("SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, dst)).fetchone()
            reserved = self.bank_reservations.get(uid, 0) if dst == "primary" else 0
            free = config.BANK_LEVELS[dst_row["level"]]["capacity"] - dst_row["balance"] - reserved
            if src_row["balance"] < cantidad:
                conn.rollback(); conn.close()
                await interaction.response.send_message("Saldo insuficiente en la cuenta de origen.", ephemeral=False)
                return
            if free < cantidad:
                conn.rollback(); conn.close()
                await interaction.response.send_message("La cuenta de destino no tiene capacidad suficiente.", ephemeral=False)
                return
            src_new, dst_new = src_row["balance"] - cantidad, dst_row["balance"] + cantidad
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = ?", (src_new, uid, src))
            cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = ?", (dst_new, uid, dst))
            self.log_bank(cur, uid, src, "internal_out", cantidad, src_new, f"Movimiento interno hacia {dst}")
            self.log_bank(cur, uid, dst, "internal_in", cantidad, dst_new, f"Movimiento interno desde {src}")
            conn.commit(); conn.close()
        await interaction.response.send_message(f"🏦 Moviste **{money(cantidad)}** sin comisión.")

    @lude.command(name="historial", description="Muestra los últimos 10 movimientos bancarios guardados.")
    async def historial(self, interaction: discord.Interaction):
        uid = interaction.user.id
        self.ensure_user(uid)
        with self.db_lock:
            conn = self.connect()
            rows = conn.execute(
                "SELECT * FROM bank_history WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (uid, int(config.BANK_HISTORY_KEEP)),
            ).fetchall()
            conn.close()
        if not rows:
            await interaction.response.send_message("Todavía no tienes movimientos bancarios.", ephemeral=False)
            return
        labels = {
            "deposit": "Depósito", "withdraw": "Retiro", "transfer_sent": "Transferencia enviada",
            "transfer_received": "Transferencia recibida", "transfer_fee": "Comisión transferencia",
            "internal_out": "Movimiento interno", "internal_in": "Movimiento interno",
            "bank_upgrade": "Mejora bancaria", "additional_open": "Apertura adicional",
            "salary": "Salario", "judicial_penalty": "Multa judicial", "crypto_buy": "Compra cripto",
            "crypto_sell": "Venta cripto", "bail": "Fianza", "debt_payment": "Pago de deuda",
        }
        lines = [f"**{labels.get(row['action'], row['action'])}** · {money(row['amount'])} · saldo {money(row['balance_after'])} · <t:{row['created_at']}:R>" for row in rows]
        embed = discord.Embed(title=f"📜 Bank of Interlude · Últimos {int(config.BANK_HISTORY_KEEP)}", description="\n".join(lines), color=config.COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @lude.command(name="deuda", description="Consulta tu Deuda Judicial.")
    async def deuda(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        embed = discord.Embed(title="⚖️ Deuda Judicial", color=config.COLOR_DANGER if user["judicial_debt"] else config.COLOR_SUCCESS)
        embed.description = f"Deuda actual: **{money(user['judicial_debt'])}**."
        if user["judicial_debt"]:
            embed.add_field(name="Retención", value=f"{config.JUDICIAL_RATE * 100:g}% de ingresos legítimos y recargo en compras hasta cancelar la deuda.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @lude.command(name="pagar-deuda", description="Paga voluntariamente parte o toda tu Deuda Judicial.")
    @app_commands.choices(origen=[
        app_commands.Choice(name="Wallet", value="wallet"),
        app_commands.Choice(name="Cuenta Principal", value="bank"),
    ])
    async def pagar_deuda(self, interaction: discord.Interaction, cantidad: int, origen: app_commands.Choice[str]):
        uid = interaction.user.id
        debt = int(self.get_user(uid)["judicial_debt"])
        if debt <= 0:
            await interaction.response.send_message("No tienes Deuda Judicial.", ephemeral=False); return
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser mayor que 0.", ephemeral=False); return
        pay = min(cantidad, debt)
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            if origen.value == "wallet":
                wallet = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (uid,)).fetchone()["wallet"]
                if wallet < pay:
                    conn.rollback(); conn.close(); await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=False); return
                cur.execute("UPDATE economy_users SET wallet = wallet - ?, judicial_debt = judicial_debt - ? WHERE user_id = ?", (pay, pay, uid))
            else:
                bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (uid,)).fetchone()
                if bank["balance"] < pay:
                    conn.rollback(); conn.close(); await interaction.response.send_message("No tienes suficiente saldo en la Cuenta Principal.", ephemeral=False); return
                new_balance = bank["balance"] - pay
                cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (new_balance, uid))
                cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (pay, uid))
                self.log_bank(cur, uid, "primary", "debt_payment", pay, new_balance, "Pago voluntario de Deuda Judicial")
            remaining = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (uid,)).fetchone()["judicial_debt"]
            conn.commit(); conn.close()
        await interaction.response.send_message(f"⚖️ Pagaste **{money(pay)}**. Deuda restante: **{money(remaining)}**.")

    @lude.command(name="fianza", description="Paga tu fianza y sal del arresto.")
    @app_commands.choices(metodo=[
        app_commands.Choice(name="Automático (Wallet → Banco → financiación)", value="auto"),
        app_commands.Choice(name="Solo Wallet", value="wallet"),
        app_commands.Choice(name="Solo Cuenta Principal", value="bank"),
    ])
    async def fianza(self, interaction: discord.Interaction, metodo: app_commands.Choice[str]):
        uid = interaction.user.id
        user = self.get_user(uid)
        if not user["arrested"]:
            await interaction.response.send_message("No estás arrestado.", ephemeral=False); return
        bail = int(user["bail_due"])
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            wallet = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (uid,)).fetchone()["wallet"]
            bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (uid,)).fetchone()["balance"]
            from_wallet = from_bank = financed = 0
            if metodo.value == "wallet":
                if wallet < bail:
                    conn.rollback(); conn.close(); await interaction.response.send_message("Tu Wallet no alcanza. Usa el método Automático para permitir financiación.", ephemeral=False); return
                from_wallet = bail
            elif metodo.value == "bank":
                if bank < bail:
                    conn.rollback(); conn.close(); await interaction.response.send_message("Tu Cuenta Principal no alcanza. Usa el método Automático para permitir financiación.", ephemeral=False); return
                from_bank = bail
            else:
                remaining = bail
                from_wallet = min(wallet, remaining); remaining -= from_wallet
                from_bank = min(bank, remaining); remaining -= from_bank
                financed = remaining
            if from_wallet:
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (from_wallet, uid))
            if from_bank:
                new_balance = bank - from_bank
                cur.execute("UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'", (new_balance, uid))
                self.log_bank(cur, uid, "primary", "bail", from_bank, new_balance, "Pago de fianza")
            if financed:
                cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt + ? WHERE user_id = ?", (financed, uid))
            cur.execute("UPDATE economy_users SET arrested = 0, bail_due = 0 WHERE user_id = ?", (uid,))
            conn.commit(); conn.close()
        text = f"🔓 Fianza de **{money(bail)}** pagada. Ya estás libre."
        if financed:
            text += f"\n🏦 Bank of Interlude financió **{money(financed)}**, agregado a tu Deuda Judicial."
        await interaction.response.send_message(text)
