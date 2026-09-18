import time

import discord

from . import config
from .utils import format_seconds, money, work_level_progress
from .views import LudeNavigator


class EmbedsMixin:
    def build_qol_embed(self, page: str, user_id: int) -> discord.Embed:
        if page == "mercado":
            return self.build_market_embed()
        if page == "cartera":
            return self.build_portfolio_embed(user_id)
        if page == "banco":
            return self.build_bank_embed(user_id)
        return self.build_overview_embed(user_id)

    async def show_qol(self, interaction: discord.Interaction, page: str):
        view = LudeNavigator(self, interaction.user.id, page)
        # Deliberadamente público: la vista limita los botones al autor.
        await interaction.response.send_message(
            embed=self.build_qol_embed(page, interaction.user.id), view=view, ephemeral=False
        )
        view.message = await interaction.original_response()

    def build_bank_embed(self, user_id: int) -> discord.Embed:
        primary = self.get_bank(user_id, "primary")
        extra = self.get_bank(user_id, "additional")
        embed = discord.Embed(title="🏦 Bank of Interlude", color=config.COLOR)
        embed.add_field(
            name=f"Cuenta Principal · Nivel {primary['level']}",
            value=f"**{money(primary['balance'])} / {money(self.bank_capacity(primary))}**",
            inline=False,
        )
        if extra:
            embed.add_field(
                name=f"Cuenta Adicional · Nivel {extra['level']}",
                value=f"**{money(extra['balance'])} / {money(self.bank_capacity(extra))}**",
                inline=False,
            )
        else:
            embed.add_field(name="Cuenta Adicional", value="No abierta. Requiere Principal Nivel 7.", inline=False)
        embed.set_footer(text="Panel público · solo quien lo abrió puede usar los botones")
        return embed

    def _portfolio_rows(self, user_id: int):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            try:
                return conn.execute(
                    """SELECT h.symbol, h.quantity, h.cost_basis, m.name, m.price
                       FROM crypto_holdings h JOIN crypto_market m ON m.symbol = h.symbol
                       WHERE h.user_id = ? AND h.quantity > 0 ORDER BY h.symbol""",
                    (user_id,),
                ).fetchall()
            finally:
                conn.close()

    @staticmethod
    def _signed_money(amount: float) -> str:
        return ("+" if amount > 0 else "") + money(amount)

    def build_portfolio_embed(self, user_id: int) -> discord.Embed:
        holdings = self._portfolio_rows(user_id)
        embed = discord.Embed(title="💼 Cartera Cripto", color=config.COLOR)
        total_value, total_cost, total_fees, total_net = 0.0, 0.0, 0, 0
        for row in holdings:
            qty, cost, price = float(row["quantity"]), float(row["cost_basis"]), float(row["price"])
            value = qty * price
            unrealized = value - cost
            percent = unrealized / cost * 100 if cost > 0 else 0.0
            fee = max(1, int(round(value * config.CRYPTO_FEE_RATE)))
            net_est = max(0, int(round(value)) - fee)
            total_value += value
            total_cost += cost
            total_fees += fee
            total_net += net_est
            embed.add_field(
                name=f"{row['name']} ({row['symbol']})",
                value=(f"Unidades: **{qty:.8f}**\n"
                       f"Precio actual: **{money(price)}**\n"
                       f"Precio promedio: **{money(cost / qty)}**\n"
                       f"Costo de adquisición: **{money(cost)}**\n"
                       f"Valor actual: **{money(value)}**\n"
                       f"Ganancia no realizada: **{self._signed_money(unrealized)} ({percent:+.2f}%)**\n"
                       f"Comisión de venta estimada: **{money(fee)}**\n"
                       f"Cobrarías aprox.: **{money(net_est)}**"),
                inline=True,
            )
        if holdings:
            aggregate = (total_value - total_cost) / total_cost * 100 if total_cost > 0 else 0.0
            embed.description = (
                f"Valor total: **{money(total_value)}** · Ganancia no realizada: "
                f"**{self._signed_money(total_value - total_cost)} ({aggregate:+.2f}%)**\n"
                f"Comisiones de venta estimadas: **{money(total_fees)}** · Cobrarías aprox.: **{money(total_net)}**"
            )
        else:
            embed.description = "Todavía no tenés criptomonedas."
        embed.set_footer(text="El costo promedio excluye la comisión de compra; estimaciones sujetas a precio, capacidad bancaria y retenciones judiciales.")
        return embed

    def build_market_embed(self) -> discord.Embed:
        embed = discord.Embed(title="📈 Mercado Cripto de Interlude", color=config.COLOR)
        now = int(time.time())
        with self.db_lock:
            conn = self.connect()
            try:
                market = conn.execute("SELECT * FROM crypto_market ORDER BY symbol").fetchall()
                for row in market:
                    history = conn.execute(
                        "SELECT price FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT 6",
                        (row["symbol"],),
                    ).fetchall()
                    prices = [float(item["price"]) for item in reversed(history)]
                    moves = []
                    for before, after in zip(prices[:-1], prices[1:]):
                        moves.append(
                            f"<:crypto_up:{config.CRYPTO_UP_EMOJI_ID}>" if after > before
                            else f"<:crypto_down:{config.CRYPTO_DOWN_EMOJI_ID}>" if after < before
                            else "➖"
                        )
                    pct = (prices[-1] / prices[-2] - 1) * 100 if len(prices) >= 2 and prices[-2] > 0 else 0.0
                    trend_change = (prices[-1] / prices[0] - 1) * 100 if len(prices) >= 2 and prices[0] > 0 else 0.0
                    trend = "↗️ Alza" if trend_change >= 1 else "↘️ Baja" if trend_change <= -1 else "↔️ Estable"
                    state = conn.execute(
                        "SELECT fundamental, regime FROM crypto_engine_state WHERE symbol = ?",
                        (row["symbol"],),
                    ).fetchone()
                    fundamental = float(state["fundamental"]) if state else float(config.CRYPTO_CONFIG[row["symbol"]]["initial"])
                    deviation = (float(row["price"]) / max(0.01, fundamental) - 1) * 100
                    next_update = int(row["updated_at"]) + int(config.CRYPTO_UPDATE_SECONDS)
                    next_text = f"<t:{next_update}:R>" if next_update > now else "Pendiente de actualización"
                    regime = config.MARKET_REGIME_LABELS.get(state["regime"], "↔️ Consolidación") if state else "↔️ Consolidación"
                    embed.add_field(
                        name=f"{row['name']} ({row['symbol']})",
                        value=(f"**{money(float(row['price']))}**\n"
                               f"Último cambio: **{pct:+.2f}%**\n"
                               f"Vs. fundamental: **{deviation:+.1f}%**\n"
                               f"Régimen: **{regime}**\n"
                               f"Tendencia reciente: **{trend} ({trend_change:+.2f}%)**\n"
                               f"Últimos 5: {' '.join(moves[-5:]) if moves else 'Sin historial'}\n"
                               f"Próximo tick: **{next_text}**"),
                        inline=True,
                    )
            finally:
                conn.close()
        embed.set_footer(text=f"Actualización cada {format_seconds(config.CRYPTO_UPDATE_SECONDS)} · movimientos de antiguo a reciente · datos al consultar")
        return embed

    def build_overview_embed(self, user_id: int) -> discord.Embed:
        user = self.get_user(user_id)
        primary = self.get_bank(user_id, "primary")
        extra = self.get_bank(user_id, "additional")
        investments = sum(float(row["quantity"]) * float(row["price"]) for row in self._portfolio_rows(user_id))
        job = config.JOBS.get(user["current_job"], config.JOBS["changas"])
        level, progress, needed = work_level_progress(user["work_xp"])
        now = int(time.time())
        embed = discord.Embed(title="🏙️ Interlude · Mi economía", color=config.COLOR)
        embed.add_field(name="💵 Wallet", value=money(user["wallet"]), inline=True)
        embed.add_field(name="🏦 Banco principal", value=money(primary["balance"]), inline=True)
        embed.add_field(name="📈 Inversiones", value=money(investments), inline=True)
        embed.add_field(name="⚖️ Deuda judicial", value=money(user["judicial_debt"]), inline=True)
        embed.add_field(name="💼 Profesión", value=job["name"], inline=True)
        embed.add_field(name="⭐ Work Level", value=f"{level} · {progress}/{needed or 'MAX'} XP", inline=True)
        if extra:
            embed.add_field(name="🏦 Banco adicional", value=money(extra["balance"]), inline=True)
        if user["arrested"]:
            embed.add_field(name="🚔 Estado", value=f"Arrestado · Fianza {money(user['bail_due'])}", inline=True)
        cooldowns = []
        for label, column, interval in (
            ("Trabajar", "last_work_at", config.WORK_COOLDOWN),
            ("Crimen", "last_crime_at", config.CRIME_COOLDOWN),
            ("Robar", "last_rob_at", config.ROB_COOLDOWN),
        ):
            ready_at = int(user[column]) + int(interval)
            cooldowns.append(f"**{label}:** <t:{ready_at}:R>" if ready_at > now else f"**{label}:** ✅ Disponible")
        embed.add_field(name="⏱️ Actividades", value="\n".join(cooldowns), inline=False)
        embed.set_footer(text="Panel público · solo quien lo abrió puede usar los botones")
        return embed
