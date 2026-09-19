"""Lude v3 bank, crypto and interactive UI. Requires an offline-migrated cents_v3 DB.

All account mutations use the existing SQLite db_lock + BEGIN IMMEDIATE. Market
prices/volumes remain denominated in whole INT$, not cents.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal, ROUND_DOWN

import discord
from discord import app_commands

from . import config
from .groups import lude, crypto_group
from .money_v3 import (MAX_SQLITE_INT, QUANTUM, cents, decimal, format_cents,
                       quantity_8, quote_net_sale, quote_sale, round_cents, safe_add)
from .utils import money, work_level_progress

ACCOUNT_NAMES = {"primary": "Principal", "additional": "Adicional", "savings": "Ahorro", "wallet": "Wallet"}
COINS = [app_commands.Choice(name="InterCoin (IC)", value="IC"),
         app_commands.Choice(name="Nova (NVA)", value="NVA"),
         app_commands.Choice(name="Flux (FLX)", value="FLX")]
ACCOUNT_CHOICES = [app_commands.Choice(name="Principal", value="primary"),
                   app_commands.Choice(name="Adicional", value="additional"),
                   app_commands.Choice(name="Ahorro", value="savings")]
DESTINATIONS = ACCOUNT_CHOICES


def price_text(price):
    value = decimal(price)
    text = f"{value:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"INT$ {text}"


def amount_or_error(value):
    try:
        return cents(value)
    except ValueError as exc:
        raise ValueError(f"❌ {exc}") from exc


class SaleConfirmationV3(discord.ui.View):
    """One-shot quote: any changed market, debt, fee or destination invalidates it."""
    def __init__(self, cog, user_id, symbol, mode, value, destination, quote, fingerprint):
        super().__init__(timeout=120)
        self.cog, self.user_id, self.symbol = cog, user_id, symbol
        self.mode, self.value, self.destination = mode, value, destination
        self.quote, self.fingerprint = quote, fingerprint
        self.operation_id = str(uuid.uuid4())
        self.finished = False
        self.message = None

    def embed(self):
        q = self.quote
        embed = discord.Embed(title=f"📉 Confirmar venta · {self.symbol}", color=config.COLOR_GOLD)
        embed.description = (f"Unidades: **{q.quantity:.8f}**\nPrecio: **{price_text(q.price)}**\n"
                             f"Bruto: **{format_cents(q.gross_cents)}**\n"
                             f"Comisión: **-{format_cents(q.fee_cents)}**\n"
                             f"Retención judicial: **-{format_cents(q.judicial_withheld_cents)}**\n"
                             f"**Neto a acreditar: {format_cents(q.credited_cents)}**\n"
                             f"Destino: **{ACCOUNT_NAMES[self.destination]}**")
        if q.requested_cents is not None and q.extra_cents:
            embed.add_field(name="Ajuste por precisión de 8 decimales",
                            value=f"Solicitaste {format_cents(q.requested_cents)}; diferencia +{format_cents(q.extra_cents)}.",
                            inline=False)
        embed.set_footer(text="La operación se ejecuta solo al confirmar. Si cambia algún dato, deberás reconfirmar.")
        return embed

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Solo quien solicitó la venta puede confirmarla.", ephemeral=False)
            return False
        return True

    @discord.ui.button(label="Confirmar venta", emoji="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        if self.finished:
            await interaction.response.send_message("Esta venta ya fue procesada.", ephemeral=False)
            return
        self.finished = True
        for item in self.children:
            item.disabled = True
        status, text, replacement = self.cog.execute_v3_sale(self)
        if status == "fallback":
            await interaction.response.edit_message(content=text, embed=replacement.embed(), view=replacement)
            replacement.message = await interaction.original_response()
        else:
            await interaction.response.edit_message(content=text, embed=None, view=self)

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        self.finished = True
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Venta cancelada. No se descontó nada.", embed=None, view=self)

    async def on_timeout(self):
        self.finished = True
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class SellModalV3(discord.ui.Modal, title="Vender criptomoneda"):
    def __init__(self, cog, user_id, symbol):
        super().__init__(timeout=300)
        self.cog, self.user_id, self.symbol = cog, user_id, symbol
        self.amount = discord.ui.TextInput(label="Neto que querés recibir (INT$)", placeholder="7500,25", max_length=40)
        self.add_item(self.amount)

    async def on_submit(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta cartera no es tuya.", ephemeral=False)
            return
        await self.cog.show_v3_sale(interaction, self.symbol, "net", str(self.amount.value), "savings")


class NavigatorV3(discord.ui.View):
    def __init__(self, cog, owner_id, page="panel"):
        super().__init__(timeout=600)
        self.cog, self.owner_id, self.page = cog, owner_id, page
        self.index, self.message = 0, None
        self.refresh_buttons()

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Solo quien abrió el panel puede usar sus botones.", ephemeral=False)
            return False
        return True

    def page_count(self):
        if self.page == "mercado":
            return len(config.CRYPTO_CONFIG)
        if self.page == "cartera":
            return len(self.cog.v3_positions(self.owner_id)) + 1
        return 1

    def refresh_buttons(self):
        count = self.page_count()
        self.index = max(0, min(self.index, count - 1))
        self.previous.disabled = self.page not in ("mercado", "cartera") or self.index == 0
        self.next.disabled = self.page not in ("mercado", "cartera") or self.index >= count - 1
        self.sell.disabled = self.page != "cartera" or self.index == 0
        self.savings.disabled = self.page == "ahorro"
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id:
                item.style = (discord.ButtonStyle.primary if item.custom_id == f"lude:v3:{self.page}"
                              else discord.ButtonStyle.secondary)

    def render(self):
        self.refresh_buttons()
        return self.cog.build_v3_page(self.page, self.owner_id, self.index)

    async def change(self, interaction, page, index=None):
        if page != self.page:
            self.index = 0
        self.page = page
        if index is not None:
            self.index = index
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Panel", emoji="🏙️", custom_id="lude:v3:panel", row=0)
    async def panel(self, interaction, button):
        await self.change(interaction, "panel")

    @discord.ui.button(label="Banco", emoji="🏦", custom_id="lude:v3:banco", row=0)
    async def banco(self, interaction, button):
        await self.change(interaction, "banco")

    @discord.ui.button(label="Mercado", emoji="📈", custom_id="lude:v3:mercado", row=0)
    async def mercado(self, interaction, button):
        await self.change(interaction, "mercado")

    @discord.ui.button(label="Cartera", emoji="💼", custom_id="lude:v3:cartera", row=0)
    async def cartera(self, interaction, button):
        await self.change(interaction, "cartera")

    @discord.ui.button(label="Ahorro", emoji="💰", custom_id="lude:v3:ahorro", row=1)
    async def savings(self, interaction, button):
        await self.change(interaction, "ahorro")

    @discord.ui.button(label="◀ Anterior", row=1)
    async def previous(self, interaction, button):
        await self.change(interaction, self.page, self.index - 1)

    @discord.ui.button(label="Siguiente ▶", row=1)
    async def next(self, interaction, button):
        await self.change(interaction, self.page, self.index + 1)

    @discord.ui.button(label="Vender", emoji="📉", style=discord.ButtonStyle.success, row=2)
    async def sell(self, interaction, button):
        positions = self.cog.v3_positions(self.owner_id)
        if self.page != "cartera" or not 0 < self.index <= len(positions):
            await interaction.response.send_message("Elegí una posición de tu cartera primero.", ephemeral=False)
            return
        await interaction.response.send_modal(SellModalV3(self.cog, self.owner_id, positions[self.index - 1]["symbol"]))

    @discord.ui.button(label="Actualizar", emoji="🔄", row=2)
    async def refresh(self, interaction, button):
        await self.change(interaction, self.page, self.index)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class FullV3Mixin:
    def ensure_user(self, user_id):
        super().ensure_user(user_id)
        if not getattr(self, "v3_active", False):
            return
        with self.db_lock:
            conn = self.connect()
            try:
                conn.execute("INSERT OR IGNORE INTO bank_accounts(user_id,account_type,level,balance) VALUES(?,'savings',0,0)", (user_id,))
                conn.commit()
            finally:
                conn.close()

    def bank_capacity(self, account):
        if account["account_type"] == "savings":
            return MAX_SQLITE_INT
        return super().bank_capacity(account)

    def v3_move(self, user_id, source, target, amount):
        self.ensure_user(user_id)
        if source == target or source not in ACCOUNT_NAMES or target not in ACCOUNT_NAMES:
            return False, "Elegí cuentas de origen y destino diferentes."
        if target == "wallet" and source != "savings":
            return False, "Para retirar de Principal usá /lude retirar. El retiro directo a Wallet está disponible desde Ahorro."
        if source == "wallet" and target != "savings":
            return False, "Para depositar en Principal usá /lude depositar. Wallet puede depositar directamente en Ahorro."
        if amount <= 0:
            return False, "La cantidad debe ser mayor que cero."
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                src = (cur.execute("SELECT wallet AS balance FROM economy_users WHERE user_id=?", (user_id,)).fetchone()
                       if source == "wallet" else cur.execute("SELECT * FROM bank_accounts WHERE user_id=? AND account_type=?", (user_id, source)).fetchone())
                dst = (cur.execute("SELECT wallet AS balance FROM economy_users WHERE user_id=?", (user_id,)).fetchone()
                       if target == "wallet" else cur.execute("SELECT * FROM bank_accounts WHERE user_id=? AND account_type=?", (user_id, target)).fetchone())
                if src is None or dst is None:
                    return False, "No tenés abierta una de las cuentas indicadas."
                if int(src["balance"]) < amount:
                    return False, "Saldo insuficiente en la cuenta de origen."
                new_src = int(src["balance"]) - amount
                new_dst = safe_add(int(dst["balance"]), amount)
                if target != "wallet":
                    reserved = self.bank_reservations.get(user_id, 0) if target == "primary" else 0
                    if target != "savings" and new_dst + reserved > self.bank_capacity(dst):
                        return False, "La cuenta de destino no tiene capacidad suficiente."
                if source == "wallet":
                    cur.execute("UPDATE economy_users SET wallet=? WHERE user_id=?", (new_src, user_id))
                else:
                    cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type=?", (new_src, user_id, source))
                if target == "wallet":
                    cur.execute("UPDATE economy_users SET wallet=? WHERE user_id=?", (new_dst, user_id))
                else:
                    cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type=?", (new_dst, user_id, target))
                self.log_bank(cur, user_id, target if target != "wallet" else source, "internal_move", amount,
                              new_dst if target != "wallet" else new_src,
                              f"{ACCOUNT_NAMES[source]} → {ACCOUNT_NAMES[target]}; origen {new_src}; destino {new_dst}")
                cur.execute("UPDATE bank_history SET source_account=?, destination_account=?, destination_balance_after=?,operation_id=? WHERE id=last_insert_rowid()",
                            (source, target, new_dst, str(uuid.uuid4())))
                conn.commit()
                return True, f"✅ Moviste **{format_cents(amount)}** de **{ACCOUNT_NAMES[source]}** a **{ACCOUNT_NAMES[target]}**, sin comisión."
            except (OverflowError, ValueError) as exc:
                return False, str(exc)
            finally:
                conn.close()

    def transfer(self, sender_id, receiver_id, amount):
        if sender_id == receiver_id:
            return False, "Para mover dinero entre tus cuentas usá /lude mover-fondos."
        self.ensure_user(sender_id); self.ensure_user(receiver_id)
        if amount <= 0:
            return False, "El importe debe ser mayor que cero."
        fee = max(100, round_cents(Decimal(amount) / 100 * decimal(config.TRANSFER_FEE_RATE)))
        total = safe_add(amount, fee)
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                sender = cur.execute("SELECT * FROM bank_accounts WHERE user_id=? AND account_type='primary'", (sender_id,)).fetchone()
                receiver = cur.execute("SELECT * FROM bank_accounts WHERE user_id=? AND account_type='primary'", (receiver_id,)).fetchone()
                if sender["balance"] < total:
                    return False, f"Necesitás {format_cents(total)} en tu Cuenta Principal, comisión incluida."
                if safe_add(receiver["balance"], amount, self.bank_reservations.get(receiver_id, 0)) > self.bank_capacity(receiver):
                    return False, "La Cuenta Principal del destinatario no tiene capacidad suficiente."
                net, withheld = self.apply_income_withholding(cur, receiver_id, amount)
                from_balance = int(sender["balance"]) - total
                to_balance = safe_add(int(receiver["balance"]), net)
                cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type='primary'", (from_balance, sender_id))
                cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type='primary'", (to_balance, receiver_id))
                self.log_bank(cur, sender_id, "primary", "transfer_sent", amount, from_balance, f"Transferencia a {receiver_id}")
                self.log_bank(cur, sender_id, "primary", "transfer_fee", fee, from_balance, f"Comisión por transferencia a {receiver_id}")
                self.log_bank(cur, receiver_id, "primary", "transfer_received", net, to_balance, f"De {sender_id}; retención {withheld}")
                conn.commit()
                return True, f"✅ Enviado {format_cents(amount)} a <@{receiver_id}>. Comisión: {format_cents(fee)}. Retención del destinatario: {format_cents(withheld)}."
            finally:
                conn.close()

    def crypto_buy(self, user_id, symbol, amount):
        self.ensure_user(user_id)
        symbol = symbol.upper()
        if symbol not in config.CRYPTO_CONFIG or amount <= 0:
            return False, "Criptomoneda o importe inválido."
        fee = max(100, round_cents(Decimal(amount) / 100 * decimal(config.CRYPTO_FEE_RATE)))
        total = safe_add(amount, fee)
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id=? AND account_type='primary'", (user_id,)).fetchone()
                market = cur.execute("SELECT price FROM crypto_market WHERE symbol=?", (symbol,)).fetchone()
                if bank["balance"] < total:
                    return False, f"Necesitás {format_cents(total)} en Principal, comisión incluida."
                price = decimal(market["price"])
                if price <= 0:
                    return False, "La cotización está temporalmente indisponible."
                qty = quantity_8(Decimal(amount) / 100 / price)
                if qty <= 0:
                    return False, "El importe es demasiado pequeño para comprar 0,00000001 unidades."
                new_bank = int(bank["balance"]) - total
                holding = cur.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=? AND symbol=?", (user_id, symbol)).fetchone()
                old_qty = decimal(holding["quantity"]) if holding else Decimal(0)
                old_cost = int(holding["cost_basis_cents"]) if holding else 0
                new_qty = old_qty + qty
                new_cost = safe_add(old_cost, amount)
                cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type='primary'", (new_bank, user_id))
                cur.execute("INSERT OR IGNORE INTO crypto_holdings(user_id,symbol,quantity,cost_basis,cost_basis_cents) VALUES(?,?,0,0,0)", (user_id,symbol))
                cur.execute("UPDATE crypto_holdings SET quantity=?,cost_basis=?,cost_basis_cents=? WHERE user_id=? AND symbol=?",
                            (float(new_qty), new_cost / 100, new_cost, user_id, symbol))
                cur.execute("UPDATE crypto_market SET buy_volume=buy_volume+? WHERE symbol=?", (amount / 100, symbol))
                self.log_bank(cur, user_id, "primary", "crypto_buy", total, new_bank, f"Compra {symbol}: {qty:.8f} unidades; fee {fee} centavos")
                conn.commit()
                return True, f"📈 Compraste **{qty:.8f} {symbol}** por **{format_cents(amount)}** + comisión **{format_cents(fee)}**."
            finally:
                conn.close()

    def v3_positions(self, user_id):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            try:
                return conn.execute("SELECT h.symbol,h.quantity,h.cost_basis_cents,m.price,m.name FROM crypto_holdings h JOIN crypto_market m ON m.symbol=h.symbol WHERE h.user_id=? AND h.quantity>0 ORDER BY h.symbol", (user_id,)).fetchall()
            finally:
                conn.close()

    def _quote_v3(self, cur, user_id, symbol, mode, value, destination):
        if destination not in ("primary", "additional", "savings"):
            raise ValueError("Cuenta de destino inválida.")
        holding = cur.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=? AND symbol=?", (user_id,symbol)).fetchone()
        if not holding or holding["quantity"] <= 0:
            raise ValueError(f"No tenés {symbol} para vender.")
        bank = cur.execute("SELECT * FROM bank_accounts WHERE user_id=? AND account_type=?", (user_id,destination)).fetchone()
        if bank is None:
            raise ValueError("No tenés abierta la cuenta de destino.")
        market = cur.execute("SELECT price FROM crypto_market WHERE symbol=?", (symbol,)).fetchone()
        if market is None:
            raise ValueError("La cotización no está disponible.")
        user = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id=?", (user_id,)).fetchone()
        available = decimal(holding["quantity"])
        arguments = dict(symbol=symbol,available_quantity=available,price=market["price"],
                         cost_basis_cents=int(holding["cost_basis_cents"]),
                         fee_rate=decimal(config.CRYPTO_FEE_RATE),judicial_rate=decimal(config.JUDICIAL_RATE),
                         judicial_debt_cents=int(user["judicial_debt"]),destination=destination)
        if mode == "net":
            quote = quote_net_sale(requested_cents=cents(value), **arguments)
        else:
            if mode == "units":
                units = decimal(value.replace(",", "."))
                if units <= 0 or units != units.quantize(QUANTUM, rounding=ROUND_DOWN):
                    raise ValueError("Ingresá hasta 8 decimales de unidades.")
            elif mode == "percent":
                percentage = decimal(value.replace(",", "."))
                if not 0 < percentage <= 100:
                    raise ValueError("El porcentaje debe ser mayor a 0 y menor o igual a 100.")
                units = available * percentage / 100
            else:
                raise ValueError("Modalidad inválida.")
            quote = quote_sale(quantity=units, requested_cents=None, **arguments)
        reserved = self.bank_reservations.get(user_id, 0) if destination == "primary" else 0
        free = MAX_SQLITE_INT - int(bank["balance"]) if destination == "savings" else self.bank_capacity(bank) - int(bank["balance"]) - reserved
        fingerprint = (str(available), int(holding["cost_basis_cents"]), str(market["price"]),
                       int(user["judicial_debt"]), str(config.CRYPTO_FEE_RATE), str(config.JUDICIAL_RATE),
                       int(bank["balance"]), self.bank_capacity(bank), reserved)
        return quote, fingerprint, free

    async def show_v3_sale(self, interaction, symbol, mode, value, destination="savings"):
        self.ensure_user(interaction.user.id)
        if symbol not in config.CRYPTO_CONFIG:
            await interaction.response.send_message("Criptomoneda inválida.", ephemeral=False)
            return
        try:
            with self.db_lock:
                conn = self.connect()
                try:
                    quote, fingerprint, free = self._quote_v3(conn.cursor(), interaction.user.id, symbol, mode, value, destination)
                finally:
                    conn.close()
            if free < quote.credited_cents:
                if destination != "savings":
                    destination = "savings"
                    with self.db_lock:
                        conn = self.connect()
                        try:
                            quote, fingerprint, free = self._quote_v3(conn.cursor(), interaction.user.id, symbol, mode, value, destination)
                        finally:
                            conn.close()
                    note = "La cuenta elegida no tiene espacio. Te propongo Ahorro; confirmá expresamente el nuevo destino.\n"
                else:
                    raise ValueError("La cuenta de Ahorro excedería el límite técnico de SQLite.")
            else:
                note = None
        except (ValueError, OverflowError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        view = SaleConfirmationV3(self, interaction.user.id, symbol, mode, value, destination, quote, fingerprint)
        await interaction.response.send_message(content=note, embed=view.embed(), view=view, ephemeral=False)
        view.message = await interaction.original_response()

    def execute_v3_sale(self, view):
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                if cur.execute("SELECT 1 FROM crypto_sale_receipts WHERE operation_id=?", (view.operation_id,)).fetchone():
                    return "error", "La venta ya fue registrada. No se duplicó el cobro.", None
                try:
                    quote, fingerprint, free = self._quote_v3(cur, view.user_id, view.symbol,view.mode,view.value,view.destination)
                except (ValueError,OverflowError) as exc:
                    return "error", f"❌ No se ejecutó la venta: {exc}", None
                if fingerprint != view.fingerprint or quote != view.quote:
                    return "error", "⚠️ Cambió el precio, la posición, la deuda, una comisión o la capacidad bancaria. Solicitá una nueva cotización; no se realizó la venta.", None
                if free < quote.credited_cents:
                    if view.destination != "savings":
                        new_quote,new_fingerprint,new_free = self._quote_v3(cur,view.user_id,view.symbol,view.mode,view.value,"savings")
                        if new_free >= new_quote.credited_cents:
                            replacement = SaleConfirmationV3(self,view.user_id,view.symbol,view.mode,view.value,"savings",new_quote,new_fingerprint)
                            return "fallback", "Tu cuenta ya no tiene espacio. Confirmá nuevamente si querés cobrar en Ahorro.", replacement
                    return "error", "La cuenta de destino no tiene capacidad suficiente; no se realizó la venta.", None
                bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id=? AND account_type=?", (view.user_id, view.destination)).fetchone()
                holding = cur.execute("SELECT quantity,cost_basis_cents FROM crypto_holdings WHERE user_id=? AND symbol=?", (view.user_id,view.symbol)).fetchone()
                available = decimal(holding["quantity"])
                remainder = max(Decimal(0), available - quote.quantity)
                if remainder < QUANTUM:
                    remainder = Decimal(0)
                if remainder == 0:
                    cost_remainder = 0
                else:
                    cost_remainder = int((Decimal(int(holding["cost_basis_cents"])) * remainder / available).quantize(Decimal(1),rounding=ROUND_DOWN))
                bank_new = safe_add(int(bank["balance"]), quote.credited_cents)
                cur.execute("UPDATE crypto_holdings SET quantity=?,cost_basis_cents=?,cost_basis=? WHERE user_id=? AND symbol=?",
                            (float(remainder), cost_remainder, cost_remainder/100,view.user_id,view.symbol))
                cur.execute("UPDATE bank_accounts SET balance=? WHERE user_id=? AND account_type=?", (bank_new,view.user_id,view.destination))
                if quote.judicial_withheld_cents:
                    cur.execute("UPDATE economy_users SET judicial_debt=judicial_debt-? WHERE user_id=?", (quote.judicial_withheld_cents,view.user_id))
                cur.execute("UPDATE crypto_market SET sell_volume=sell_volume+? WHERE symbol=?", (quote.gross_cents/100,view.symbol))
                self.log_bank(cur,view.user_id,view.destination,"crypto_sell",quote.credited_cents,bank_new,
                              f"Venta {view.symbol}: {quote.quantity:.8f} ud; bruto {quote.gross_cents}; comisión {quote.fee_cents}; retención {quote.judicial_withheld_cents}")
                cur.execute("INSERT INTO crypto_sale_receipts(operation_id,user_id,symbol,credited_cents,created_at) VALUES(?,?,?,?,?)",
                            (view.operation_id,view.user_id,view.symbol,quote.credited_cents,int(time.time())))
                conn.commit()
                return "success", f"✅ Vendiste {quote.quantity:.8f} {view.symbol} y recibiste **{format_cents(quote.credited_cents)}** en **{ACCOUNT_NAMES[view.destination]}**.",None
            finally:
                conn.close()

    def build_v3_page(self,page,user_id,index=0):
        if page == "mercado":
            with self.db_lock:
                conn = self.connect()
                try:
                    rows = conn.execute("SELECT * FROM crypto_market ORDER BY symbol").fetchall()
                    if not rows:
                        return discord.Embed(title="📈 Mercado",description="Sin cotizaciones.",color=config.COLOR)
                    row = rows[min(index,len(rows)-1)]
                    state = conn.execute("SELECT fundamental,regime FROM crypto_engine_state WHERE symbol=?",(row["symbol"],)).fetchone()
                    prices = [float(x["price"]) for x in reversed(conn.execute("SELECT price FROM crypto_history WHERE symbol=? ORDER BY id DESC LIMIT 6",(row["symbol"],)).fetchall())]
                finally:
                    conn.close()
            moves = [(f"<:crypto_up:{config.CRYPTO_UP_EMOJI_ID}>" if b>a else f"<:crypto_down:{config.CRYPTO_DOWN_EMOJI_ID}>" if b<a else "➖") for a,b in zip(prices[:-1],prices[1:])]
            change = (prices[-1]/prices[0]-1)*100 if len(prices)>1 and prices[0] else 0
            trend = "↗️ Alza" if change>=1 else "↘️ Baja" if change<=-1 else "↔️ Estable"
            fund = float(state["fundamental"]) if state else float(row["price"])
            divergence = (float(row["price"])/fund-1)*100 if fund>0 else 0
            next_tick=int(row["updated_at"])+int(config.CRYPTO_UPDATE_SECONDS)
            embed=discord.Embed(title=f"📈 {row['name']} ({row['symbol']}) · {index+1}/{len(rows)}",color=config.COLOR)
            embed.description=(f"Precio: **{price_text(row['price'])}**\nVs. fundamental: **{divergence:+.2f}%**\n"
                               f"Régimen: **{config.MARKET_REGIME_LABELS.get(state['regime'],'Consolidación') if state else 'Consolidación'}**\n"
                               f"Tendencia: **{trend} ({change:+.2f}%)**\nÚltimos 5: **{' '.join(moves[-5:]) or 'Sin historial'}**\n"
                               f"Próximo tick: <t:{next_tick}:R>")
            return embed
        if page == "cartera":
            rows=self.v3_positions(user_id)
            embed=discord.Embed(title="💼 Cartera Cripto",color=config.COLOR)
            if not rows:
                embed.description="Todavía no tenés posiciones activas."
                return embed
            total_value=sum(round_cents(decimal(row['quantity'])*decimal(row['price'])) for row in rows)
            total_cost=sum(int(row['cost_basis_cents']) for row in rows)
            gain=total_value-total_cost
            if index==0:
                embed.description=(f"Valor actual: **{format_cents(total_value)}**\n"
                                   f"Ganancia no realizada: **{'+' if gain>0 else ''}{format_cents(gain)}**\n"
                                   f"Posiciones activas: **{len(rows)}** · Elegí Siguiente para ver una y venderla.")
                return embed
            row=rows[min(index-1,len(rows)-1)]
            qty=decimal(row['quantity']); cost=int(row['cost_basis_cents'])
            val=round_cents(qty*decimal(row['price']))
            gain=val-cost
            pct=(Decimal(gain)/Decimal(cost)*100) if cost else Decimal(0)
            fee=max(100,round_cents(Decimal(val)/100*decimal(config.CRYPTO_FEE_RATE)))
            debt=int(self.get_user(user_id)['judicial_debt'])
            profit=max(0,val-cost)
            withholding=min(debt,round_cents(Decimal(profit)/100*decimal(config.JUDICIAL_RATE)))
            net=max(0,val-fee-withholding)
            embed.title=f"💼 {row['name']} ({row['symbol']}) · {index}/{len(rows)}"
            embed.description=(f"Unidades: **{qty:.8f}**\nPrecio: **{price_text(row['price'])}**\n"
                               f"Costo de adquisición: **{format_cents(cost)}**\nValor actual: **{format_cents(val)}**\n"
                               f"Ganancia no realizada: **{'+' if gain>0 else ''}{format_cents(gain)} ({pct:+.2f}%)**\n"
                               f"Comisión estimada: **{format_cents(fee)}**\nRetención estimada: **{format_cents(withholding)}**\n"
                               f"Neto estimado: **{format_cents(net)}**")
            return embed
        if page == "ahorro":
            savings=self.get_bank(user_id,"savings")
            embed=discord.Embed(title="💰 Bank of Interlude · Ahorro",color=config.COLOR)
            embed.description=(f"Saldo: **{format_cents(savings['balance'])}**\n"
                               "Sin límite de producto ni comisiones por movimientos propios.\n"
                               "Mové fondos con `/lude mover-fondos` o depositá directamente desde Wallet con `/lude ahorrar`.")
            return embed
        if page=="banco":
            embed=super().build_bank_embed(user_id)
            savings=self.get_bank(user_id,"savings")
            embed.add_field(name="💰 Cuenta de Ahorro · Sin límite de producto",value=format_cents(savings["balance"]),inline=False)
            return embed
        embed=super().build_overview_embed(user_id)
        savings=self.get_bank(user_id,"savings")
        embed.add_field(name="💰 Ahorro",value=format_cents(savings["balance"]),inline=True)
        return embed

    async def show_qol(self,interaction,page):
        view=NavigatorV3(self,interaction.user.id,page)
        await interaction.response.send_message(embed=view.render(),view=view,ephemeral=False)
        view.message=await interaction.original_response()

    @lude.command(name="ahorro",description="Consulta tu Cuenta de Ahorro, sin límite bancario de producto.")
    async def ahorro_v3(self,interaction:discord.Interaction):
        await self.show_qol(interaction,"ahorro")

    @lude.command(name="ahorrar",description="Deposita Wallet directamente en Ahorro sin comisión.")
    async def ahorrar_v3(self,interaction:discord.Interaction,cantidad:str):
        try:
            amount=amount_or_error(cantidad)
            ok,text=self.v3_move(interaction.user.id,"wallet","savings",amount)
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="mover-fondos",description="Mové dinero gratuitamente entre todas tus cuentas.")
    @app_commands.choices(origen=[*ACCOUNT_CHOICES,app_commands.Choice(name="Wallet (solo a Ahorro)",value="wallet")],
                          destino=[*DESTINATIONS,app_commands.Choice(name="Wallet (desde Ahorro)",value="wallet")])
    async def mover_fondos_v3(self,interaction:discord.Interaction,origen:app_commands.Choice[str],destino:app_commands.Choice[str],cantidad:str):
        try:
            amount=amount_or_error(cantidad)
            ok,text=self.v3_move(interaction.user.id,origen.value,destino.value,amount)
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="depositar",description="Deposita INT$ con centavos de Wallet a Principal.")
    async def depositar_v3(self,interaction:discord.Interaction,cantidad:str):
        try:
            ok,text=self.deposit(interaction.user.id,amount_or_error(cantidad))
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="retirar",description="Retira INT$ con centavos de Principal a Wallet.")
    async def retirar_v3(self,interaction:discord.Interaction,cantidad:str):
        try:
            ok,text=self.withdraw(interaction.user.id,amount_or_error(cantidad))
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="transferir",description="Transfiere INT$ con centavos a otro usuario.")
    async def transferir_v3(self,interaction:discord.Interaction,usuario:discord.Member,cantidad:str):
        if usuario.bot or usuario.id==interaction.user.id:
            await interaction.response.send_message("Elegí otro usuario real.",ephemeral=False)
            return
        try:
            ok,text=self.transfer(interaction.user.id,usuario.id,amount_or_error(cantidad))
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="mover-banco",description="Mové Principal ↔ Adicional sin comisión.")
    @app_commands.choices(destino=[app_commands.Choice(name="Principal → Adicional",value="p2a"),app_commands.Choice(name="Adicional → Principal",value="a2p")])
    async def mover_banco_v3(self,interaction:discord.Interaction,destino:app_commands.Choice[str],cantidad:str):
        source,target=("primary","additional") if destino.value=="p2a" else ("additional","primary")
        try:
            ok,text=self.v3_move(interaction.user.id,source,target,amount_or_error(cantidad))
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @lude.command(name="historial",description="Últimos diez registros bancarios con origen y destino.")
    async def historial_v3(self,interaction:discord.Interaction):
        self.ensure_user(interaction.user.id)
        with self.db_lock:
            conn=self.connect()
            try:
                rows=conn.execute("SELECT * FROM bank_history WHERE user_id=? ORDER BY created_at DESC,id DESC LIMIT 10",(interaction.user.id,)).fetchall()
            finally:
                conn.close()
        if not rows:
            await interaction.response.send_message("Todavía no tenés movimientos bancarios.",ephemeral=False)
            return
        lines=[]
        for row in rows:
            origin=row["source_account"] or row["account_type"]
            dest=row["destination_account"] or row["account_type"]
            label=f"{ACCOUNT_NAMES.get(origin,origin)} → {ACCOUNT_NAMES.get(dest,dest)}" if origin!=dest else row["action"]
            lines.append(f"**{label}** · {format_cents(row['amount'])} · saldo {format_cents(row['balance_after'])} · <t:{row['created_at']}:R>")
        embed=discord.Embed(title="📜 Últimos diez registros bancarios",description="\n".join(lines),color=config.COLOR)
        await interaction.response.send_message(embed=embed,ephemeral=False)

    @crypto_group.command(name="comprar",description="Comprá criptomonedas con INT$ y centavos desde Principal.")
    @app_commands.choices(moneda=COINS)
    async def crypto_comprar_v3(self,interaction:discord.Interaction,moneda:app_commands.Choice[str],monto:str):
        try:
            ok,text=self.crypto_buy(interaction.user.id,moneda.value,amount_or_error(monto))
        except (ValueError,OverflowError) as exc:
            text=f"❌ {exc}"
        await interaction.response.send_message(text,ephemeral=False)

    @crypto_group.command(name="vender",description="Vende unidades, porcentaje decimal o el neto final exacto.")
    @app_commands.choices(moneda=COINS,
                          modo=[app_commands.Choice(name="Unidades (hasta 8 decimales)",value="units"),
                                app_commands.Choice(name="Porcentaje decimal",value="percent"),
                                app_commands.Choice(name="INT$ netos después de todos los descuentos",value="net")],
                          destino=DESTINATIONS)
    async def crypto_vender_v3(self,interaction:discord.Interaction,moneda:app_commands.Choice[str],modo:app_commands.Choice[str],cantidad:str,
                              destino:app_commands.Choice[str]=None):
        await self.show_v3_sale(interaction,moneda.value,modo.value,cantidad,destino.value if destino else "savings")
