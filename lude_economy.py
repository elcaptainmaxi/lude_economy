import asyncio
import math
import random
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

GUILD_ID = 1545821075525603358
TESTER_ROLE_ID = 1545942284745576488
DB_PATH = "lude_economy.db"

COLOR = discord.Color.from_rgb(88, 101, 242)
COLOR_SUCCESS = discord.Color.from_rgb(46, 204, 113)
COLOR_DANGER = discord.Color.from_rgb(231, 76, 60)
COLOR_GOLD = discord.Color.from_rgb(241, 196, 15)

CURRENCY = "INT$"

WORK_COOLDOWN = 5 * 60
CRIME_COOLDOWN = 5 * 60  # Fácil de ajustar durante testing.
ROB_COOLDOWN = 30 * 60
ROB_PROTECTION_SECONDS = 30 * 60
ROB_PROTECTION_COST = 1_500

CASINO_MIN_BET = 50
COINFLIP_FEE_RATE = 0.05
JUDICIAL_RATE = 0.25
TRANSFER_FEE_RATE = 0.05

SLOTS_JACKPOT_BASE = 10_000
SLOTS_JACKPOT_CONTRIBUTION = 0.05

CRYPTO_UPDATE_SECONDS = 15 * 60
CRYPTO_FEE_RATE = 0.01
CRYPTO_HISTORY_KEEP = 96  # 24 horas a 15 min por tick.

BANK_LEVELS = {
    1: {"capacity": 10_000, "upgrade_cost": 0},
    2: {"capacity": 25_000, "upgrade_cost": 2_500},
    3: {"capacity": 50_000, "upgrade_cost": 7_500},
    4: {"capacity": 100_000, "upgrade_cost": 20_000},
    5: {"capacity": 250_000, "upgrade_cost": 50_000},
    6: {"capacity": 500_000, "upgrade_cost": 100_000},
    7: {"capacity": 1_250_000, "upgrade_cost": 250_000},
}

ADDITIONAL_OPEN_LEVEL = 4
ADDITIONAL_OPEN_COST = 40_000
ADDITIONAL_UPGRADE_COSTS = {
    5: 100_000,
    6: 200_000,
    7: 500_000,
}

GRADE_MULTIPLIERS = {
    "S": 1.40,
    "A": 1.20,
    "B": 1.00,
    "C": 0.80,
    "D": 0.55,
    "F": 0.25,
}

GRADE_XP_MULTIPLIERS = {
    "S": 1.40,
    "A": 1.20,
    "B": 1.00,
    "C": 0.80,
    "D": 0.60,
    "F": 0.35,
}


# ============================================================
# TRABAJOS
# payment: wallet / bank
# Todo está centralizado acá para poder balancearlo rápido.
# ============================================================

JOBS = {
    "changas": {
        "name": "Desempleado / Changas", "level": 0, "branch": "Inicial",
        "salary": (100, 180), "payment": "wallet", "style": "general",
    },
    "reparador": {
        "name": "Reparador independiente", "level": 1, "branch": "Oficios",
        "salary": (100, 180), "payment": "wallet", "style": "trades",
    },
    "monotributista": {
        "name": "Monotributista", "level": 1, "branch": "Negocios",
        "salary": (100, 180), "payment": "wallet", "style": "business",
    },
    "repartidor": {
        "name": "Repartidor", "level": 3, "branch": "Servicios",
        "salary": (140, 230), "payment": "wallet", "style": "services",
    },
    "cajero": {
        "name": "Cajero", "level": 3, "branch": "Comercio",
        "salary": (140, 230), "payment": "bank", "style": "commerce",
    },
    "mecanico": {
        "name": "Mecánico", "level": 5, "branch": "Oficios",
        "salary": (180, 300), "payment": "wallet", "style": "trades",
    },
    "cocinero": {
        "name": "Cocinero", "level": 5, "branch": "Gastronomía",
        "salary": (180, 300), "payment": "bank", "style": "gastronomy",
    },
    "vendedor": {
        "name": "Vendedor", "level": 5, "branch": "Comercio",
        "salary": (180, 300), "payment": "bank", "style": "commerce",
    },
    "electricista": {
        "name": "Electricista", "level": 8, "branch": "Oficios",
        "salary": (230, 360), "payment": "wallet", "style": "trades",
    },
    "conductor": {
        "name": "Conductor", "level": 8, "branch": "Servicios",
        "salary": (230, 360), "payment": "bank", "style": "services",
    },
    "guardia": {
        "name": "Guardia de seguridad", "level": 8, "branch": "Seguridad",
        "salary": (230, 360), "payment": "bank", "style": "security",
    },
    "tecnico": {
        "name": "Técnico", "level": 12, "branch": "Tecnología",
        "salary": (290, 440), "payment": "bank", "style": "technology",
    },
    "programador-jr": {
        "name": "Programador Jr.", "level": 12, "branch": "Tecnología",
        "salary": (290, 440), "payment": "bank", "style": "technology",
    },
    "administrativo": {
        "name": "Administrativo", "level": 12, "branch": "Negocios",
        "salary": (290, 440), "payment": "bank", "style": "business",
    },
    "policia": {
        "name": "Policía", "level": 17, "branch": "Seguridad",
        "salary": (360, 550), "payment": "bank", "style": "security",
    },
    "enfermero": {
        "name": "Enfermero", "level": 17, "branch": "Salud",
        "salary": (360, 550), "payment": "bank", "style": "health",
    },
    "contador": {
        "name": "Contador", "level": 17, "branch": "Finanzas",
        "salary": (360, 550), "payment": "bank", "style": "finance",
    },
    "ingeniero": {
        "name": "Ingeniero", "level": 23, "branch": "Tecnología",
        "salary": (450, 680), "payment": "bank", "style": "technology",
    },
    "programador-sr": {
        "name": "Programador Sr.", "level": 23, "branch": "Tecnología",
        "salary": (450, 680), "payment": "bank", "style": "technology",
    },
    "arquitecto": {
        "name": "Arquitecto", "level": 23, "branch": "Profesional",
        "salary": (450, 680), "payment": "bank", "style": "professional",
    },
    "medico": {
        "name": "Médico", "level": 30, "branch": "Salud",
        "salary": (570, 850), "payment": "bank", "style": "health",
    },
    "abogado": {
        "name": "Abogado", "level": 30, "branch": "Derecho",
        "salary": (570, 850), "payment": "bank", "style": "law",
    },
    "gerente": {
        "name": "Gerente", "level": 30, "branch": "Negocios",
        "salary": (570, 850), "payment": "bank", "style": "business",
    },
    "cirujano": {
        "name": "Cirujano", "level": 40, "branch": "Salud",
        "salary": (750, 1_100), "payment": "bank", "style": "health",
    },
    "director-ejecutivo": {
        "name": "Director ejecutivo", "level": 40, "branch": "Negocios",
        "salary": (750, 1_100), "payment": "bank", "style": "business",
    },
    "juez": {
        "name": "Juez", "level": 40, "branch": "Derecho",
        "salary": (750, 1_100), "payment": "bank", "style": "law",
    },
    "especialista-elite": {
        "name": "Especialista élite", "level": 50, "branch": "Profesional",
        "salary": (950, 1_400), "payment": "bank", "style": "professional",
    },
}


WORK_MINIGAMES = {
    "general": [
        ("Te ofrecen dos changas al mismo tiempo. ¿Cuál priorizás?", ["La que paga mejor y puedo terminar", "Las dos a la vez", "Ninguna"], 0),
        ("Un cliente cambia el pedido a último momento.", ["Confirmo el cambio y reorganizo", "Lo ignoro", "Me voy"], 0),
    ],
    "trades": [
        ("Detectás una falla antes de entregar el trabajo.", ["La corrijo y pruebo de nuevo", "La tapo", "Entrego igual"], 0),
        ("Una herramienta empieza a fallar en medio del trabajo.", ["Paro y la reviso", "La fuerzo", "Improviso sin revisar"], 0),
    ],
    "business": [
        ("Un gasto no coincide con el registro.", ["Reviso comprobantes", "Lo redondeo", "Lo borro"], 0),
        ("Tenés dos tareas urgentes.", ["Priorizo por impacto y plazo", "Hago la más fácil", "Espero"], 0),
    ],
    "services": [
        ("Hay una demora inesperada en la ruta.", ["Busco una alternativa segura", "Acelero de más", "Cancelo sin avisar"], 0),
        ("El cliente da una dirección dudosa.", ["La confirmo antes de salir", "Adivino", "Lo dejo en cualquier lado"], 0),
    ],
    "commerce": [
        ("La caja no coincide al cierre.", ["Recuento y reviso movimientos", "Cambio el número", "Lo dejo así"], 0),
        ("Un cliente reclama un precio distinto.", ["Verifico el precio registrado", "Discuto", "Le cobro cualquier cosa"], 0),
    ],
    "gastronomy": [
        ("Un plato sale con un ingrediente equivocado.", ["Lo rehago", "Lo sirvo igual", "Oculto el ingrediente"], 0),
        ("Se acumulan pedidos.", ["Ordeno por tiempos de cocción", "Cocino al azar", "Dejo de tomar pedidos"], 0),
    ],
    "security": [
        ("Ves una situación sospechosa pero no confirmada.", ["Observo y sigo protocolo", "Actúo sin verificar", "La ignoro"], 0),
        ("Dos incidentes ocurren a la vez.", ["Priorizo el de mayor riesgo", "Voy al más cercano sin pensar", "No intervengo"], 0),
    ],
    "technology": [
        ("Un cambio rompe una función que antes servía.", ["Revierto y diagnostico", "Lo despliego igual", "Borro los logs"], 0),
        ("Un error aparece solo a veces.", ["Reproduzco y registro condiciones", "Lo marco resuelto", "Reinicio y olvido"], 0),
    ],
    "health": [
        ("Dos pacientes necesitan atención.", ["Priorizo por gravedad", "Elijo al azar", "Atiendo al que llegó último"], 0),
        ("Un dato médico no está claro.", ["Lo verifico antes de actuar", "Lo supongo", "Lo omito"], 0),
    ],
    "finance": [
        ("Un número grande no concilia.", ["Rastreo el asiento", "Lo compenso manualmente", "Lo oculto"], 0),
        ("Detectás un movimiento duplicado.", ["Lo verifico y corrijo", "Lo dejo", "Duplico otro para equilibrar"], 0),
    ],
    "professional": [
        ("El proyecto tiene un riesgo nuevo.", ["Actualizo el plan y mitigaciones", "Lo ignoro", "Lo oculto"], 0),
        ("Un cálculo crítico parece extraño.", ["Lo reviso antes de continuar", "Confío sin revisar", "Lo redondeo"], 0),
    ],
    "law": [
        ("Un documento tiene una contradicción.", ["La reviso antes de presentarlo", "La dejo", "Borro una parte sin registrar"], 0),
        ("Falta una fuente importante.", ["La verifico y documento", "La invento", "La omito"], 0),
    ],
}


