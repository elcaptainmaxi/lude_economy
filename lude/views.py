import math
import random
import sqlite3
from typing import Optional

import discord

from . import config
from .utils import format_seconds, money


class WorkView(discord.ui.View):
    def __init__(self, cog, user_id: int, job_id: str, prompt: str, options: list[str], correct: int):
        super().__init__(timeout=30)
        self.cog = cog
        self.user_id = user_id
        self.job_id = job_id
        self.prompt = prompt
        self.options = options
        self.correct = correct
        self.finished = False
        self.message: Optional[discord.InteractionMessage] = None
        for idx, option in enumerate(options):
            button = discord.ui.Button(label=option[:80], style=discord.ButtonStyle.secondary, row=idx // 2)
            button.callback = self._make_callback(idx)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                await interaction.response.send_message("Este turno de trabajo no es tuyo.", ephemeral=False)
                return
            if self.finished:
                await interaction.response.send_message("Este turno ya terminó.", ephemeral=False)
                return
            self.finished = True
            for child in self.children:
                child.disabled = True
            if index == self.correct:
                grade = random.choices(["S", "A", "B"], weights=[15, 35, 50], k=1)[0]
                correct = True
            else:
                grade = random.choices(["C", "D", "F"], weights=[50, 35, 15], k=1)[0]
                correct = False
            result = self.cog.settle_work(self.user_id, self.job_id, grade)
            await interaction.response.edit_message(
                embed=self.cog.build_work_result_embed(result, correct), view=self
            )
        return callback

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        result = self.cog.settle_work(self.user_id, self.job_id, "F")
        embed = self.cog.build_work_result_embed(result, False, timeout=True)
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class ProtectionOfferView(discord.ui.View):
    def __init__(self, cog, victim_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.victim_id = victim_id
        self.done = False
        self.buy.label = f"Comprar protección · {money(config.ROB_PROTECTION_COST)}"

    @discord.ui.button(label="Comprar protección", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.victim_id:
            await interaction.response.send_message("Solo la víctima puede comprar esta protección.", ephemeral=False)
            return
        if self.done:
            await interaction.response.send_message("Esta oferta ya fue utilizada.", ephemeral=False)
            return
        ok, text = self.cog.buy_rob_protection(self.victim_id)
        if not ok:
            await interaction.response.send_message(text, ephemeral=False)
            return
        self.done = True
        button.disabled = True
        await interaction.response.edit_message(content=text, view=self)


class BlackjackView(discord.ui.View):
    def __init__(self, cog, user_id: int, bet: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.bet = bet
        self.original_bet = bet
        self.deck = self._make_deck()
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.finished = False
        self.message: Optional[discord.InteractionMessage] = None

    @staticmethod
    def _make_deck():
        ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]
        suits = ["♠", "♥", "♦", "♣"]
        deck = [(rank, suit) for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    @staticmethod
    def hand_value(hand):
        total = aces = 0
        for rank, _ in hand:
            if rank == "A":
                total += 11; aces += 1
            elif rank in {"J", "Q", "K"}:
                total += 10
            else:
                total += int(rank)
        while total > 21 and aces:
            total -= 10; aces -= 1
        return total

    @staticmethod
    def hand_text(hand):
        return " ".join(f"`{rank}{suit}`" for rank, suit in hand)

    def is_natural(self, hand):
        return len(hand) == 2 and self.hand_value(hand) == 21

    def embed(self, reveal=False, footer=None):
        embed = discord.Embed(title="🃏 Blackjack · Bank of Interlude Casino", color=config.COLOR_GOLD)
        embed.add_field(name=f"Tu mano · {self.hand_value(self.player)}", value=self.hand_text(self.player), inline=False)
        if reveal:
            dealer_value, dealer_text = self.hand_value(self.dealer), self.hand_text(self.dealer)
        else:
            dealer_value, dealer_text = "?", f"`{self.dealer[0][0]}{self.dealer[0][1]}` `??`"
        embed.add_field(name=f"Dealer · {dealer_value}", value=dealer_text, inline=False)
        embed.add_field(name="Apuesta", value=money(self.bet), inline=True)
        if footer:
            embed.description = footer
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta partida no es tuya.", ephemeral=False)
            return False
        return True

    @discord.ui.button(label="Pedir", style=discord.ButtonStyle.primary, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return
        self.player.append(self.deck.pop())
        if self.hand_value(self.player) >= 21:
            await self.finish(interaction)
            return
        self.double.disabled = True
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.finished:
            await self.finish(interaction)

    @discord.ui.button(label="Doblar ×2", style=discord.ButtonStyle.success, emoji="✖️")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return
        if len(self.player) != 2:
            await interaction.response.send_message("Solo puedes doblar con tus dos cartas iniciales.", ephemeral=False)
            return
        if not self.cog.try_debit_wallet(self.user_id, self.bet):
            await interaction.response.send_message("No tienes suficiente Wallet para doblar.", ephemeral=False)
            return
        self.bet *= 2
        self.player.append(self.deck.pop())
        await self.finish(interaction)

    async def finish(self, interaction: Optional[discord.Interaction] = None, timed_out: bool = False):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        player_value = self.hand_value(self.player)
        player_natural = self.is_natural(self.player) and self.bet == self.original_bet
        if player_value <= 21:
            while self.hand_value(self.dealer) < int(config.BLACKJACK_DEALER_STAND):
                self.dealer.append(self.deck.pop())
        dealer_value = self.hand_value(self.dealer)
        dealer_natural = self.is_natural(self.dealer)
        if player_value > 21:
            outcome, total_return = "💥 Te pasaste de 21. Perdiste.", 0
        elif player_natural and not dealer_natural:
            total_return = int(round(self.bet * config.BLACKJACK_NATURAL_RETURN)); outcome = "🖤 Blackjack natural."
        elif dealer_value > 21:
            total_return = int(round(self.bet * config.BLACKJACK_NORMAL_RETURN)); outcome = "✅ El dealer se pasó. Ganaste."
        elif player_value > dealer_value:
            total_return = int(round(self.bet * config.BLACKJACK_NORMAL_RETURN)); outcome = "✅ Ganaste la mano."
        elif player_value == dealer_value:
            total_return = self.bet; outcome = "🤝 Empate. Se devuelve la apuesta."
        else:
            total_return = 0; outcome = "❌ Ganó el dealer."
        withheld = credited = 0
        if total_return > 0:
            credited, withheld = self.cog.credit_casino_return(self.user_id, self.bet, total_return)
        if timed_out:
            outcome = "⏱️ Tiempo agotado: te plantaste automáticamente.\n" + outcome
        if withheld:
            outcome += f"\n⚖️ Retención judicial: **{money(withheld)}**."
        if credited:
            outcome += f"\n💰 Acreditado: **{money(credited)}**."
        embed = self.embed(reveal=True, footer=outcome)
        if interaction is not None:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self):
        if not self.finished:
            await self.finish(timed_out=True)


class CoinflipView(discord.ui.View):
    def __init__(self, cog, creator_id: int, opponent_id: int, bet: int, creator_choice: str):
        super().__init__(timeout=60)
        self.cog, self.creator_id, self.opponent_id = cog, creator_id, opponent_id
        self.bet, self.creator_choice, self.done = bet, creator_choice, False
        self.message: Optional[discord.InteractionMessage] = None

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Solo el usuario desafiado puede aceptar.", ephemeral=False)
            return
        if self.done:
            return
        result = self.cog.resolve_coinflip(self.creator_id, self.opponent_id, self.bet, self.creator_choice)
        if not result["ok"]:
            await interaction.response.send_message(result["message"], ephemeral=False)
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        embed = discord.Embed(title="🪙 Coinflip PvP", color=config.COLOR_GOLD)
        embed.description = (
            f"Resultado: **{result['result']}**\n\n🏆 Ganador: <@{result['winner_id']}>\n"
            f"💰 Pozo: **{money(result['pool'])}**\n🏦 Comisión del casino: **{money(result['fee'])}**\n"
            f"💵 Acreditado: **{money(result['credited'])}**"
        )
        if result["withheld"]:
            embed.description += f"\n⚖️ Retención judicial: **{money(result['withheld'])}**"
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Solo el usuario desafiado puede rechazar.", ephemeral=False)
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="❌ Desafío de Coinflip rechazado.", embed=None, view=self)

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⌛ El desafío de Coinflip expiró.", view=self)
            except discord.HTTPException:
                pass


class LudeNavigator(discord.ui.View):
    def __init__(self, cog, owner_id: int, page: str = "panel"):
        super().__init__(timeout=600)
        self.cog, self.owner_id, self.page = cog, owner_id, page
        self.message = None
        self._mark_page()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Solo quien abrió este panel puede usar sus botones.", ephemeral=False)
            return False
        return True

    def _mark_page(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id:
                item.style = discord.ButtonStyle.primary if item.custom_id == f"lude:qol:{self.page}" else discord.ButtonStyle.secondary

    async def _show(self, interaction: discord.Interaction, page: str):
        self.page = page
        self._mark_page()
        await interaction.response.edit_message(embed=self.cog.build_qol_embed(page, self.owner_id), view=self)

    @discord.ui.button(label="Panel", emoji="🏙️", custom_id="lude:qol:panel", row=0)
    async def panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "panel")

    @discord.ui.button(label="Banco", emoji="🏦", custom_id="lude:qol:banco", row=0)
    async def banco(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "banco")

    @discord.ui.button(label="Mercado", emoji="📈", custom_id="lude:qol:mercado", row=0)
    async def mercado(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "mercado")

    @discord.ui.button(label="Cartera", emoji="💼", custom_id="lude:qol:cartera", row=0)
    async def cartera(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, "cartera")

    @discord.ui.button(label="Actualizar", emoji="🔄", style=discord.ButtonStyle.success, row=1)
    async def actualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, self.page)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class LudeAdminConfirmation(discord.ui.View):
    def __init__(self, cog, user_id: int, key: str, proposed, restore: bool = False):
        super().__init__(timeout=120)
        self.cog, self.user_id, self.key = cog, user_id, key
        self.restore, self.proposed = restore, proposed
        self.expected = config.setting_display_value(config.SETTING_SPECS[key])
        self.finished = False
        self.message = None

    def render(self):
        spec = config.SETTING_SPECS[self.key]
        target = spec.default if self.restore else self.proposed
        embed = discord.Embed(title="⚙️ Confirmar restauración" if self.restore else "⚙️ Confirmar cambio", color=config.COLOR_GOLD)
        embed.description = (
            f"**{spec.label}**\n`{self.key}`\n\nActual: **{config.format_setting_value(self.expected)}**\n"
            f"Nuevo: **{config.format_setting_value(target)}**\n\nEl cambio se aplicará solamente cuando presiones Confirmar."
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id or interaction.user.id != config.ADMIN_OWNER_ID:
            await interaction.response.send_message("⛔ Solo el dueño puede confirmar este cambio.", ephemeral=False)
            return False
        return True

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            await interaction.response.send_message("Este cambio ya fue procesado.", ephemeral=True)
            return
        if config.setting_display_value(config.SETTING_SPECS[self.key]) != self.expected:
            self.finished = True
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(content="⚠️ El ajuste cambió desde que abriste esta confirmación. Volvé a intentarlo.", embed=None, view=self)
            return
        try:
            value = (self.cog.reset_runtime_setting(self.key, interaction.user.id) if self.restore
                     else self.cog.update_runtime_setting(self.key, self.proposed, interaction.user.id))
        except (ValueError, KeyError, sqlite3.Error) as exc:
            await interaction.response.send_message(f"❌ No se aplicó el cambio: {exc}", ephemeral=False)
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        symbol = "♻️" if self.restore else "✅"
        await interaction.response.edit_message(
            content=f"{symbol} `{self.key}`: **{config.format_setting_value(self.expected)} → {config.format_setting_value(value)}** · registrado en el historial.",
            embed=None, view=self,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.finished = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="🚫 Cambio cancelado. No se modificó la configuración.", embed=None, view=self)

    async def on_timeout(self):
        if self.finished:
            return
        self.finished = True
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class LudeAdminModal(discord.ui.Modal, title="Editar ajuste de Lude"):
    def __init__(self, cog, user_id: int, key: str):
        super().__init__(timeout=300)
        self.cog, self.user_id, self.key = cog, user_id, key
        self.value = discord.ui.TextInput(
            label="Nuevo valor", default=str(config.setting_display_value(config.SETTING_SPECS[key])),
            placeholder="Introducí el valor deseado", max_length=100,
        )
        self.add_item(self.value)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id or interaction.user.id != config.ADMIN_OWNER_ID:
            await interaction.response.send_message("⛔ Sin autorización.", ephemeral=False)
            return
        try:
            value = config.parse_setting_value(config.SETTING_SPECS[self.key], str(self.value.value))
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=False)
            return
        view = LudeAdminConfirmation(self.cog, self.user_id, self.key, value)
        await interaction.response.send_message(embed=view.render(), view=view)
        view.message = await interaction.original_response()


class LudeAdminPanel(discord.ui.View):
    PER_PAGE = 20

    def __init__(self, cog, user_id: int):
        super().__init__(timeout=600)
        self.cog, self.user_id = cog, user_id
        self.category, self.page, self.key = config.SETTING_CATEGORIES[0], 0, None
        self.message = None
        self.rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id or interaction.user.id != config.ADMIN_OWNER_ID:
            await interaction.response.send_message("⛔ Solo el dueño puede utilizar este panel.", ephemeral=False)
            return False
        return True

    def items(self):
        return sorted((s for s in config.SETTING_SPECS.values() if s.category == self.category), key=lambda s: s.key)

    def rebuild(self):
        self.clear_items()
        items = self.items()
        pages = max(1, math.ceil(len(items) / self.PER_PAGE))
        self.page = min(self.page, pages - 1)
        visible = items[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]
        if self.key not in {item.key for item in visible}:
            self.key = visible[0].key if visible else None
        category = discord.ui.Select(
            placeholder="Categoría", row=0,
            options=[discord.SelectOption(label=cat.title(), value=cat, default=cat == self.category) for cat in config.SETTING_CATEGORIES],
        )
        category.callback = self.select_category
        self.add_item(category)
        if visible:
            select = discord.ui.Select(
                placeholder="Seleccioná el ajuste", row=1,
                options=[discord.SelectOption(label=item.key[:100], value=item.key, default=item.key == self.key) for item in visible],
            )
            select.callback = self.select_setting
            self.add_item(select)
        for label, style, row, callback, disabled in (
            ("◀ Anterior", discord.ButtonStyle.secondary, 2, self.previous, self.page == 0),
            ("Siguiente ▶", discord.ButtonStyle.secondary, 2, self.next_page, self.page >= pages - 1),
            ("✏️ Editar", discord.ButtonStyle.primary, 3, self.edit_setting, not self.key),
            ("♻️ Restaurar", discord.ButtonStyle.secondary, 3, self.restore_setting, not self.key),
            ("📋 Historial", discord.ButtonStyle.secondary, 4, self.history, False),
            ("🔄 Actualizar", discord.ButtonStyle.secondary, 4, self.refresh, False),
        ):
            button = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
            button.callback = callback
            self.add_item(button)

    def render(self):
        items = self.items()
        pages = max(1, math.ceil(len(items) / self.PER_PAGE))
        embed = discord.Embed(title="⚙️ Lude Admin · Panel interactivo", color=config.COLOR)
        embed.description = (
            f"Categoría: **{self.category.title()}** · Página **{self.page + 1}/{pages}**\n"
            "Elegí una clave y usá Editar o Restaurar. Todos los cambios requieren confirmación."
        )
        if self.key:
            spec = config.SETTING_SPECS[self.key]
            limits = []
            if spec.minimum is not None:
                limits.append(f"mín. {spec.minimum}")
            if spec.maximum is not None:
                limits.append(f"máx. {spec.maximum}")
            if spec.choices:
                limits.append(" / ".join(spec.choices))
            embed.add_field(
                name=spec.label[:256],
                value=(f"Clave: `{spec.key}`\nActual: **{config.format_setting_value(config.setting_display_value(spec))}**\n"
                       f"Predeterminado: **{config.format_setting_value(spec.default)}**\n"
                       f"Restricciones: {' · '.join(limits) if limits else '—'}"),
                inline=False,
            )
        embed.set_footer(text=f"{len(items)} ajustes · Solo el dueño puede interactuar")
        return embed

    async def select_category(self, interaction: discord.Interaction):
        self.category = interaction.data["values"][0]
        self.page, self.key = 0, None
        self.rebuild()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def select_setting(self, interaction: discord.Interaction):
        self.key = interaction.data["values"][0]
        self.rebuild()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def previous(self, interaction: discord.Interaction):
        self.page -= 1; self.key = None; self.rebuild()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1; self.key = None; self.rebuild()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def refresh(self, interaction: discord.Interaction):
        self.rebuild()
        await interaction.response.edit_message(embed=self.render(), view=self)

    async def edit_setting(self, interaction: discord.Interaction):
        if not self.key:
            await interaction.response.send_message("Elegí una clave.", ephemeral=False)
            return
        await interaction.response.send_modal(LudeAdminModal(self.cog, self.user_id, self.key))

    async def restore_setting(self, interaction: discord.Interaction):
        if not self.key:
            await interaction.response.send_message("Elegí una clave.", ephemeral=False)
            return
        view = LudeAdminConfirmation(self.cog, self.user_id, self.key, config.SETTING_SPECS[self.key].default, restore=True)
        await interaction.response.send_message(embed=view.render(), view=view)
        view.message = await interaction.original_response()

    async def history(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=self.cog.build_admin_history_embed())

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