# ============================================================
# CRIMEN
# ============================================================

CRIME_CATEGORIES = {
    "minor": {
        "name": "🟢 Menor", "weight": 35, "success": 0.80, "arrest_if_fail": 0.15,
        "reward": (0.50, 1.00), "fine": (0.25, 0.50), "bail": 0.50,
        "crimes": ["Carterismo", "Hurto en una tienda", "Estafa callejera", "Robo de bicicleta"],
    },
    "moderate": {
        "name": "🔵 Moderado", "weight": 27, "success": 0.65, "arrest_if_fail": 0.30,
        "reward": (1.00, 2.00), "fine": (0.50, 1.00), "bail": 1.00,
        "crimes": ["Robo de un domicilio", "Robo de un comercio", "Estafa online", "Robo de motocicleta"],
    },
    "considerable": {
        "name": "🟡 Considerable", "weight": 20, "success": 0.50, "arrest_if_fail": 0.45,
        "reward": (2.00, 3.50), "fine": (1.00, 1.75), "bail": 2.00,
        "crimes": ["Robo de vehículo", "Contrabando", "Robo de un depósito", "Fraude financiero"],
    },
    "grave": {
        "name": "🔴 Grave", "weight": 12, "success": 0.35, "arrest_if_fail": 0.65,
        "reward": (3.50, 6.00), "fine": (1.75, 3.00), "bail": 3.50,
        "crimes": ["Robo de joyería", "Robo de camión de valores", "Gran fraude financiero", "Robo de casino"],
    },
    "extreme": {
        "name": "🟣 Extremo", "weight": 6, "success": 0.20, "arrest_if_fail": 0.80,
        "reward": (6.00, 10.00), "fine": (3.00, 5.00), "bail": 6.00,
        "crimes": ["Robo bancario", "Robo de bóveda", "Golpe al Banco de Interlude"],
    },
}


# ============================================================
# CRIPTOMONEDAS
# ============================================================

CRYPTO_CONFIG = {
    "IC": {
        "name": "InterCoin", "initial": 1_000.0,
        "auto_min": 0.01, "auto_max": 0.04, "player_max": 0.02,
    },
    "NVA": {
        "name": "Nova", "initial": 250.0,
        "auto_min": 0.03, "auto_max": 0.09, "player_max": 0.04,
    },
    "FLX": {
        "name": "Flux", "initial": 50.0,
        "auto_min": 0.07, "auto_max": 0.18, "player_max": 0.06,
    },
}


# ============================================================
# HELPERS
# ============================================================


def money(value: int | float) -> str:
    if isinstance(value, float) and not value.is_integer():
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{CURRENCY} {formatted}"
    return f"{CURRENCY} {int(round(value)):,}".replace(",", ".")


def format_seconds(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def work_level_from_xp(total_xp: int) -> int:
    level = 0
    remaining = max(0, total_xp)
    while level < 100:
        needed = int(100 + 35 * (level ** 1.35))
        if remaining < needed:
            break
        remaining -= needed
        level += 1
    return level


def work_level_progress(total_xp: int) -> tuple[int, int, int]:
    level = 0
    remaining = max(0, total_xp)
    while level < 100:
        needed = int(100 + 35 * (level ** 1.35))
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1
    return level, remaining, 0


def job_level_progress(total_xp: int) -> tuple[int, int, int]:
    level = 0
    remaining = max(0, total_xp)
    while level < 100:
        needed = int(80 + 25 * (level ** 1.30))
        if remaining < needed:
            return level, remaining, needed
        remaining -= needed
        level += 1
    return level, remaining, 0


def rob_bail_multiplier(theft_percent: int) -> float:
    if theft_percent <= 15:
        return 0.50
    if theft_percent <= 30:
        return 1.00
    if theft_percent <= 45:
        return 2.00
    if theft_percent <= 55:
        return 3.50
    return 6.00


class TesterLudeGroup(app_commands.Group):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if interaction.guild_id != GUILD_ID:
            return False

        member = interaction.user
        tester_role = interaction.guild.get_role(TESTER_ROLE_ID) if interaction.guild else None
        allowed = (
            isinstance(member, discord.Member)
            and tester_role is not None
            and member.top_role.position >= tester_role.position
        )
        if allowed:
            return True

        if interaction.type != discord.InteractionType.autocomplete and not interaction.response.is_done():
            await interaction.response.send_message(
                f"🧪 Este sistema está en **testing**. Necesitas el rol <@&{TESTER_ROLE_ID}> para usar `/lude`.",
                ephemeral=True,
            )
        return False


# ============================================================
# VIEWS
# ============================================================

class WorkView(discord.ui.View):
    def __init__(self, cog: "LudeEconomy", user_id: int, job_id: str, prompt: str, options: list[str], correct: int):
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
                await interaction.response.send_message("Este turno de trabajo no es tuyo.", ephemeral=True)
                return
            if self.finished:
                await interaction.response.send_message("Este turno ya terminó.", ephemeral=True)
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
            embed = self.cog.build_work_result_embed(result, correct)
            await interaction.response.edit_message(embed=embed, view=self)
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
    def __init__(self, cog: "LudeEconomy", victim_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.victim_id = victim_id
        self.done = False

    @discord.ui.button(label="Comprar protección · INT$ 1.500", style=discord.ButtonStyle.primary, emoji="🛡️")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.victim_id:
            await interaction.response.send_message("Solo la víctima puede comprar esta protección.", ephemeral=True)
            return
        if self.done:
            await interaction.response.send_message("Esta oferta ya fue utilizada.", ephemeral=True)
            return

        ok, text = self.cog.buy_rob_protection(self.victim_id)
        if not ok:
            await interaction.response.send_message(text, ephemeral=True)
            return

        self.done = True
        button.disabled = True
        await interaction.response.edit_message(content=text, view=self)


class BlackjackView(discord.ui.View):
    def __init__(self, cog: "LudeEconomy", user_id: int, bet: int):
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
        total = 0
        aces = 0
        for rank, _ in hand:
            if rank == "A":
                total += 11
                aces += 1
            elif rank in {"J", "Q", "K"}:
                total += 10
            else:
                total += int(rank)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    @staticmethod
    def hand_text(hand):
        return " ".join(f"`{rank}{suit}`" for rank, suit in hand)

    def is_natural(self, hand):
        return len(hand) == 2 and self.hand_value(hand) == 21

    def embed(self, reveal=False, footer=None):
        embed = discord.Embed(title="🃏 Blackjack · Bank of Interlude Casino", color=COLOR_GOLD)
        embed.add_field(
            name=f"Tu mano · {self.hand_value(self.player)}",
            value=self.hand_text(self.player),
            inline=False,
        )
        if reveal:
            dealer_value = self.hand_value(self.dealer)
            dealer_text = self.hand_text(self.dealer)
        else:
            dealer_value = "?"
            dealer_text = f"`{self.dealer[0][0]}{self.dealer[0][1]}` `??`"
        embed.add_field(name=f"Dealer · {dealer_value}", value=dealer_text, inline=False)
        embed.add_field(name="Apuesta", value=money(self.bet), inline=True)
        if footer:
            embed.description = footer
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Esta partida no es tuya.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pedir", style=discord.ButtonStyle.primary, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return
        self.player.append(self.deck.pop())
        value = self.hand_value(self.player)
        if value >= 21:
            await self.finish(interaction)
            return
        self.double.disabled = True
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Plantarse", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return
        await self.finish(interaction)

    @discord.ui.button(label="Doblar", style=discord.ButtonStyle.success, emoji="×2")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return
        if len(self.player) != 2:
            await interaction.response.send_message("Solo puedes doblar con tus dos cartas iniciales.", ephemeral=True)
            return
        if not self.cog.try_debit_wallet(self.user_id, self.bet):
            await interaction.response.send_message("No tienes suficiente Wallet para doblar.", ephemeral=True)
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
            while self.hand_value(self.dealer) < 17:
                self.dealer.append(self.deck.pop())

        dealer_value = self.hand_value(self.dealer)
        dealer_natural = self.is_natural(self.dealer)

        if player_value > 21:
            outcome, total_return = "💥 Te pasaste de 21. Perdiste.", 0
        elif player_natural and not dealer_natural:
            total_return = int(round(self.bet * 2.5))
            outcome = "🖤 Blackjack natural."
        elif dealer_value > 21:
            total_return = self.bet * 2
            outcome = "✅ El dealer se pasó. Ganaste."
        elif player_value > dealer_value:
            total_return = self.bet * 2
            outcome = "✅ Ganaste la mano."
        elif player_value == dealer_value:
            total_return = self.bet
            outcome = "🤝 Empate. Se devuelve la apuesta."
        else:
            total_return = 0
            outcome = "❌ Ganó el dealer."

        withheld = 0
        credited = 0
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
    def __init__(self, cog: "LudeEconomy", creator_id: int, opponent_id: int, bet: int, creator_choice: str):
        super().__init__(timeout=60)
        self.cog = cog
        self.creator_id = creator_id
        self.opponent_id = opponent_id
        self.bet = bet
        self.creator_choice = creator_choice
        self.done = False
        self.message: Optional[discord.InteractionMessage] = None

    @discord.ui.button(label="Aceptar", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Solo el usuario desafiado puede aceptar.", ephemeral=True)
            return
        if self.done:
            return

        result = self.cog.resolve_coinflip(self.creator_id, self.opponent_id, self.bet, self.creator_choice)
        if not result["ok"]:
            await interaction.response.send_message(result["message"], ephemeral=True)
            return

        self.done = True
        for child in self.children:
            child.disabled = True

        embed = discord.Embed(title="🪙 Coinflip PvP", color=COLOR_GOLD)
        embed.description = (
            f"Resultado: **{result['result']}**\n\n"
            f"🏆 Ganador: <@{result['winner_id']}>\n"
            f"💰 Pozo: **{money(result['pool'])}**\n"
            f"🏦 Comisión del casino: **{money(result['fee'])}**\n"
            f"💵 Acreditado: **{money(result['credited'])}**"
        )
        if result["withheld"]:
            embed.description += f"\n⚖️ Retención judicial: **{money(result['withheld'])}**"
        await interaction.response.edit_message(content=None, embed=embed, view=self)

    @discord.ui.button(label="Rechazar", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.opponent_id:
            await interaction.response.send_message("Solo el usuario desafiado puede rechazar.", ephemeral=True)
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


# ============================================================
# COG
# ============================================================

class LudeEconomy(commands.Cog):
    lude = TesterLudeGroup(
        name="lude",
        description="Economía de Interlude (testing).",
        guild_ids=[GUILD_ID],
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_lock = threading.RLock()
        self.active_work_users: set[int] = set()
        self.bank_reservations: dict[int, int] = {}
        self.init_db()

    async def cog_load(self):
        if not self.crypto_price_loop.is_running():
            self.crypto_price_loop.start()

    def cog_unload(self):
        self.crypto_price_loop.cancel()

    # --------------------------------------------------------
    # DB
    # --------------------------------------------------------

    def connect(self):
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self):
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS economy_users (
                    user_id INTEGER PRIMARY KEY,
                    wallet INTEGER NOT NULL DEFAULT 0,
                    work_xp INTEGER NOT NULL DEFAULT 0,
                    current_job TEXT NOT NULL DEFAULT 'changas',
                    last_work_at INTEGER NOT NULL DEFAULT 0,
                    last_crime_at INTEGER NOT NULL DEFAULT 0,
                    last_rob_at INTEGER NOT NULL DEFAULT 0,
                    arrested INTEGER NOT NULL DEFAULT 0,
                    bail_due INTEGER NOT NULL DEFAULT 0,
                    judicial_debt INTEGER NOT NULL DEFAULT 0,
                    protection_until INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS job_progress (
                    user_id INTEGER NOT NULL,
                    job_id TEXT NOT NULL,
                    xp INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, job_id)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bank_accounts (
                    user_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, account_type)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bank_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    account_type TEXT NOT NULL,
                    action TEXT NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    balance_after INTEGER NOT NULL DEFAULT 0,
                    details TEXT,
                    created_at INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS casino_state (
                    key TEXT PRIMARY KEY,
                    value REAL NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_market (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    buy_volume REAL NOT NULL DEFAULT 0,
                    sell_volume REAL NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_holdings (
                    user_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL DEFAULT 0,
                    cost_basis REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, symbol)
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)

            cur.execute("INSERT OR IGNORE INTO casino_state(key, value) VALUES('slots_jackpot', ?)", (SLOTS_JACKPOT_BASE,))

            now = int(time.time())
            for symbol, cfg in CRYPTO_CONFIG.items():
                cur.execute(
                    "INSERT OR IGNORE INTO crypto_market(symbol, name, price, updated_at) VALUES(?, ?, ?, ?)",
                    (symbol, cfg["name"], cfg["initial"], now),
                )
                exists = cur.execute("SELECT 1 FROM crypto_history WHERE symbol = ? LIMIT 1", (symbol,)).fetchone()
                if not exists:
                    cur.execute(
                        "INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)",
                        (symbol, cfg["initial"], now),
                    )

            conn.commit()
            conn.close()

    def ensure_user(self, user_id: int):
        now = int(time.time())
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO economy_users(user_id, created_at) VALUES(?, ?)",
                (user_id, now),
            )
            cur.execute(
                "INSERT OR IGNORE INTO bank_accounts(user_id, account_type, level, balance) VALUES(?, 'primary', 1, 0)",
                (user_id,),
            )
            cur.execute(
                "INSERT OR IGNORE INTO job_progress(user_id, job_id, xp) VALUES(?, 'changas', 0)",
                (user_id,),
            )
            conn.commit()
            conn.close()

    def get_user(self, user_id: int):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            row = conn.execute("SELECT * FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            conn.close()
            return row

    def get_bank(self, user_id: int, account_type: str = "primary"):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            row = conn.execute(
                "SELECT * FROM bank_accounts WHERE user_id = ? AND account_type = ?",
                (user_id, account_type),
            ).fetchone()
            conn.close()
            return row

    def bank_capacity(self, account) -> int:
        return BANK_LEVELS[int(account["level"])]["capacity"]

    def bank_free(self, user_id: int, account_type: str = "primary", include_reservation: bool = True) -> int:
        account = self.get_bank(user_id, account_type)
        if not account:
            return 0
        free = self.bank_capacity(account) - int(account["balance"])
        if account_type == "primary" and include_reservation:
            free -= self.bank_reservations.get(user_id, 0)
        return max(0, free)

    def log_bank(self, cur, user_id: int, account_type: str, action: str, amount: int, balance_after: int, details: str = ""):
        now = int(time.time())
        cur.execute(
            """
            INSERT INTO bank_history(user_id, account_type, action, amount, balance_after, details, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, account_type, action, int(amount), int(balance_after), details, now),
        )
        cur.execute("""
            DELETE FROM bank_history
            WHERE user_id = ?
              AND id NOT IN (
                  SELECT id FROM bank_history
                  WHERE user_id = ?
                  ORDER BY created_at DESC, id DESC
                  LIMIT 10
              )
        """, (user_id, user_id))

    # --------------------------------------------------------
    # ECONOMÍA / DEUDA
    # --------------------------------------------------------

    def salary_reference(self, user_id: int) -> int:
        user = self.get_user(user_id)
        job = JOBS.get(user["current_job"], JOBS["changas"])
        low, high = job["salary"]
        return int(round((low + high) / 2))

    def apply_income_withholding(self, cur, user_id: int, gross_income: int) -> tuple[int, int]:
        row = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
        debt = int(row["judicial_debt"])
        if debt <= 0 or gross_income <= 0:
            return gross_income, 0
        withheld = min(debt, int(round(gross_income * JUDICIAL_RATE)))
        cur.execute(
            "UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?",
            (withheld, user_id),
        )
        return gross_income - withheld, withheld

    def purchase_surcharge(self, cur, user_id: int, base_price: int) -> int:
        row = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
        debt = int(row["judicial_debt"])
        if debt <= 0:
            return 0
        return min(debt, int(round(base_price * JUDICIAL_RATE)))

    def try_debit_wallet(self, user_id: int, amount: int) -> bool:
        self.ensure_user(user_id)
        if amount <= 0:
            return False
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            row = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            if row["wallet"] < amount:
                conn.rollback()
                conn.close()
                return False
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))
            conn.commit()
            conn.close()
            return True

    def collect_penalty(self, user_id: int, amount: int) -> dict:
        """Cobra multa: Wallet -> Cuenta Principal -> Deuda Judicial."""
        self.ensure_user(user_id)
        amount = max(0, int(amount))
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            user = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            bank = cur.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (user_id,),
            ).fetchone()

            remaining = amount
            from_wallet = min(int(user["wallet"]), remaining)
            if from_wallet:
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (from_wallet, user_id))
                remaining -= from_wallet

            from_bank = min(int(bank["balance"]), remaining)
            if from_bank:
                new_balance = int(bank["balance"]) - from_bank
                cur.execute(
                    "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                    (new_balance, user_id),
                )
                self.log_bank(cur, user_id, "primary", "judicial_penalty", from_bank, new_balance, "Cobro de multa judicial")
                remaining -= from_bank

            if remaining:
                cur.execute(
                    "UPDATE economy_users SET judicial_debt = judicial_debt + ? WHERE user_id = ?",
                    (remaining, user_id),
                )

            conn.commit()
            conn.close()
            return {"wallet": from_wallet, "bank": from_bank, "debt": remaining}

    def arrest_user(self, user_id: int, bail: int):
        self.ensure_user(user_id)
        with self.db_lock:
            conn = self.connect()
            conn.execute(
                "UPDATE economy_users SET arrested = 1, bail_due = ? WHERE user_id = ?",
                (max(1, int(bail)), user_id),
            )
            conn.commit()
            conn.close()

    def is_arrested(self, user_id: int) -> bool:
        return bool(self.get_user(user_id)["arrested"])

    # --------------------------------------------------------
    # WORK
    # --------------------------------------------------------

    def settle_work(self, user_id: int, job_id: str, grade: str) -> dict:
        self.ensure_user(user_id)
        job = JOBS[job_id]
        base = random.randint(*job["salary"])
        gross = max(1, int(round(base * GRADE_MULTIPLIERS[grade])))
        work_xp_gain = max(1, int(round(random.randint(18, 30) * GRADE_XP_MULTIPLIERS[grade])))
        job_xp_gain = max(1, int(round(random.randint(15, 25) * GRADE_XP_MULTIPLIERS[grade])))

        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            before = cur.execute("SELECT work_xp FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            old_work_level = work_level_from_xp(before["work_xp"])

            net, withheld = self.apply_income_withholding(cur, user_id, gross)

            destination = job["payment"]
            if destination == "bank":
                account = cur.execute(
                    "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                    (user_id,),
                ).fetchone()
                capacity = BANK_LEVELS[account["level"]]["capacity"]
                if account["balance"] + net > capacity:
                    # La reserva debería impedirlo. Fallback seguro: Wallet.
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
            cur.execute(
                "INSERT OR IGNORE INTO job_progress(user_id, job_id, xp) VALUES(?, ?, 0)",
                (user_id, job_id),
            )
            cur.execute(
                "UPDATE job_progress SET xp = xp + ? WHERE user_id = ? AND job_id = ?",
                (job_xp_gain, user_id, job_id),
            )
            after = cur.execute("SELECT work_xp FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            new_work_level = work_level_from_xp(after["work_xp"])
            job_xp = cur.execute(
                "SELECT xp FROM job_progress WHERE user_id = ? AND job_id = ?",
                (user_id, job_id),
            ).fetchone()["xp"]
            job_level, job_progress, job_needed = job_level_progress(job_xp)

            conn.commit()
            conn.close()

        self.active_work_users.discard(user_id)
        self.bank_reservations.pop(user_id, None)

        return {
            "job": job,
            "grade": grade,
            "gross": gross,
            "net": net,
            "withheld": withheld,
            "work_xp_gain": work_xp_gain,
            "job_xp_gain": job_xp_gain,
            "old_work_level": old_work_level,
            "new_work_level": new_work_level,
            "job_level": job_level,
            "job_progress": job_progress,
            "job_needed": job_needed,
            "destination": destination,
        }

    def build_work_result_embed(self, result: dict, correct: bool, timeout: bool = False):
        grade = result["grade"]
        embed = discord.Embed(
            title=f"💼 Turno terminado · Nota {grade}",
            color=COLOR_SUCCESS if grade in {"S", "A", "B"} else COLOR_GOLD,
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
            embed.add_field(
                name="🎉 Subida de nivel",
                value=f"Work Level **{result['old_work_level']} → {result['new_work_level']}**",
                inline=False,
            )
        if result["destination"] == "wallet-fallback":
            embed.set_footer(text="Tu banco se quedó sin capacidad durante el turno; el pago fue enviado a Wallet.")
        return embed

    # --------------------------------------------------------
    # BANK
    # --------------------------------------------------------

    def deposit(self, user_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            user = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            account = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (user_id,),
            ).fetchone()
            reserved = self.bank_reservations.get(user_id, 0)
            free = BANK_LEVELS[account["level"]]["capacity"] - account["balance"] - reserved
            if user["wallet"] < amount:
                conn.rollback(); conn.close()
                return False, "No tienes suficiente dinero en Wallet."
            if free < amount:
                conn.rollback(); conn.close()
                return False, f"Tu Cuenta Principal no tiene capacidad suficiente. Espacio disponible: **{money(max(0, free))}**."
            new_balance = account["balance"] + amount
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (amount, user_id))
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            self.log_bank(cur, user_id, "primary", "deposit", amount, new_balance, "Depósito desde Wallet")
            conn.commit(); conn.close()
            return True, f"🏦 Depositaste **{money(amount)}** en tu Cuenta Principal."

    def withdraw(self, user_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            account = cur.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (user_id,),
            ).fetchone()
            if account["balance"] < amount:
                conn.rollback(); conn.close()
                return False, "No tienes suficiente dinero en tu Cuenta Principal."
            new_balance = account["balance"] - amount
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (amount, user_id))
            self.log_bank(cur, user_id, "primary", "withdraw", amount, new_balance, "Retiro hacia Wallet")
            conn.commit(); conn.close()
            return True, f"💵 Retiraste **{money(amount)}** hacia tu Wallet."

    def transfer(self, sender_id: int, receiver_id: int, amount: int) -> tuple[bool, str]:
        self.ensure_user(sender_id)
        self.ensure_user(receiver_id)
        if amount <= 0:
            return False, "La cantidad debe ser mayor que 0."
        fee = max(1, int(round(amount * TRANSFER_FEE_RATE)))
        total = amount + fee
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            sender = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (sender_id,),
            ).fetchone()
            receiver = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (receiver_id,),
            ).fetchone()
            receiver_reserved = self.bank_reservations.get(receiver_id, 0)
            receiver_free = BANK_LEVELS[receiver["level"]]["capacity"] - receiver["balance"] - receiver_reserved

            if sender["balance"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en tu Cuenta Principal ({money(amount)} + {money(fee)} de comisión)."
            # Acuerdo: debe haber capacidad para el importe completo antes de cualquier retención.
            if receiver_free < amount:
                conn.rollback(); conn.close()
                return False, "La Cuenta Principal del destinatario no tiene capacidad para recibir la transferencia completa."

            sender_new = sender["balance"] - total
            net_received, withheld = self.apply_income_withholding(cur, receiver_id, amount)
            receiver_new = receiver["balance"] + net_received

            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (sender_new, sender_id),
            )
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (receiver_new, receiver_id),
            )
            self.log_bank(cur, sender_id, "primary", "transfer_sent", amount, sender_new, f"Transferencia a {receiver_id}")
            self.log_bank(cur, sender_id, "primary", "transfer_fee", fee, sender_new, f"Comisión 5% por transferencia a {receiver_id}")
            self.log_bank(cur, receiver_id, "primary", "transfer_received", amount, receiver_new, f"Transferencia de {sender_id}; retención {withheld}")
            conn.commit(); conn.close()

            text = f"✅ Transferiste **{money(amount)}** a <@{receiver_id}>. Comisión: **{money(fee)}**."
            if withheld:
                text += f"\n⚖️ Al destinatario se le retuvieron **{money(withheld)}** para su Deuda Judicial."
            return True, text

    # --------------------------------------------------------
    # PROTECCIÓN / ROB
    # --------------------------------------------------------

    def buy_rob_protection(self, user_id: int) -> tuple[bool, str]:
        self.ensure_user(user_id)
        now = int(time.time())
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            user = cur.execute(
                "SELECT wallet, judicial_debt, protection_until FROM economy_users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            if user["protection_until"] > now:
                conn.rollback(); conn.close()
                return False, f"Ya tienes protección activa hasta <t:{user['protection_until']}:R>."
            surcharge = min(int(user["judicial_debt"]), int(round(ROB_PROTECTION_COST * JUDICIAL_RATE)))
            total = ROB_PROTECTION_COST + surcharge
            if user["wallet"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en Wallet para comprar la protección."
            until = now + ROB_PROTECTION_SECONDS
            cur.execute(
                "UPDATE economy_users SET wallet = wallet - ?, judicial_debt = judicial_debt - ?, protection_until = ? WHERE user_id = ?",
                (total, surcharge, until, user_id),
            )
            conn.commit(); conn.close()

            text = f"🛡️ Protección activada por **30 minutos**. Costo: **{money(ROB_PROTECTION_COST)}**."
            if surcharge:
                text += f" Recargo judicial: **{money(surcharge)}**."
            return True, text

    # --------------------------------------------------------
    # CASINO
    # --------------------------------------------------------

    def credit_casino_return(self, user_id: int, stake: int, total_return: int) -> tuple[int, int]:
        self.ensure_user(user_id)
        total_return = max(0, int(total_return))
        net_gain = max(0, total_return - int(stake))
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            withheld = 0
            if net_gain > 0:
                debt = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()["judicial_debt"]
                withheld = min(int(debt), int(round(net_gain * JUDICIAL_RATE)))
                if withheld:
                    cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (withheld, user_id))
            credited = total_return - withheld
            if credited:
                cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (credited, user_id))
            conn.commit(); conn.close()
            return credited, withheld

    def resolve_coinflip(self, creator_id: int, opponent_id: int, bet: int, creator_choice: str) -> dict:
        self.ensure_user(creator_id)
        self.ensure_user(opponent_id)
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            c = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (creator_id,)).fetchone()["wallet"]
            o = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (opponent_id,)).fetchone()["wallet"]
            if c < bet:
                conn.rollback(); conn.close()
                return {"ok": False, "message": "El creador ya no tiene suficiente Wallet para cubrir la apuesta."}
            if o < bet:
                conn.rollback(); conn.close()
                return {"ok": False, "message": "No tienes suficiente Wallet para cubrir la apuesta."}
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id IN (?, ?)", (bet, creator_id, opponent_id))
            conn.commit(); conn.close()

        result = random.choice(["cara", "cruz"])
        winner_id = creator_id if result == creator_choice else opponent_id
        pool = bet * 2
        fee = max(1, int(round(pool * COINFLIP_FEE_RATE)))
        total_return = pool - fee
        credited, withheld = self.credit_casino_return(winner_id, bet, total_return)
        return {
            "ok": True,
            "result": "Cara" if result == "cara" else "Cruz",
            "winner_id": winner_id,
            "pool": pool,
            "fee": fee,
            "credited": credited,
            "withheld": withheld,
        }

    # --------------------------------------------------------
    # CRYPTO
    # --------------------------------------------------------

    def crypto_snapshot(self):
        with self.db_lock:
            conn = self.connect()
            rows = conn.execute("SELECT * FROM crypto_market ORDER BY symbol").fetchall()
            conn.close()
            return rows

    def crypto_buy(self, user_id: int, symbol: str, amount: int) -> tuple[bool, str]:
        symbol = symbol.upper()
        self.ensure_user(user_id)
        if symbol not in CRYPTO_CONFIG:
            return False, "Criptomoneda inválida. Usa IC, NVA o FLX."
        if amount <= 0:
            return False, "El monto debe ser mayor que 0."
        fee = max(1, int(round(amount * CRYPTO_FEE_RATE)))
        total = amount + fee
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            bank = cur.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (user_id,),
            ).fetchone()
            market = cur.execute("SELECT price FROM crypto_market WHERE symbol = ?", (symbol,)).fetchone()
            if bank["balance"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en tu Cuenta Principal (incluye 1% de comisión)."
            quantity = amount / float(market["price"])
            new_balance = int(bank["balance"]) - total
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            cur.execute(
                "INSERT OR IGNORE INTO crypto_holdings(user_id, symbol, quantity, cost_basis) VALUES(?, ?, 0, 0)",
                (user_id, symbol),
            )
            cur.execute(
                "UPDATE crypto_holdings SET quantity = quantity + ?, cost_basis = cost_basis + ? WHERE user_id = ? AND symbol = ?",
                (quantity, amount, user_id, symbol),
            )
            cur.execute("UPDATE crypto_market SET buy_volume = buy_volume + ? WHERE symbol = ?", (amount, symbol))
            self.log_bank(cur, user_id, "primary", "crypto_buy", total, new_balance, f"Compra {symbol}: {quantity:.8f} unidades")
            conn.commit(); conn.close()
            return True, f"📈 Compraste **{quantity:.8f} {symbol}** por **{money(amount)}** + **{money(fee)}** de comisión."

    def crypto_sell(self, user_id: int, symbol: str, percent: int) -> tuple[bool, str]:
        symbol = symbol.upper()
        self.ensure_user(user_id)
        if symbol not in CRYPTO_CONFIG:
            return False, "Criptomoneda inválida. Usa IC, NVA o FLX."
        if percent < 1 or percent > 100:
            return False, "El porcentaje debe estar entre 1 y 100."

        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            holding = cur.execute(
                "SELECT quantity, cost_basis FROM crypto_holdings WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            ).fetchone()
            if not holding or holding["quantity"] <= 0:
                conn.rollback(); conn.close()
                return False, f"No tienes {symbol} para vender."

            market = cur.execute("SELECT price FROM crypto_market WHERE symbol = ?", (symbol,)).fetchone()
            qty = float(holding["quantity"]) * (percent / 100)
            if percent == 100:
                qty = float(holding["quantity"])
            cost_portion = float(holding["cost_basis"]) * (qty / float(holding["quantity"]))
            gross = qty * float(market["price"])
            fee = max(1, int(round(gross * CRYPTO_FEE_RATE)))
            after_fee = max(0, int(round(gross)) - fee)
            profit = max(0, int(round(gross - cost_portion)))

            user = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            withheld = min(int(user["judicial_debt"]), int(round(profit * JUDICIAL_RATE))) if profit > 0 else 0
            credited = max(0, after_fee - withheld)

            bank = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'",
                (user_id,),
            ).fetchone()
            reserved = self.bank_reservations.get(user_id, 0)
            free = BANK_LEVELS[bank["level"]]["capacity"] - bank["balance"] - reserved
            if free < credited:
                conn.rollback(); conn.close()
                return False, f"Tu Cuenta Principal no tiene espacio suficiente para acreditar **{money(credited)}**."

            remaining_qty = max(0.0, float(holding["quantity"]) - qty)
            remaining_cost = max(0.0, float(holding["cost_basis"]) - cost_portion)
            new_balance = int(bank["balance"]) + credited
            cur.execute(
                "UPDATE crypto_holdings SET quantity = ?, cost_basis = ? WHERE user_id = ? AND symbol = ?",
                (remaining_qty, remaining_cost, user_id, symbol),
            )
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            if withheld:
                cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (withheld, user_id))
            cur.execute("UPDATE crypto_market SET sell_volume = sell_volume + ? WHERE symbol = ?", (gross, symbol))
            self.log_bank(cur, user_id, "primary", "crypto_sell", credited, new_balance, f"Venta {symbol}: {qty:.8f} unidades; fee {fee}; retención {withheld}")
            conn.commit(); conn.close()

            text = f"📉 Vendiste **{qty:.8f} {symbol}**. Bruto: **{money(gross)}** · Comisión: **{money(fee)}** · Acreditado: **{money(credited)}**."
            if withheld:
                text += f"\n⚖️ Retención judicial sobre ganancia: **{money(withheld)}**."
            return True, text

    @tasks.loop(minutes=1)
    async def crypto_price_loop(self):
        with self.db_lock:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            now = int(time.time())
            for symbol, cfg in CRYPTO_CONFIG.items():
                row = cur.execute(
                    "SELECT price, buy_volume, sell_volume, updated_at FROM crypto_market WHERE symbol = ?",
                    (symbol,),
                ).fetchone()
                if now - int(row["updated_at"]) < CRYPTO_UPDATE_SECONDS:
                    continue
                price = float(row["price"])
                buy = float(row["buy_volume"])
                sell = float(row["sell_volume"])

                auto_move = random.uniform(cfg["auto_min"], cfg["auto_max"])
                if random.random() < 0.5:
                    auto_move *= -1

                total_volume = buy + sell
                if total_volume > 0:
                    pressure = (buy - sell) / total_volume
                    player_move = pressure * cfg["player_max"]
                else:
                    player_move = 0.0

                total_move = auto_move + player_move
                new_price = max(1.0, round(price * (1 + total_move), 4))

                cur.execute(
                    "UPDATE crypto_market SET price = ?, buy_volume = 0, sell_volume = 0, updated_at = ? WHERE symbol = ?",
                    (new_price, now, symbol),
                )
                cur.execute(
                    "INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)",
                    (symbol, new_price, now),
                )
                cur.execute("""
                    DELETE FROM crypto_history
                    WHERE symbol = ?
                      AND id NOT IN (
                          SELECT id FROM crypto_history
                          WHERE symbol = ?
                          ORDER BY created_at DESC, id DESC
                          LIMIT ?
                      )
                """, (symbol, symbol, CRYPTO_HISTORY_KEEP))
            conn.commit(); conn.close()

    @crypto_price_loop.before_loop
    async def before_crypto_loop(self):
        await self.bot.wait_until_ready()

    # ========================================================
    # COMMANDS /lude
    # ========================================================

    @lude.command(name="estado", description="Muestra tu estado económico general.")
    async def estado(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        primary = self.get_bank(interaction.user.id, "primary")
        additional = self.get_bank(interaction.user.id, "additional")
        level, progress, needed = work_level_progress(user["work_xp"])
        job = JOBS.get(user["current_job"], JOBS["changas"])

        embed = discord.Embed(title="🏙️ Interlude · Estado económico", color=COLOR)
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
        for job_id, job in sorted(JOBS.items(), key=lambda item: (item[1]["level"], item[1]["name"])):
            unlocked = level >= job["level"]
            current = " ⭐" if user["current_job"] == job_id else ""
            pay = "Banco" if job["payment"] == "bank" else "Wallet"
            icon = "✅" if unlocked else "🔒"
            lines.append(f"{icon} **Lv.{job['level']} · {job['name']}** — {money(job['salary'][0])}–{money(job['salary'][1])} · {pay}{current}")
        embed = discord.Embed(title=f"💼 Mercado laboral · Work Level {level}", description="\n".join(lines), color=COLOR)
        await interaction.response.send_message(embed=embed)

    @lude.command(name="empleo", description="Cambia a un trabajo que tengas desbloqueado.")
    async def empleo(self, interaction: discord.Interaction, trabajo: str):
        trabajo = trabajo.lower()
        if trabajo not in JOBS:
            await interaction.response.send_message("Trabajo inválido.", ephemeral=True)
            return
        user = self.get_user(interaction.user.id)
        level = work_level_from_xp(user["work_xp"])
        job = JOBS[trabajo]
        if level < job["level"]:
            await interaction.response.send_message(f"Necesitas Work Level **{job['level']}**.", ephemeral=True)
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
        tester_role = interaction.guild.get_role(TESTER_ROLE_ID) if interaction.guild else None
        if (
            not isinstance(member, discord.Member)
            or tester_role is None
            or member.top_role.position < tester_role.position
        ):
            return []
        user = self.get_user(interaction.user.id)
        level = work_level_from_xp(user["work_xp"])
        current_lower = current.lower()
        results = []
        for job_id, job in JOBS.items():
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
            await interaction.response.send_message("🚔 Estás arrestado. Debes pagar tu fianza antes de trabajar.", ephemeral=True)
            return
        if uid in self.active_work_users:
            await interaction.response.send_message("Ya tienes un turno de trabajo activo.", ephemeral=True)
            return
        now = int(time.time())
        remaining = WORK_COOLDOWN - (now - user["last_work_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a trabajar en **{format_seconds(remaining)}**.", ephemeral=True)
            return

        job_id = user["current_job"]
        job = JOBS.get(job_id, JOBS["changas"])
        if job["payment"] == "bank":
            max_salary = int(math.ceil(job["salary"][1] * GRADE_MULTIPLIERS["S"]))
            if self.bank_free(uid, "primary", include_reservation=False) < max_salary:
                await interaction.response.send_message(
                    f"🏦 Este empleo paga por Bank of Interlude. Necesitas al menos **{money(max_salary)}** de capacidad libre en tu Cuenta Principal antes de iniciar el turno.",
                    ephemeral=True,
                )
                return
            self.bank_reservations[uid] = max_salary

        self.active_work_users.add(uid)
        with self.db_lock:
            conn = self.connect()
            conn.execute("UPDATE economy_users SET last_work_at = ? WHERE user_id = ?", (now, uid))
            conn.commit(); conn.close()

        prompt, options, correct = random.choice(WORK_MINIGAMES.get(job["style"], WORK_MINIGAMES["general"]))
        view = WorkView(self, uid, job_id, prompt, options, correct)
        embed = discord.Embed(title=f"💼 {job['name']} · Turno", description=prompt, color=COLOR)
        embed.set_footer(text="Tienes 30 segundos para decidir.")
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @lude.command(name="banco", description="Muestra tus cuentas de Bank of Interlude.")
    async def banco(self, interaction: discord.Interaction):
        uid = interaction.user.id
        primary = self.get_bank(uid, "primary")
        additional = self.get_bank(uid, "additional")
        embed = discord.Embed(title="🏦 Bank of Interlude", color=COLOR)
        embed.add_field(
            name=f"Cuenta Principal · Nivel {primary['level']}",
            value=f"**{money(primary['balance'])} / {money(self.bank_capacity(primary))}**",
            inline=False,
        )
        if additional:
            embed.add_field(
                name=f"Cuenta Adicional · Nivel {additional['level']}",
                value=f"**{money(additional['balance'])} / {money(self.bank_capacity(additional))}**",
                inline=False,
            )
        else:
            embed.add_field(name="Cuenta Adicional", value="No abierta. Requiere Principal Nivel 7.", inline=False)
        await interaction.response.send_message(embed=embed)

    @lude.command(name="depositar", description="Deposita Wallet en tu Cuenta Principal.")
    async def depositar(self, interaction: discord.Interaction, cantidad: int):
        ok, text = self.deposit(interaction.user.id, cantidad)
        await interaction.response.send_message(text, ephemeral=not ok)

    @lude.command(name="retirar", description="Retira dinero de tu Cuenta Principal a Wallet.")
    async def retirar(self, interaction: discord.Interaction, cantidad: int):
        ok, text = self.withdraw(interaction.user.id, cantidad)
        await interaction.response.send_message(text, ephemeral=not ok)

    @lude.command(name="transferir", description="Transfiere desde tu Cuenta Principal a otro usuario.")
    async def transferir(self, interaction: discord.Interaction, usuario: discord.Member, cantidad: int):
        if usuario.bot or usuario.id == interaction.user.id:
            await interaction.response.send_message("El destinatario debe ser otro usuario real.", ephemeral=True)
            return
        ok, text = self.transfer(interaction.user.id, usuario.id, cantidad)
        await interaction.response.send_message(text, ephemeral=not ok)

    @lude.command(name="mejorar-banco", description="Mejora una cuenta de Bank of Interlude.")
    @app_commands.choices(cuenta=[
        app_commands.Choice(name="Principal", value="primary"),
        app_commands.Choice(name="Adicional", value="additional"),
    ])
    async def mejorar_banco(self, interaction: discord.Interaction, cuenta: app_commands.Choice[str]):
        uid = interaction.user.id
        account_type = cuenta.value
        account = self.get_bank(uid, account_type)
        if not account:
            await interaction.response.send_message("No tienes esa cuenta bancaria.", ephemeral=True)
            return
        level = int(account["level"])
        if level >= 7:
            await interaction.response.send_message("Esa cuenta ya está en Nivel 7.", ephemeral=True)
            return
        next_level = level + 1
        if account_type == "primary":
            cost = BANK_LEVELS[next_level]["upgrade_cost"]
        else:
            cost = ADDITIONAL_UPGRADE_COSTS[next_level]

        # El upgrade se paga desde Wallet para no mezclar capacidad con el costo.
        user = self.get_user(uid)
        if user["wallet"] < cost:
            await interaction.response.send_message(f"Necesitas **{money(cost)}** en Wallet.", ephemeral=True)
            return
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (cost, uid))
            cur.execute("UPDATE bank_accounts SET level = ? WHERE user_id = ? AND account_type = ?", (next_level, uid, account_type))
            current_balance = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, account_type)).fetchone()["balance"]
            self.log_bank(cur, uid, account_type, "bank_upgrade", cost, current_balance, f"Mejora a Nivel {next_level}")
            conn.commit(); conn.close()
        await interaction.response.send_message(f"🏦 **{cuenta.name}** mejorada a **Nivel {next_level}**. Nueva capacidad: **{money(BANK_LEVELS[next_level]['capacity'])}**.")

    @lude.command(name="abrir-adicional", description="Abre tu Cuenta Adicional al alcanzar Principal Nivel 7.")
    async def abrir_adicional(self, interaction: discord.Interaction):
        uid = interaction.user.id
        primary = self.get_bank(uid, "primary")
        if int(primary["level"]) < 7:
            await interaction.response.send_message("Tu Cuenta Principal debe estar en **Nivel 7**.", ephemeral=True)
            return
        if self.get_bank(uid, "additional"):
            await interaction.response.send_message("Ya tienes una Cuenta Adicional.", ephemeral=True)
            return
        user = self.get_user(uid)
        if user["wallet"] < ADDITIONAL_OPEN_COST:
            await interaction.response.send_message(f"Necesitas **{money(ADDITIONAL_OPEN_COST)}** en Wallet.", ephemeral=True)
            return
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (ADDITIONAL_OPEN_COST, uid))
            cur.execute(
                "INSERT INTO bank_accounts(user_id, account_type, level, balance) VALUES(?, 'additional', ?, 0)",
                (uid, ADDITIONAL_OPEN_LEVEL),
            )
            self.log_bank(cur, uid, "additional", "additional_open", ADDITIONAL_OPEN_COST, 0, "Apertura de Cuenta Adicional Nivel 4")
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
            await interaction.response.send_message("La cantidad debe ser mayor que 0.", ephemeral=True)
            return
        if not self.get_bank(uid, "additional"):
            await interaction.response.send_message("No tienes Cuenta Adicional.", ephemeral=True)
            return
        src, dst = ("primary", "additional") if destino.value == "p2a" else ("additional", "primary")
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            src_row = cur.execute("SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, src)).fetchone()
            dst_row = cur.execute("SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = ?", (uid, dst)).fetchone()
            dst_reserved = self.bank_reservations.get(uid, 0) if dst == "primary" else 0
            free = BANK_LEVELS[dst_row["level"]]["capacity"] - dst_row["balance"] - dst_reserved
            if src_row["balance"] < cantidad:
                conn.rollback(); conn.close()
                await interaction.response.send_message("Saldo insuficiente en la cuenta de origen.", ephemeral=True)
                return
            if free < cantidad:
                conn.rollback(); conn.close()
                await interaction.response.send_message("La cuenta de destino no tiene capacidad suficiente.", ephemeral=True)
                return
            src_new = src_row["balance"] - cantidad
            dst_new = dst_row["balance"] + cantidad
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
                "SELECT * FROM bank_history WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 10",
                (uid,),
            ).fetchall()
            conn.close()
        if not rows:
            await interaction.response.send_message("Todavía no tienes movimientos bancarios.", ephemeral=True)
            return
        labels = {
            "deposit": "Depósito", "withdraw": "Retiro", "transfer_sent": "Transferencia enviada",
            "transfer_received": "Transferencia recibida", "transfer_fee": "Comisión transferencia",
            "internal_out": "Movimiento interno", "internal_in": "Movimiento interno",
            "bank_upgrade": "Mejora bancaria", "additional_open": "Apertura adicional",
            "salary": "Salario", "judicial_penalty": "Multa judicial",
            "crypto_buy": "Compra cripto", "crypto_sell": "Venta cripto", "bail": "Fianza",
            "debt_payment": "Pago de deuda",
        }
        lines = []
        for row in rows:
            when = f"<t:{row['created_at']}:R>"
            lines.append(f"**{labels.get(row['action'], row['action'])}** · {money(row['amount'])} · saldo {money(row['balance_after'])} · {when}")
        embed = discord.Embed(title="📜 Bank of Interlude · Últimos 10", description="\n".join(lines), color=COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @lude.command(name="deuda", description="Consulta tu Deuda Judicial.")
    async def deuda(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        embed = discord.Embed(title="⚖️ Deuda Judicial", color=COLOR_DANGER if user["judicial_debt"] else COLOR_SUCCESS)
        embed.description = f"Deuda actual: **{money(user['judicial_debt'])}**."
        if user["judicial_debt"]:
            embed.add_field(name="Retención", value="25% de ingresos legítimos y recargo en compras hasta cancelar la deuda.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @lude.command(name="pagar-deuda", description="Paga voluntariamente parte o toda tu Deuda Judicial.")
    @app_commands.choices(origen=[
        app_commands.Choice(name="Wallet", value="wallet"),
        app_commands.Choice(name="Cuenta Principal", value="bank"),
    ])
    async def pagar_deuda(self, interaction: discord.Interaction, cantidad: int, origen: app_commands.Choice[str]):
        uid = interaction.user.id
        user = self.get_user(uid)
        debt = int(user["judicial_debt"])
        if debt <= 0:
            await interaction.response.send_message("No tienes Deuda Judicial.", ephemeral=True)
            return
        if cantidad <= 0:
            await interaction.response.send_message("La cantidad debe ser mayor que 0.", ephemeral=True)
            return
        pay = min(cantidad, debt)
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            if origen.value == "wallet":
                wallet = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (uid,)).fetchone()["wallet"]
                if wallet < pay:
                    conn.rollback(); conn.close()
                    await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
                    return
                cur.execute("UPDATE economy_users SET wallet = wallet - ?, judicial_debt = judicial_debt - ? WHERE user_id = ?", (pay, pay, uid))
            else:
                bank = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (uid,)).fetchone()
                if bank["balance"] < pay:
                    conn.rollback(); conn.close()
                    await interaction.response.send_message("No tienes suficiente saldo en la Cuenta Principal.", ephemeral=True)
                    return
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
            await interaction.response.send_message("No estás arrestado.", ephemeral=True)
            return
        bail = int(user["bail_due"])
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            u = cur.execute("SELECT wallet FROM economy_users WHERE user_id = ?", (uid,)).fetchone()
            b = cur.execute("SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (uid,)).fetchone()
            from_wallet = from_bank = financed = 0
            if metodo.value == "wallet":
                if u["wallet"] < bail:
                    conn.rollback(); conn.close()
                    await interaction.response.send_message("Tu Wallet no alcanza. Usa el método Automático para permitir financiación.", ephemeral=True)
                    return
                from_wallet = bail
            elif metodo.value == "bank":
                if b["balance"] < bail:
                    conn.rollback(); conn.close()
                    await interaction.response.send_message("Tu Cuenta Principal no alcanza. Usa el método Automático para permitir financiación.", ephemeral=True)
                    return
                from_bank = bail
            else:
                remaining = bail
                from_wallet = min(u["wallet"], remaining); remaining -= from_wallet
                from_bank = min(b["balance"], remaining); remaining -= from_bank
                financed = remaining

            if from_wallet:
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (from_wallet, uid))
            if from_bank:
                new_balance = b["balance"] - from_bank
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

    @lude.command(name="crime", description="Comete un crimen aleatorio contra el sistema.")
    async def crime(self, interaction: discord.Interaction):
        uid = interaction.user.id
        user = self.get_user(uid)
        if user["arrested"]:
            await interaction.response.send_message("🚔 Estás arrestado. Debes pagar tu fianza antes de cometer otro crimen.", ephemeral=True)
            return
        now = int(time.time())
        remaining = CRIME_COOLDOWN - (now - user["last_crime_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a usar `/lude crime` en **{format_seconds(remaining)}**.", ephemeral=True)
            return

        keys = list(CRIME_CATEGORIES)
        category_key = random.choices(keys, weights=[CRIME_CATEGORIES[k]["weight"] for k in keys], k=1)[0]
        cat = CRIME_CATEGORIES[category_key]
        crime_name = random.choice(cat["crimes"])
        salary = self.salary_reference(uid)

        with self.db_lock:
            conn = self.connect(); conn.execute("UPDATE economy_users SET last_crime_at = ? WHERE user_id = ?", (now, uid)); conn.commit(); conn.close()

        success = random.random() < cat["success"]
        embed = discord.Embed(title=f"🚨 {crime_name}", color=COLOR_DANGER)
        embed.add_field(name="Categoría", value=cat["name"], inline=True)
        embed.add_field(name="Salario de referencia", value=money(salary), inline=True)

        if success:
            multiplier = random.uniform(*cat["reward"])
            reward = max(1, int(round(salary * multiplier)))
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (reward, uid)); conn.commit(); conn.close()
            embed.description = f"✅ **El crimen salió bien.** Ganaste **{money(reward)}** en efectivo."
            embed.set_footer(text="Los ingresos de crime no sufren retención de Bank of Interlude.")
        else:
            fine = max(1, int(round(salary * random.uniform(*cat["fine"]))))
            penalty = self.collect_penalty(uid, fine)
            arrested = random.random() < cat["arrest_if_fail"]
            embed.description = f"❌ **El crimen fracasó.** Multa: **{money(fine)}**."
            if penalty["debt"]:
                embed.description += f"\n⚖️ **{money(penalty['debt'])}** de la multa pasó a Deuda Judicial por falta de fondos."
            if arrested:
                bail = max(1, int(round(salary * cat["bail"])))
                self.arrest_user(uid, bail)
                embed.description += f"\n🚔 Además, fuiste **arrestado**. Fianza: **{money(bail)}**. Usa `/lude fianza`."
            else:
                embed.description += "\n🏃 Lograste evitar el arresto."
        await interaction.response.send_message(embed=embed)

    @lude.command(name="rob", description="Intenta robar una parte aleatoria del Wallet de otro usuario.")
    async def rob(self, interaction: discord.Interaction, usuario: discord.Member):
        thief_id = interaction.user.id
        victim_id = usuario.id
        if usuario.bot or victim_id == thief_id:
            await interaction.response.send_message("Debes elegir a otro usuario real.", ephemeral=True)
            return
        thief = self.get_user(thief_id)
        victim = self.get_user(victim_id)
        if thief["arrested"]:
            await interaction.response.send_message("🚔 Estás arrestado. No puedes robar hasta pagar tu fianza.", ephemeral=True)
            return
        now = int(time.time())
        remaining = ROB_COOLDOWN - (now - thief["last_rob_at"])
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Puedes volver a robar en **{format_seconds(remaining)}**.", ephemeral=True)
            return

        # La protección se verifica antes del mínimo: intentar robar a una persona protegida es una trampa.
        if victim["protection_until"] > now:
            theft_percent = random.randint(1, 65)
            bail = max(1, int(round(self.salary_reference(thief_id) * rob_bail_multiplier(theft_percent))))
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET last_rob_at = ? WHERE user_id = ?", (now, thief_id)); conn.commit(); conn.close()
            self.arrest_user(thief_id, bail)
            await interaction.response.send_message(
                f"🛡️ {usuario.mention} tenía **protección anti-robo activa**.\n🚔 Fuiste arrestado automáticamente. Fianza: **{money(bail)}**.",
            )
            return

        min_wallet = self.salary_reference(victim_id) * 2
        if victim["wallet"] < min_wallet:
            await interaction.response.send_message(
                f"💸 {usuario.mention} no puede ser robado ahora. Debe llevar al menos **{money(min_wallet)}** en Wallet.\nTu cooldown **no fue consumido**.",
                ephemeral=True,
            )
            return

        theft_percent = random.randint(1, 65)
        success_chance = 100 if theft_percent == 1 else 100 - theft_percent
        attempted = max(1, int(math.floor(victim["wallet"] * theft_percent / 100)))

        with self.db_lock:
            conn = self.connect(); conn.execute("UPDATE economy_users SET last_rob_at = ? WHERE user_id = ?", (now, thief_id)); conn.commit(); conn.close()

        success = random.randint(1, 100) <= success_chance
        embed = discord.Embed(title="🔫 Intento de robo", color=COLOR_DANGER)
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
                    await interaction.response.send_message("El Wallet de la víctima cambió antes de resolver el robo.", ephemeral=True)
                    return
                cur.execute("UPDATE economy_users SET wallet = wallet - ? WHERE user_id = ?", (actual, victim_id))
                cur.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (actual, thief_id))
                conn.commit(); conn.close()
            embed.description = f"✅ Robo exitoso. <@{thief_id}> robó **{money(actual)}**."
            view = ProtectionOfferView(self, victim_id)
            await interaction.response.send_message(content=usuario.mention, embed=embed, view=view)
        else:
            fine = max(1, int(round(attempted * 0.25)))
            penalty = self.collect_penalty(thief_id, fine)
            protection_until = now + ROB_PROTECTION_SECONDS
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET protection_until = ? WHERE user_id = ?", (protection_until, victim_id)); conn.commit(); conn.close()
            embed.description = (
                f"❌ El robo falló. <@{thief_id}> fue multado con **{money(fine)}**.\n"
                f"🛡️ {usuario.mention} recibió **30 minutos de protección gratis**."
            )
            if penalty["debt"]:
                embed.description += f"\n⚖️ **{money(penalty['debt'])}** de la multa pasó a Deuda Judicial."
            await interaction.response.send_message(embed=embed)

    @lude.command(name="slots", description="Apuesta en Slots. El 5% alimenta el Jackpot Global.")
    async def slots(self, interaction: discord.Interaction, apuesta: int):
        uid = interaction.user.id
        if apuesta < CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(CASINO_MIN_BET)}**.", ephemeral=True)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
            return

        symbols = ["🍒", "🍋", "🔔", "💎", "7️⃣"]
        weights = [40, 28, 18, 10, 4]
        reels = random.choices(symbols, weights=weights, k=3)

        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            jackpot = float(cur.execute("SELECT value FROM casino_state WHERE key = 'slots_jackpot'").fetchone()["value"])
            contribution = max(1, int(round(apuesta * SLOTS_JACKPOT_CONTRIBUTION)))
            jackpot += contribution
            cur.execute("UPDATE casino_state SET value = ? WHERE key = 'slots_jackpot'", (jackpot,))
            conn.commit(); conn.close()

        total_return = 0
        result_name = "Sin premio"
        if reels == ["7️⃣", "7️⃣", "7️⃣"]:
            total_return = apuesta + int(round(jackpot))
            result_name = "🎉 JACKPOT GLOBAL"
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE casino_state SET value = ? WHERE key = 'slots_jackpot'", (SLOTS_JACKPOT_BASE,)); conn.commit(); conn.close()
        elif reels[0] == reels[1] == reels[2] == "💎":
            total_return = apuesta * 5; result_name = "💎 ×5"
        elif reels[0] == reels[1] == reels[2] == "🔔":
            total_return = apuesta * 3; result_name = "🔔 ×3"
        elif reels[0] == reels[1] == reels[2] == "🍋":
            total_return = apuesta * 2; result_name = "🍋 ×2"
        elif reels[0] == reels[1] == reels[2] == "🍒":
            total_return = int(round(apuesta * 1.5)); result_name = "🍒 ×1.5"
        elif reels.count("🍒") >= 2:
            total_return = int(round(apuesta * 0.5)); result_name = "🍒🍒 ×0.5"

        credited, withheld = (0, 0)
        if total_return:
            credited, withheld = self.credit_casino_return(uid, apuesta, total_return)

        embed = discord.Embed(title="🎰 Slots", description=" │ ".join(reels), color=COLOR_GOLD)
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
        if apuesta < CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(CASINO_MIN_BET)}**.", ephemeral=True)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
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
        if apuesta < CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(CASINO_MIN_BET)}**.", ephemeral=True)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
            return
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        number = random.randint(0, 36)
        result_color = "green" if number == 0 else ("red" if number in red_numbers else "black")
        won = color.value == result_color
        multiplier = 36 if color.value == "green" else 2
        total_return = apuesta * multiplier if won else 0
        credited, withheld = self.credit_casino_return(uid, apuesta, total_return) if won else (0, 0)
        names = {"red": "🔴 Rojo", "black": "⚫ Negro", "green": "🟢 Verde"}
        embed = discord.Embed(title="🎡 Ruleta", color=COLOR_GOLD)
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
            await interaction.response.send_message("Debes desafiar a otro usuario real.", ephemeral=True)
            return
        if apuesta < CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(CASINO_MIN_BET)}**.", ephemeral=True)
            return
        creator = self.get_user(interaction.user.id)
        opponent = self.get_user(usuario.id)
        if creator["wallet"] < apuesta:
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
            return
        if opponent["wallet"] < apuesta:
            await interaction.response.send_message(f"{usuario.mention} no tiene suficiente Wallet para aceptar esa apuesta.", ephemeral=True)
            return
        view = CoinflipView(self, interaction.user.id, usuario.id, apuesta, eleccion.value)
        embed = discord.Embed(title="🪙 Desafío Coinflip PvP", color=COLOR_GOLD)
        embed.description = (
            f"{interaction.user.mention} desafía a {usuario.mention}.\n"
            f"Apuesta por jugador: **{money(apuesta)}**\n"
            f"{interaction.user.mention} eligió **{eleccion.name}**.\n"
            f"Comisión del casino: **5% del pozo**."
        )
        embed.set_footer(text="El desafío expira en 60 segundos. El dinero se descuenta solo al aceptar.")
        await interaction.response.send_message(content=usuario.mention, embed=embed, view=view)
        view.message = await interaction.original_response()

    @lude.command(name="crypto", description="Muestra el mercado actual de criptomonedas.")
    async def crypto(self, interaction: discord.Interaction):
        rows = self.crypto_snapshot()
        embed = discord.Embed(title="📈 Mercado Cripto de Interlude", color=COLOR)
        now = int(time.time())
        with self.db_lock:
            conn = self.connect()
            for row in rows:
                previous = conn.execute(
                    "SELECT price FROM crypto_history WHERE symbol = ? AND id != (SELECT MAX(id) FROM crypto_history WHERE symbol = ?) ORDER BY created_at DESC, id DESC LIMIT 1",
                    (row["symbol"], row["symbol"]),
                ).fetchone()
                pct = 0.0
                if previous and previous["price"]:
                    pct = (row["price"] / previous["price"] - 1) * 100
                embed.add_field(
                    name=f"{row['name']} ({row['symbol']})",
                    value=f"**{money(float(row['price']))}**\nÚltimo cambio: **{pct:+.2f}%**",
                    inline=True,
                )
            conn.close()
        embed.set_footer(text="Los precios se actualizan cada 15 minutos · movimiento híbrido sistema + jugadores")
        await interaction.response.send_message(embed=embed)

    @lude.command(name="crypto-comprar", description="Compra criptomonedas desde tu Cuenta Principal.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_comprar(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], monto: int):
        ok, text = self.crypto_buy(interaction.user.id, moneda.value, monto)
        await interaction.response.send_message(text, ephemeral=not ok)

    @lude.command(name="crypto-vender", description="Vende un porcentaje de una criptomoneda y cobra al banco.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_vender(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], porcentaje: int):
        ok, text = self.crypto_sell(interaction.user.id, moneda.value, porcentaje)
        await interaction.response.send_message(text, ephemeral=not ok)

    @lude.command(name="crypto-cartera", description="Muestra tus criptomonedas y su valor actual.")
    async def crypto_cartera(self, interaction: discord.Interaction):
        uid = interaction.user.id
        self.ensure_user(uid)
        with self.db_lock:
            conn = self.connect()
            holdings = conn.execute("""
                SELECT h.symbol, h.quantity, h.cost_basis, m.name, m.price
                FROM crypto_holdings h
                JOIN crypto_market m ON m.symbol = h.symbol
                WHERE h.user_id = ? AND h.quantity > 0
                ORDER BY h.symbol
            """, (uid,)).fetchall()
            conn.close()
        embed = discord.Embed(title="💼 Cartera Cripto", color=COLOR)
        if not holdings:
            embed.description = "No tienes criptomonedas."
        else:
            total_value = 0.0
            total_cost = 0.0
            for row in holdings:
                value = float(row["quantity"]) * float(row["price"])
                total_value += value
                total_cost += float(row["cost_basis"])
                pnl = value - float(row["cost_basis"])
                embed.add_field(
                    name=f"{row['name']} ({row['symbol']})",
                    value=(
                        f"Unidades: **{row['quantity']:.8f}**\n"
                        f"Valor: **{money(value)}**\n"
                        f"P/L: **{money(pnl)}**"
                    ),
                    inline=True,
                )
            embed.description = f"Valor total: **{money(total_value)}** · Resultado acumulado: **{money(total_value - total_cost)}**"
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    cog = LudeEconomy(bot)
    await bot.add_cog(cog)
    # Guild-specific: sincroniza /lude inmediatamente al cargar/reloadear el Cog.
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    except discord.HTTPException as exc:
        print(f"[LudeEconomy] No se pudo sincronizar /lude: {exc}")
