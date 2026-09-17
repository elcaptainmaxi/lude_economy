import asyncio
import json
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
ADMIN_OWNER_ID = 1006704642618568735  # Cambiá este ID para transferir administración.
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
ROB_THEFT_MIN_PERCENT = 1
ROB_THEFT_MAX_PERCENT = 65
ROB_FAIL_FINE_RATE = 0.25
ROB_MIN_WALLET_SALARY_MULTIPLIER = 2.0

CASINO_MIN_BET = 50
BLACKJACK_NORMAL_RETURN = 2.0
BLACKJACK_NATURAL_RETURN = 2.5
BLACKJACK_DEALER_STAND = 17
ROULETTE_EVEN_RETURN = 2.0
ROULETTE_GREEN_RETURN = 36.0
COINFLIP_FEE_RATE = 0.05
JUDICIAL_RATE = 0.25
TRANSFER_FEE_RATE = 0.05

SLOTS_JACKPOT_BASE = 10_000
SLOTS_JACKPOT_CONTRIBUTION = 0.05
SLOTS_SYMBOL_WEIGHTS = {"🍒": 40, "🍋": 28, "🔔": 18, "💎": 10, "7️⃣": 4}
SLOTS_PAYOUTS = {
    "cherry_pair": 0.5,
    "cherry_triple": 1.5,
    "lemon_triple": 2.0,
    "bell_triple": 3.0,
    "diamond_triple": 5.0,
}

BANK_HISTORY_KEEP = 10

CRYPTO_UPDATE_SECONDS = 5 * 60
CRYPTO_FEE_RATE = 0.01
CRYPTO_HISTORY_KEEP = 288  # 24 horas a 5 min por tick.
CRYPTO_DYNAMIC_RATE = 0.002  # Adaptación base del fundamental por tick.
CRYPTO_STABLE_BOOST = 2.5  # Acelera la adaptación cuando consolida.
CRYPTO_FUNDAMENTAL_MAX_STEP = 0.008  # Movimiento máximo por tick del fundamental.
CRYPTO_REGIME_SWITCH = 0.035  # Probabilidad base de cambiar de régimen.
CRYPTO_SHOCK_CHANCE = 0.003  # Evento extraordinario, común a todo el mercado.
CRYPTO_GLOBAL_INFLUENCE = 0.12  # Máxima influencia de la tendencia común.
CRYPTO_UP_EMOJI_ID = 1550285735305941022
CRYPTO_DOWN_EMOJI_ID = 1550285765584625845

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
        "reversion_strength": 0.38, "momentum_strength": 0.30,
        "momentum_cap": 0.06, "liquidity": 15_000.0,
    },
    "NVA": {
        "name": "Nova", "initial": 250.0,
        "auto_min": 0.03, "auto_max": 0.09, "player_max": 0.04,
        "reversion_strength": 0.22, "momentum_strength": 0.40,
        "momentum_cap": 0.08, "liquidity": 7_500.0,
    },
    "FLX": {
        "name": "Flux", "initial": 50.0,
        "auto_min": 0.07, "auto_max": 0.18, "player_max": 0.06,
        "reversion_strength": 0.08, "momentum_strength": 0.55,
        "momentum_cap": 0.10, "liquidity": 3_000.0,
    },
}


# ============================================================
# CONFIGURACIÓN RUNTIME / ADMIN
# ============================================================

@dataclass(frozen=True)
class SettingSpec:
    key: str
    category: str
    label: str
    value_type: str
    default: object
    target_kind: str
    target_name: str
    path: tuple = ()
    scale: float = 1.0
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    choices: tuple = ()


def _deep_get(obj, path: tuple):
    for part in path:
        obj = obj[part]
    return obj


def _deep_set(obj, path: tuple, value):
    if not path:
        return value
    key = path[0]
    if len(path) == 1:
        if isinstance(obj, tuple):
            clone = list(obj)
            clone[key] = value
            return tuple(clone)
        obj[key] = value
        return obj
    child = obj[key]
    replacement = _deep_set(child, path[1:], value)
    if replacement is not child:
        if isinstance(obj, tuple):
            clone = list(obj)
            clone[key] = replacement
            return tuple(clone)
        obj[key] = replacement
    return obj


def build_setting_specs() -> dict[str, SettingSpec]:
    specs: dict[str, SettingSpec] = {}

    def add_global(key, category, label, target, default, value_type="float", scale=1.0,
                   minimum=None, maximum=None, choices=()):
        specs[key] = SettingSpec(
            key, category, label, value_type, default, "global", target, (), scale,
            minimum, maximum, tuple(choices),
        )

    def add_dict(key, category, label, target, path, default, value_type="float", scale=1.0,
                 minimum=None, maximum=None, choices=()):
        specs[key] = SettingSpec(
            key, category, label, value_type, default, "dict", target, tuple(path), scale,
            minimum, maximum, tuple(choices),
        )

    # General / cooldowns. Los tiempos se administran en minutos.
    add_global("work.cooldown_min", "general", "Cooldown de /work (min)", "WORK_COOLDOWN", 5.0, scale=60, minimum=0, maximum=1440)
    add_global("crime.cooldown_min", "general", "Cooldown de /crime (min)", "CRIME_COOLDOWN", 5.0, scale=60, minimum=0, maximum=1440)
    add_global("rob.cooldown_min", "rob", "Cooldown de /rob (min)", "ROB_COOLDOWN", 30.0, scale=60, minimum=0, maximum=10080)
    add_global("rob.protection_min", "rob", "Duración protección anti-robo (min)", "ROB_PROTECTION_SECONDS", 30.0, scale=60, minimum=1, maximum=10080)
    add_global("rob.protection_cost", "rob", "Costo protección anti-robo", "ROB_PROTECTION_COST", 1500, "int", minimum=0, maximum=100_000_000)
    add_global("rob.theft_min_pct", "rob", "Porcentaje mínimo que puede intentar robar", "ROB_THEFT_MIN_PERCENT", 1, "int", minimum=1, maximum=99)
    add_global("rob.theft_max_pct", "rob", "Porcentaje máximo que puede intentar robar", "ROB_THEFT_MAX_PERCENT", 65, "int", minimum=1, maximum=99)
    add_global("rob.fail_fine_pct", "rob", "Multa por robo fallido (% del intento)", "ROB_FAIL_FINE_RATE", 25.0, scale=0.01, minimum=0, maximum=1000)
    add_global("rob.min_wallet_salary_multiplier", "rob", "Wallet mínimo de víctima (x salario)", "ROB_MIN_WALLET_SALARY_MULTIPLIER", 2.0, minimum=0, maximum=100)
    add_global("casino.min_bet", "casino", "Apuesta mínima del casino", "CASINO_MIN_BET", 50, "int", minimum=1, maximum=100_000_000)
    add_global("casino.blackjack.normal_return", "casino", "Blackjack · retorno victoria normal (x)", "BLACKJACK_NORMAL_RETURN", 2.0, minimum=0, maximum=100)
    add_global("casino.blackjack.natural_return", "casino", "Blackjack · retorno natural (x)", "BLACKJACK_NATURAL_RETURN", 2.5, minimum=0, maximum=100)
    add_global("casino.blackjack.dealer_stand", "casino", "Blackjack · dealer se planta en", "BLACKJACK_DEALER_STAND", 17, "int", minimum=12, maximum=21)
    add_global("casino.roulette.even_return", "casino", "Ruleta · retorno rojo/negro (x)", "ROULETTE_EVEN_RETURN", 2.0, minimum=0, maximum=100)
    add_global("casino.roulette.green_return", "casino", "Ruleta · retorno verde (x)", "ROULETTE_GREEN_RETURN", 36.0, minimum=0, maximum=1000)
    add_global("casino.coinflip_fee_pct", "casino", "Comisión Coinflip (%)", "COINFLIP_FEE_RATE", 5.0, scale=0.01, minimum=0, maximum=100)
    add_global("judicial.rate_pct", "general", "Retención/recargo judicial (%)", "JUDICIAL_RATE", 25.0, scale=0.01, minimum=0, maximum=100)
    add_global("bank.transfer_fee_pct", "bank", "Comisión de transferencias (%)", "TRANSFER_FEE_RATE", 5.0, scale=0.01, minimum=0, maximum=100)
    add_global("slots.jackpot_base", "casino", "Jackpot base de Slots", "SLOTS_JACKPOT_BASE", 10_000, "int", minimum=0, maximum=1_000_000_000)
    add_global("slots.jackpot_contribution_pct", "casino", "Aporte al jackpot (%)", "SLOTS_JACKPOT_CONTRIBUTION", 5.0, scale=0.01, minimum=0, maximum=100)
    for symbol_name, weight in SLOTS_SYMBOL_WEIGHTS.items():
        symbol_key = {"🍒": "cherry", "🍋": "lemon", "🔔": "bell", "💎": "diamond", "7️⃣": "seven"}[symbol_name]
        add_dict(f"casino.slots.weight.{symbol_key}", "casino", f"Slots · peso {symbol_name}", "SLOTS_SYMBOL_WEIGHTS", (symbol_name,), weight, minimum=0, maximum=1_000_000)
    for payout_key, payout in SLOTS_PAYOUTS.items():
        add_dict(f"casino.slots.payout.{payout_key}", "casino", f"Slots · retorno {payout_key} (x)", "SLOTS_PAYOUTS", (payout_key,), payout, minimum=0, maximum=10000)
    add_global("bank.history_keep", "bank", "Movimientos bancarios conservados", "BANK_HISTORY_KEEP", 10, "int", minimum=1, maximum=1000)
    add_global("crypto.update_min", "crypto", "Intervalo de actualización cripto (min)", "CRYPTO_UPDATE_SECONDS", 5.0, scale=60, minimum=1, maximum=1440)
    add_global("crypto.fee_pct", "crypto", "Comisión compra/venta cripto (%)", "CRYPTO_FEE_RATE", 1.0, scale=0.01, minimum=0, maximum=100)
    add_global("crypto.history_keep", "crypto", "Registros históricos por cripto", "CRYPTO_HISTORY_KEEP", 288, "int", minimum=2, maximum=10000)

    # Bank of Interlude.
    for level, cfg in BANK_LEVELS.items():
        add_dict(f"bank.level.{level}.capacity", "bank", f"Capacidad banco nivel {level}", "BANK_LEVELS", (level, "capacity"), cfg["capacity"], "int", minimum=1)
        add_dict(f"bank.level.{level}.upgrade_cost", "bank", f"Costo mejora banco nivel {level}", "BANK_LEVELS", (level, "upgrade_cost"), cfg["upgrade_cost"], "int", minimum=0)
    add_global("bank.additional.open_level", "bank", "Nivel inicial cuenta adicional", "ADDITIONAL_OPEN_LEVEL", ADDITIONAL_OPEN_LEVEL, "int", minimum=1, maximum=7)
    add_global("bank.additional.open_cost", "bank", "Costo apertura cuenta adicional", "ADDITIONAL_OPEN_COST", ADDITIONAL_OPEN_COST, "int", minimum=0)
    for level, cost in ADDITIONAL_UPGRADE_COSTS.items():
        add_dict(f"bank.additional.level.{level}.upgrade_cost", "bank", f"Costo adicional nivel {level}", "ADDITIONAL_UPGRADE_COSTS", (level,), cost, "int", minimum=0)

    # Calificaciones laborales.
    for grade, value in GRADE_MULTIPLIERS.items():
        add_dict(f"work.grade.{grade}.salary_multiplier", "work", f"Multiplicador salario nota {grade}", "GRADE_MULTIPLIERS", (grade,), value, minimum=0, maximum=20)
    for grade, value in GRADE_XP_MULTIPLIERS.items():
        add_dict(f"work.grade.{grade}.xp_multiplier", "work", f"Multiplicador XP nota {grade}", "GRADE_XP_MULTIPLIERS", (grade,), value, minimum=0, maximum=20)

    # Todos los empleos.
    for job_id, job in JOBS.items():
        add_dict(f"job.{job_id}.level", "jobs", f"{job['name']} · Work Level", "JOBS", (job_id, "level"), job["level"], "int", minimum=0, maximum=100)
        add_dict(f"job.{job_id}.salary_min", "jobs", f"{job['name']} · salario mínimo", "JOBS", (job_id, "salary", 0), job["salary"][0], "int", minimum=0)
        add_dict(f"job.{job_id}.salary_max", "jobs", f"{job['name']} · salario máximo", "JOBS", (job_id, "salary", 1), job["salary"][1], "int", minimum=0)
        add_dict(f"job.{job_id}.payment", "jobs", f"{job['name']} · destino de pago", "JOBS", (job_id, "payment"), job["payment"], "str", choices=("wallet", "bank"))

    # Crime.
    for crime_id, cfg in CRIME_CATEGORIES.items():
        add_dict(f"crime.{crime_id}.weight", "crime", f"{cfg['name']} · peso de aparición", "CRIME_CATEGORIES", (crime_id, "weight"), cfg["weight"], minimum=0, maximum=10000)
        add_dict(f"crime.{crime_id}.success_pct", "crime", f"{cfg['name']} · éxito (%)", "CRIME_CATEGORIES", (crime_id, "success"), cfg["success"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crime.{crime_id}.arrest_if_fail_pct", "crime", f"{cfg['name']} · arresto si falla (%)", "CRIME_CATEGORIES", (crime_id, "arrest_if_fail"), cfg["arrest_if_fail"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crime.{crime_id}.reward_min_pct", "crime", f"{cfg['name']} · recompensa mínima (% salario)", "CRIME_CATEGORIES", (crime_id, "reward", 0), cfg["reward"][0] * 100, scale=0.01, minimum=0, maximum=10000)
        add_dict(f"crime.{crime_id}.reward_max_pct", "crime", f"{cfg['name']} · recompensa máxima (% salario)", "CRIME_CATEGORIES", (crime_id, "reward", 1), cfg["reward"][1] * 100, scale=0.01, minimum=0, maximum=10000)
        add_dict(f"crime.{crime_id}.fine_min_pct", "crime", f"{cfg['name']} · multa mínima (% salario)", "CRIME_CATEGORIES", (crime_id, "fine", 0), cfg["fine"][0] * 100, scale=0.01, minimum=0, maximum=10000)
        add_dict(f"crime.{crime_id}.fine_max_pct", "crime", f"{cfg['name']} · multa máxima (% salario)", "CRIME_CATEGORIES", (crime_id, "fine", 1), cfg["fine"][1] * 100, scale=0.01, minimum=0, maximum=10000)
        add_dict(f"crime.{crime_id}.bail_pct", "crime", f"{cfg['name']} · fianza (% salario)", "CRIME_CATEGORIES", (crime_id, "bail"), cfg["bail"] * 100, scale=0.01, minimum=0, maximum=10000)

    # Motor cripto 2.0; se pueden modificar desde /lude admin.
    add_global("crypto.dynamic_rate", "crypto", "Adaptación base del fundamental por tick", "CRYPTO_DYNAMIC_RATE", 0.002, minimum=0, maximum=0.03)
    add_global("crypto.stable_boost", "crypto", "Aceleración cuando consolida", "CRYPTO_STABLE_BOOST", 2.5, minimum=1, maximum=8)
    add_global("crypto.fundamental_max_step_pct", "crypto", "Variación máxima del fundamental por tick (%)", "CRYPTO_FUNDAMENTAL_MAX_STEP", 0.8, scale=0.01, minimum=0, maximum=5)
    add_global("crypto.regime_switch_pct", "crypto", "Cambio base de régimen por tick (%)", "CRYPTO_REGIME_SWITCH", 3.5, scale=0.01, minimum=0, maximum=100)
    add_global("crypto.shock_chance_pct", "crypto", "Probabilidad de shock global por tick (%)", "CRYPTO_SHOCK_CHANCE", 0.3, scale=0.01, minimum=0, maximum=10)
    add_global("crypto.global_influence", "crypto", "Influencia del mercado global", "CRYPTO_GLOBAL_INFLUENCE", 0.12, minimum=0, maximum=1)

    # Criptomonedas. auto_min/max mantienen exactamente los rangos originales por tick.
    for symbol, cfg in CRYPTO_CONFIG.items():
        add_dict(f"crypto.{symbol}.fundamental", "crypto", f"{symbol} · fijar fundamental manualmente", "CRYPTO_CONFIG", (symbol, "initial"), cfg["initial"], minimum=0.01)
        add_dict(f"crypto.{symbol}.auto_min_pct", "crypto", f"{symbol} · volatilidad mínima por tick (%)", "CRYPTO_CONFIG", (symbol, "auto_min"), cfg["auto_min"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crypto.{symbol}.auto_max_pct", "crypto", f"{symbol} · volatilidad máxima por tick (%)", "CRYPTO_CONFIG", (symbol, "auto_max"), cfg["auto_max"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crypto.{symbol}.player_max_pct", "crypto", f"{symbol} · impacto máximo jugadores (%)", "CRYPTO_CONFIG", (symbol, "player_max"), cfg["player_max"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crypto.{symbol}.reversion_strength", "crypto", f"{symbol} · fuerza de reversión", "CRYPTO_CONFIG", (symbol, "reversion_strength"), cfg["reversion_strength"], minimum=0, maximum=10)
        add_dict(f"crypto.{symbol}.momentum_strength", "crypto", f"{symbol} · fuerza de momentum", "CRYPTO_CONFIG", (symbol, "momentum_strength"), cfg["momentum_strength"], minimum=0, maximum=10)
        add_dict(f"crypto.{symbol}.momentum_cap_pct", "crypto", f"{symbol} · tope momentum por tick (%)", "CRYPTO_CONFIG", (symbol, "momentum_cap"), cfg["momentum_cap"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crypto.{symbol}.liquidity", "crypto", f"{symbol} · liquidez de referencia", "CRYPTO_CONFIG", (symbol, "liquidity"), cfg["liquidity"], minimum=1)

    return specs


SETTING_SPECS = build_setting_specs()
SETTING_CATEGORIES = ("general", "work", "jobs", "bank", "crime", "rob", "casino", "crypto")


def _setting_raw_value(spec: SettingSpec):
    if spec.target_kind == "global":
        return globals()[spec.target_name]
    return _deep_get(globals()[spec.target_name], spec.path)


def setting_display_value(spec: SettingSpec):
    raw = _setting_raw_value(spec)
    if spec.value_type == "str":
        return str(raw)
    return raw / spec.scale


def parse_setting_value(spec: SettingSpec, value):
    if spec.value_type == "str":
        parsed = str(value).strip().lower()
        if spec.choices and parsed not in spec.choices:
            raise ValueError(f"Valores permitidos: {', '.join(spec.choices)}")
        return parsed
    try:
        parsed = int(value) if spec.value_type == "int" else float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("El valor debe ser numérico.")
    if spec.minimum is not None and parsed < spec.minimum:
        raise ValueError(f"El mínimo permitido es {spec.minimum}.")
    if spec.maximum is not None and parsed > spec.maximum:
        raise ValueError(f"El máximo permitido es {spec.maximum}.")
    return parsed


def apply_setting_value(spec: SettingSpec, display_value):
    parsed = parse_setting_value(spec, display_value)
    if spec.value_type == "str":
        raw = parsed
    else:
        raw = parsed * spec.scale
        if spec.value_type == "int" and spec.scale == 1:
            raw = int(raw)
    if spec.target_kind == "global":
        globals()[spec.target_name] = raw
    else:
        root = globals()[spec.target_name]
        replacement = _deep_set(root, spec.path, raw)
        if replacement is not root:
            globals()[spec.target_name] = replacement
    return parsed


def format_setting_value(value) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


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
            and (
                member.guild_permissions.administrator
                or (tester_role is not None and member.top_role.position >= tester_role.position)
            )
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
        self.buy.label = f"Comprar protección · {money(ROB_PROTECTION_COST)}"

    @discord.ui.button(label="Comprar protección", style=discord.ButtonStyle.primary, emoji="🛡️")
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

    @discord.ui.button(label="Doblar ×2", style=discord.ButtonStyle.success, emoji="✖️")
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
            while self.hand_value(self.dealer) < int(BLACKJACK_DEALER_STAND):
                self.dealer.append(self.deck.pop())

        dealer_value = self.hand_value(self.dealer)
        dealer_natural = self.is_natural(self.dealer)

        if player_value > 21:
            outcome, total_return = "💥 Te pasaste de 21. Perdiste.", 0
        elif player_natural and not dealer_natural:
            total_return = int(round(self.bet * BLACKJACK_NATURAL_RETURN))
            outcome = "🖤 Blackjack natural."
        elif dealer_value > 21:
            total_return = int(round(self.bet * BLACKJACK_NORMAL_RETURN))
            outcome = "✅ El dealer se pasó. Ganaste."
        elif player_value > dealer_value:
            total_return = int(round(self.bet * BLACKJACK_NORMAL_RETURN))
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
# LUDE MARKET ENGINE 2.0 · estado persistente, función pura
# ============================================================

MARKET_REGIMES = ("bull", "bear", "sideways", "storm")
MARKET_REGIME_LABELS = {
    "bull": "📈 Alcista", "bear": "📉 Bajista",
    "sideways": "↔️ Consolidación", "storm": "⚡ Volatilidad",
}


def market_engine_step(price, cfg, state, history, buy, sell, global_sentiment, shock=0.0, rng=None):
    """Avanza un tick SIN modificar saldos; devuelve (precio, nuevo estado).

    Mantiene auto_min/auto_max originales como límites del movimiento automático;
    jugadores, momentum y shocks son componentes independientes y acotados.
    """
    rng = rng or random
    price = max(0.01, float(price))
    fundamental = max(0.01, float(state["fundamental"]))
    regime = state["regime"] if state["regime"] in MARKET_REGIMES else "sideways"
    age = max(0, int(state["regime_ticks"])) + 1
    volatility = max(0.0, min(1.0, float(state["volatility"])))
    pressure = max(-1.0, min(1.0, float(state["pressure"])))
    prices = [max(0.01, float(p)) for p in history if float(p) > 0]
    if not prices or abs(prices[-1] - price) > max(0.0001, price * 1e-8):
        prices.append(price)
    returns = [math.log(b / a) for a, b in zip(prices[:-1], prices[1:])]
    momentum = sum(returns[-4:]) / min(4, len(returns)) if returns else 0.0
    spread_prices = prices[-12:]
    spread = (max(spread_prices) / min(spread_prices) - 1) if len(spread_prices) >= 3 else 1.0
    stable = len(spread_prices) >= 8 and spread < max(0.025, cfg["auto_max"] * 1.4)
    stable_ticks = (int(state["stable_ticks"]) + 1) if stable else 0

    # Transiciones no periódicas: la edad importa, pero no fuerza un ciclo rígido.
    personality = {"IC": 0.75, "NVA": 1.0, "FLX": 1.35}.get(cfg["symbol"], 1.0)
    transition = min(0.36, CRYPTO_REGIME_SWITCH * personality + min(age, 100) * 0.0006)
    if rng.random() < transition:
        direction = math.tanh(momentum / max(cfg["auto_max"], 0.0001))
        shared = max(-1.0, min(1.0, global_sentiment))
        bull_weight = max(0.1, 1.0 + direction + shared * 0.7)
        bear_weight = max(0.1, 1.0 - direction - shared * 0.7)
        sideways_weight = 1.8 if stable else 0.9
        storm_weight = 0.35 + 0.65 * volatility
        regime = rng.choices(MARKET_REGIMES, weights=[bull_weight, bear_weight, sideways_weight, storm_weight], k=1)[0]
        age = 0

    volume = max(0.0, buy) + max(0.0, sell)
    signed = (buy - sell) / volume if volume else 0.0
    # Impacto sublineal, saturación por liquidez y persistencia decreciente.
    liquidity = max(1.0, float(cfg["liquidity"]))
    flow = signed * (math.sqrt(volume) / (math.sqrt(volume) + math.sqrt(liquidity))) if volume else 0.0
    pressure = max(-1.0, min(1.0, pressure * 0.55 + flow * 0.7))
    player_move = max(-cfg["player_max"], min(cfg["player_max"], cfg["player_max"] * (flow + 0.20 * pressure)))

    # Adaptación gradual del fundamental: acelerar solo tras estabilización real.
    speed = CRYPTO_DYNAMIC_RATE * {"IC": 0.6, "NVA": 1.0, "FLX": 1.35}.get(cfg["symbol"], 1.0)
    if stable_ticks >= 8:
        speed *= CRYPTO_STABLE_BOOST
    speed *= 1.0 + min(0.35, volume / (volume + liquidity) * 0.35) if volume else 1.0
    fundamental_step = max(-CRYPTO_FUNDAMENTAL_MAX_STEP, min(CRYPTO_FUNDAMENTAL_MAX_STEP, speed * math.log(price / fundamental)))
    fundamental = max(0.01, fundamental * math.exp(fundamental_step))

    # La reversión es débil fuera de una consolidación; no hay precio garantizado.
    reversion_factor = {"bull": 0.12, "bear": 0.12, "sideways": 0.65, "storm": 0.04}[regime]
    reversion = -math.tanh(math.log(price / fundamental) * cfg["reversion_strength"]) * 0.20 * reversion_factor
    trend = {"bull": 0.17, "bear": -0.17, "sideways": 0.0, "storm": 0.0}[regime]
    momentum_bias = math.tanh(momentum / max(cfg["auto_max"], 0.0001)) * cfg["momentum_strength"] * 0.15
    shared_bias = max(-0.12, min(0.12, global_sentiment * CRYPTO_GLOBAL_INFLUENCE))
    up_probability = max(0.08, min(0.92, 0.5 + trend + reversion + momentum_bias + shared_bias))

    # Agrupamiento de volatilidad sin alterar los rangos auto_min/auto_max.
    volatility = max(0.0, min(1.0, volatility * 0.84 + abs(momentum) / max(cfg["auto_max"], 0.0001) * 0.12 + abs(shock) * 1.8))
    floor, ceiling = sorted((max(0.0, cfg["auto_min"]), max(0.0, cfg["auto_max"])))
    sample = rng.random()
    if regime == "storm" or volatility > 0.70:
        sample = max(sample, rng.random())
    elif regime == "sideways" and volatility < 0.22:
        sample = min(sample, rng.random())
    magnitude = floor + (ceiling - floor) * sample
    auto_move = magnitude if rng.random() < up_probability else -magnitude
    momentum_move = max(-cfg["momentum_cap"], min(cfg["momentum_cap"], momentum * cfg["momentum_strength"] * (0.7 if regime == "sideways" else 1.0)))
    shock_move = max(-ceiling * 0.6, min(ceiling * 0.6, shock))
    total_return = max(-0.85, min(1.5, auto_move + momentum_move + player_move + shock_move))
    new_price = max(0.01, round(price * (1.0 + total_return), 4))
    return new_price, {
        "fundamental": fundamental, "regime": regime, "regime_ticks": age,
        "volatility": volatility, "pressure": pressure, "stable_ticks": stable_ticks,
    }

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

    crypto_group = app_commands.Group(
        name="crypto",
        description="Mercado e inversiones en criptomonedas.",
        parent=lude,
    )

    admin_group = app_commands.Group(
        name="admin",
        description="Configuración administrativa de la economía.",
        parent=lude,
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_lock = threading.RLock()
        self.active_work_users: set[int] = set()
        self.bank_reservations: dict[int, int] = {}
        self.init_db()
        self.load_runtime_settings()

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
                CREATE TABLE IF NOT EXISTS economy_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_by INTEGER,
                    updated_at INTEGER NOT NULL
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

            # Migración aditiva: no toca precios ni tenencias existentes.
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_engine_state (
                    symbol TEXT PRIMARY KEY,
                    fundamental REAL NOT NULL,
                    regime TEXT NOT NULL DEFAULT 'sideways',
                    regime_ticks INTEGER NOT NULL DEFAULT 0,
                    volatility REAL NOT NULL DEFAULT 0.35,
                    pressure REAL NOT NULL DEFAULT 0,
                    stable_ticks INTEGER NOT NULL DEFAULT 0
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crypto_global_state (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    sentiment REAL NOT NULL DEFAULT 0
                )
            """)
            cur.execute("INSERT OR IGNORE INTO crypto_global_state(id, sentiment) VALUES(1, 0)")
            for symbol, cfg in CRYPTO_CONFIG.items():
                cur.execute(
                    "INSERT OR IGNORE INTO crypto_engine_state(symbol, fundamental) VALUES(?, ?)",
                    (symbol, float(cfg["initial"])),
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
                  LIMIT ?
              )
        """, (user_id, user_id, int(BANK_HISTORY_KEEP)))

    # --------------------------------------------------------
    # CONFIGURACIÓN RUNTIME / ADMIN
    # --------------------------------------------------------

    def load_runtime_settings(self):
        with self.db_lock:
            conn = self.connect()
            rows = conn.execute("SELECT key, value FROM economy_settings").fetchall()
            conn.close()
        for row in rows:
            spec = SETTING_SPECS.get(row["key"])
            if not spec:
                continue
            try:
                value = json.loads(row["value"])
                apply_setting_value(spec, value)
            except Exception as exc:
                print(f"[LudeEconomy] Ajuste inválido ignorado {row['key']}: {exc}")

    def update_runtime_setting(self, key: str, value, updated_by: int):
        spec = SETTING_SPECS.get(key)
        if not spec:
            raise KeyError("Ajuste inexistente")
        previous_value = setting_display_value(spec)
        parsed = apply_setting_value(spec, value)

        # Validaciones cruzadas importantes.
        if key.endswith("salary_min"):
            job_id = key.split(".")[1]
            if JOBS[job_id]["salary"][0] > JOBS[job_id]["salary"][1]:
                apply_setting_value(spec, previous_value)
                raise ValueError("El salario mínimo no puede superar al salario máximo.")
        elif key.endswith("salary_max"):
            job_id = key.split(".")[1]
            if JOBS[job_id]["salary"][1] < JOBS[job_id]["salary"][0]:
                apply_setting_value(spec, previous_value)
                raise ValueError("El salario máximo no puede ser menor al salario mínimo.")
        elif key.endswith("auto_min_pct"):
            symbol = key.split(".")[1]
            if CRYPTO_CONFIG[symbol]["auto_min"] > CRYPTO_CONFIG[symbol]["auto_max"]:
                apply_setting_value(spec, previous_value)
                raise ValueError("La volatilidad mínima no puede superar la máxima.")
        elif key.endswith("auto_max_pct"):
            symbol = key.split(".")[1]
            if CRYPTO_CONFIG[symbol]["auto_max"] < CRYPTO_CONFIG[symbol]["auto_min"]:
                apply_setting_value(spec, previous_value)
                raise ValueError("La volatilidad máxima no puede ser menor a la mínima.")
        elif key in {"rob.theft_min_pct", "rob.theft_max_pct"}:
            if ROB_THEFT_MIN_PERCENT > ROB_THEFT_MAX_PERCENT:
                apply_setting_value(spec, previous_value)
                raise ValueError("El porcentaje mínimo de robo no puede superar al máximo.")
        elif key.startswith("crime.") and key.endswith(".weight"):
            if sum(max(0, float(c["weight"])) for c in CRIME_CATEGORIES.values()) <= 0:
                apply_setting_value(spec, previous_value)
                raise ValueError("Al menos una categoría de crimen debe tener peso mayor que 0.")
        elif key.startswith("casino.slots.weight."):
            if sum(max(0, float(w)) for w in SLOTS_SYMBOL_WEIGHTS.values()) <= 0:
                apply_setting_value(spec, previous_value)
                raise ValueError("Al menos un símbolo de Slots debe tener peso mayor que 0.")

        with self.db_lock:
            conn = self.connect()
            conn.execute(
                """
                INSERT INTO economy_settings(key, value, updated_by, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (key, json.dumps(parsed, ensure_ascii=False), updated_by, int(time.time())),
            )
            if key.startswith("crypto.") and key.endswith(".fundamental"):
                symbol = key.split(".")[1]
                conn.execute(
                    "UPDATE crypto_engine_state SET fundamental = ?, stable_ticks = 0 WHERE symbol = ?",
                    (float(parsed), symbol),
                )
            conn.commit()
            conn.close()
        return parsed

    def reset_runtime_setting(self, key: str):
        spec = SETTING_SPECS.get(key)
        if not spec:
            raise KeyError("Ajuste inexistente")
        # Usar la misma validación cruzada de /admin cambiar antes de restaurar.
        self.update_runtime_setting(key, spec.default, 0)
        with self.db_lock:
            conn = self.connect()
            conn.execute("DELETE FROM economy_settings WHERE key = ?", (key,))
            conn.commit()
            conn.close()
        return spec.default

    def member_is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == ADMIN_OWNER_ID

    async def require_admin(self, interaction: discord.Interaction) -> bool:
        if self.member_is_admin(interaction):
            return True

        if not interaction.response.is_done():
            await interaction.response.send_message(
                "⛔ Solo el dueño del bot puede utilizar este comando.",
                ephemeral=True,
            )
        return False

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
            self.log_bank(cur, sender_id, "primary", "transfer_fee", fee, sender_new, f"Comisión {TRANSFER_FEE_RATE * 100:g}% por transferencia a {receiver_id}")
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

            text = f"🛡️ Protección activada por **{format_seconds(ROB_PROTECTION_SECONDS)}**. Costo: **{money(ROB_PROTECTION_COST)}**."
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
                return False, f"Necesitas **{money(total)}** en tu Cuenta Principal (incluye {CRYPTO_FEE_RATE * 100:g}% de comisión)."
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

    @tasks.loop(seconds=30)
    async def crypto_price_loop(self):
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor()
                cur.execute("BEGIN IMMEDIATE")
                now = int(time.time())
                due = []
                for symbol, cfg in CRYPTO_CONFIG.items():
                    row = cur.execute(
                        "SELECT price, buy_volume, sell_volume, updated_at FROM crypto_market WHERE symbol = ?",
                        (symbol,),
                    ).fetchone()
                    if row and now - int(row["updated_at"]) >= CRYPTO_UPDATE_SECONDS:
                        due.append((symbol, cfg, row))
                if due:
                    global_state = cur.execute("SELECT sentiment FROM crypto_global_state WHERE id = 1").fetchone()
                    old_sentiment = float(global_state["sentiment"]) if global_state else 0.0
                    # Componente compartido suave, un único evento para todas las monedas.
                    global_sentiment = max(-1.0, min(1.0, old_sentiment * 0.87 + random.uniform(-0.15, 0.15)))
                    shock = random.choice((-1.0, 1.0)) * random.uniform(0.025, 0.075) if random.random() < CRYPTO_SHOCK_CHANCE else 0.0
                    for symbol, cfg, row in due:
                        prices = cur.execute(
                            "SELECT price FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT 13",
                            (symbol,),
                        ).fetchall()
                        history = [float(p["price"]) for p in reversed(prices)]
                        state_row = cur.execute("SELECT * FROM crypto_engine_state WHERE symbol = ?", (symbol,)).fetchone()
                        if not state_row:
                            cur.execute("INSERT OR IGNORE INTO crypto_engine_state(symbol, fundamental) VALUES(?, ?)", (symbol, float(cfg["initial"])))
                            state_row = cur.execute("SELECT * FROM crypto_engine_state WHERE symbol = ?", (symbol,)).fetchone()
                        state = dict(state_row)
                        cfg_with_symbol = dict(cfg, symbol=symbol)
                        new_price, new_state = market_engine_step(
                            row["price"], cfg_with_symbol, state, history,
                            max(0.0, float(row["buy_volume"])),
                            max(0.0, float(row["sell_volume"])), global_sentiment, shock,
                        )
                        cur.execute(
                            "UPDATE crypto_market SET price = ?, buy_volume = 0, sell_volume = 0, updated_at = ? WHERE symbol = ?",
                            (new_price, now, symbol),
                        )
                        cur.execute(
                            """UPDATE crypto_engine_state SET fundamental = ?, regime = ?, regime_ticks = ?,
                               volatility = ?, pressure = ?, stable_ticks = ? WHERE symbol = ?""",
                            (new_state["fundamental"], new_state["regime"], new_state["regime_ticks"],
                             new_state["volatility"], new_state["pressure"], new_state["stable_ticks"], symbol),
                        )
                        cur.execute(
                            "INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)",
                            (symbol, new_price, now),
                        )
                        cur.execute("""
                            DELETE FROM crypto_history WHERE symbol = ? AND id NOT IN (
                                SELECT id FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT ?
                            )
                        """, (symbol, symbol, int(CRYPTO_HISTORY_KEEP)))
                    cur.execute("UPDATE crypto_global_state SET sentiment = ? WHERE id = 1", (global_sentiment,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

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
                "SELECT * FROM bank_history WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (uid, int(BANK_HISTORY_KEEP)),
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
        embed = discord.Embed(title=f"📜 Bank of Interlude · Últimos {int(BANK_HISTORY_KEEP)}", description="\n".join(lines), color=COLOR)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @lude.command(name="deuda", description="Consulta tu Deuda Judicial.")
    async def deuda(self, interaction: discord.Interaction):
        user = self.get_user(interaction.user.id)
        embed = discord.Embed(title="⚖️ Deuda Judicial", color=COLOR_DANGER if user["judicial_debt"] else COLOR_SUCCESS)
        embed.description = f"Deuda actual: **{money(user['judicial_debt'])}**."
        if user["judicial_debt"]:
            embed.add_field(name="Retención", value=f"{JUDICIAL_RATE * 100:g}% de ingresos legítimos y recargo en compras hasta cancelar la deuda.", inline=False)
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
            theft_percent = random.randint(int(ROB_THEFT_MIN_PERCENT), int(ROB_THEFT_MAX_PERCENT))
            bail = max(1, int(round(self.salary_reference(thief_id) * rob_bail_multiplier(theft_percent))))
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET last_rob_at = ? WHERE user_id = ?", (now, thief_id)); conn.commit(); conn.close()
            self.arrest_user(thief_id, bail)
            await interaction.response.send_message(
                f"🛡️ {usuario.mention} tenía **protección anti-robo activa**.\n🚔 Fuiste arrestado automáticamente. Fianza: **{money(bail)}**.",
            )
            return

        min_wallet = int(round(self.salary_reference(victim_id) * ROB_MIN_WALLET_SALARY_MULTIPLIER))
        if victim["wallet"] < min_wallet:
            await interaction.response.send_message(
                f"💸 {usuario.mention} no puede ser robado ahora. Debe llevar al menos **{money(min_wallet)}** en Wallet.\nTu cooldown **no fue consumido**.",
                ephemeral=True,
            )
            return

        theft_percent = random.randint(int(ROB_THEFT_MIN_PERCENT), int(ROB_THEFT_MAX_PERCENT))
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
            fine = max(1, int(round(attempted * ROB_FAIL_FINE_RATE)))
            penalty = self.collect_penalty(thief_id, fine)
            protection_until = now + ROB_PROTECTION_SECONDS
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET protection_until = ? WHERE user_id = ?", (protection_until, victim_id)); conn.commit(); conn.close()
            embed.description = (
                f"❌ El robo falló. <@{thief_id}> fue multado con **{money(fine)}**.\n"
                f"🛡️ {usuario.mention} recibió **{format_seconds(ROB_PROTECTION_SECONDS)} de protección gratis**."
            )
            if penalty["debt"]:
                embed.description += f"\n⚖️ **{money(penalty['debt'])}** de la multa pasó a Deuda Judicial."
            await interaction.response.send_message(embed=embed)

    @lude.command(name="slots", description="Apuesta en Slots. Una parte alimenta el Jackpot Global.")
    async def slots(self, interaction: discord.Interaction, apuesta: int):
        uid = interaction.user.id
        if apuesta < CASINO_MIN_BET:
            await interaction.response.send_message(f"La apuesta mínima es **{money(CASINO_MIN_BET)}**.", ephemeral=True)
            return
        if not self.try_debit_wallet(uid, apuesta):
            await interaction.response.send_message("No tienes suficiente Wallet.", ephemeral=True)
            return

        symbols = list(SLOTS_SYMBOL_WEIGHTS.keys())
        weights = [SLOTS_SYMBOL_WEIGHTS[symbol] for symbol in symbols]
        if sum(weights) <= 0:
            await interaction.response.send_message("Slots está temporalmente deshabilitado por configuración administrativa.", ephemeral=True)
            # Reembolsa porque la apuesta ya se debitó.
            with self.db_lock:
                conn = self.connect(); conn.execute("UPDATE economy_users SET wallet = wallet + ? WHERE user_id = ?", (apuesta, uid)); conn.commit(); conn.close()
            return
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
            total_return = int(round(apuesta * SLOTS_PAYOUTS["diamond_triple"])); result_name = f"💎 ×{SLOTS_PAYOUTS["diamond_triple"]:g}"
        elif reels[0] == reels[1] == reels[2] == "🔔":
            total_return = int(round(apuesta * SLOTS_PAYOUTS["bell_triple"])); result_name = f"🔔 ×{SLOTS_PAYOUTS["bell_triple"]:g}"
        elif reels[0] == reels[1] == reels[2] == "🍋":
            total_return = int(round(apuesta * SLOTS_PAYOUTS["lemon_triple"])); result_name = f"🍋 ×{SLOTS_PAYOUTS["lemon_triple"]:g}"
        elif reels[0] == reels[1] == reels[2] == "🍒":
            total_return = int(round(apuesta * SLOTS_PAYOUTS["cherry_triple"])); result_name = f"🍒 ×{SLOTS_PAYOUTS["cherry_triple"]:g}"
        elif reels.count("🍒") >= 2:
            total_return = int(round(apuesta * SLOTS_PAYOUTS["cherry_pair"])); result_name = f"🍒🍒 ×{SLOTS_PAYOUTS["cherry_pair"]:g}"

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
        multiplier = ROULETTE_GREEN_RETURN if color.value == "green" else ROULETTE_EVEN_RETURN
        total_return = int(round(apuesta * multiplier)) if won else 0
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
            f"Comisión del casino: **{COINFLIP_FEE_RATE * 100:g}% del pozo**."
        )
        embed.set_footer(text="El desafío expira en 60 segundos. El dinero se descuenta solo al aceptar.")
        await interaction.response.send_message(content=usuario.mention, embed=embed, view=view)
        view.message = await interaction.original_response()

    # ========================================================
    # /lude crypto ...
    # ========================================================

    @crypto_group.command(name="mercado", description="Muestra el mercado y las últimas cinco variaciones.")
    async def crypto_mercado(self, interaction: discord.Interaction):
        rows = self.crypto_snapshot()
        embed = discord.Embed(title="📈 Mercado Cripto de Interlude", color=COLOR)
        with self.db_lock:
            conn = self.connect()
            try:
                for row in rows:
                    samples = conn.execute(
                        "SELECT price FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT 6",
                        (row["symbol"],),
                    ).fetchall()
                    prices = [float(sample["price"]) for sample in reversed(samples)]
                    movements = []
                    for previous, current in zip(prices[:-1], prices[1:]):
                        if current > previous:
                            movements.append(f"<:crypto_up:{CRYPTO_UP_EMOJI_ID}>")
                        elif current < previous:
                            movements.append(f"<:crypto_down:{CRYPTO_DOWN_EMOJI_ID}>")
                        else:
                            movements.append("➖")
                    pct = (prices[-1] / prices[-2] - 1) * 100 if len(prices) >= 2 and prices[-2] > 0 else 0.0
                    state = conn.execute("SELECT fundamental, regime FROM crypto_engine_state WHERE symbol = ?", (row["symbol"],)).fetchone()
                    fundamental = float(state["fundamental"]) if state else float(CRYPTO_CONFIG[row["symbol"]]["initial"])
                    deviation = (float(row["price"]) / max(0.01, fundamental) - 1) * 100
                    embed.add_field(
                        name=f"{row['name']} ({row['symbol']})",
                        value=(
                            f"**{money(float(row['price']))}**\n"
                            f"Último cambio: **{pct:+.2f}%**\n"
                            f"Vs. fundamental: **{deviation:+.1f}%**\n"
                            f"Estado: **{MARKET_REGIME_LABELS.get(state['regime'], '↔️ Consolidación') if state else '↔️ Consolidación'}**\n"
                            f"Últimos 5: {' '.join(movements[-5:]) if movements else 'Sin historial'}"
                        ),
                        inline=True,
                    )
            finally:
                conn.close()
        embed.set_footer(text=f"Actualización cada {format_seconds(CRYPTO_UPDATE_SECONDS)} · historial de izquierda (antiguo) a derecha (reciente)")
        await interaction.response.send_message(embed=embed)

    @crypto_group.command(name="comprar", description="Compra criptomonedas desde tu Cuenta Principal.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_comprar(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], monto: int):
        ok, text = self.crypto_buy(interaction.user.id, moneda.value, monto)
        await interaction.response.send_message(text, ephemeral=not ok)

    @crypto_group.command(name="vender", description="Vende un porcentaje de una criptomoneda y cobra al banco.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_vender(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], porcentaje: int):
        ok, text = self.crypto_sell(interaction.user.id, moneda.value, porcentaje)
        await interaction.response.send_message(text, ephemeral=not ok)

    @crypto_group.command(name="cartera", description="Muestra tus criptomonedas y su valor actual.")
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

    # ========================================================
    # /lude admin ...
    # ========================================================

    @admin_group.command(name="listar", description="Lista los ajustes modificables de la economía.")
    async def admin_listar(self, interaction: discord.Interaction, categoria: Optional[str] = None, pagina: int = 1):
        if not await self.require_admin(interaction):
            return
        category = categoria.lower().strip() if categoria else None
        if category and category not in SETTING_CATEGORIES:
            await interaction.response.send_message(
                f"Categoría inválida. Usa: **{', '.join(SETTING_CATEGORIES)}**.", ephemeral=True
            )
            return
        items = [s for s in SETTING_SPECS.values() if category is None or s.category == category]
        items.sort(key=lambda spec: spec.key)
        per_page = 15
        pages = max(1, math.ceil(len(items) / per_page))
        page = max(1, min(int(pagina), pages))
        selected = items[(page - 1) * per_page: page * per_page]
        lines = []
        for spec in selected:
            current = setting_display_value(spec)
            marker = "" if current == spec.default else " ✏️"
            lines.append(f"`{spec.key}` = **{format_setting_value(current)}**{marker}")
        embed = discord.Embed(
            title="⚙️ Lude Admin · Configuración",
            description="\n".join(lines) if lines else "No hay ajustes en esta categoría.",
            color=COLOR,
        )
        embed.set_footer(text=f"Página {page}/{pages} · {len(items)} ajustes · ✏️ = modificado")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_listar.autocomplete("categoria")
    async def admin_categoria_autocomplete(self, interaction: discord.Interaction, current: str):
        if not self.member_is_admin(interaction):
            return []
        current = current.lower()
        return [app_commands.Choice(name=c, value=c) for c in SETTING_CATEGORIES if current in c][:25]

    @admin_group.command(name="ver", description="Muestra un ajuste, su valor actual y el predeterminado.")
    async def admin_ver(self, interaction: discord.Interaction, clave: str):
        if not await self.require_admin(interaction):
            return
        spec = SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.", ephemeral=True)
            return
        current = setting_display_value(spec)
        embed = discord.Embed(title="⚙️ Ajuste de Lude", color=COLOR)
        embed.add_field(name="Clave", value=f"`{spec.key}`", inline=False)
        embed.add_field(name="Descripción", value=spec.label, inline=False)
        embed.add_field(name="Actual", value=f"**{format_setting_value(current)}**", inline=True)
        embed.add_field(name="Predeterminado", value=f"**{format_setting_value(spec.default)}**", inline=True)
        embed.add_field(name="Categoría", value=spec.category, inline=True)
        restrictions = []
        if spec.minimum is not None:
            restrictions.append(f"mín {spec.minimum}")
        if spec.maximum is not None:
            restrictions.append(f"máx {spec.maximum}")
        if spec.choices:
            restrictions.append(" / ".join(spec.choices))
        if restrictions:
            embed.add_field(name="Límites", value=" · ".join(restrictions), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin_group.command(name="cambiar", description="Cambia un ajuste sin editar ni reiniciar el Cog.")
    async def admin_cambiar(self, interaction: discord.Interaction, clave: str, valor: str):
        if not await self.require_admin(interaction):
            return
        spec = SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.", ephemeral=True)
            return
        old = setting_display_value(spec)
        try:
            new = self.update_runtime_setting(clave, valor, interaction.user.id)
        except (ValueError, KeyError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"✅ `{clave}`: **{format_setting_value(old)} → {format_setting_value(new)}**\n"
            "El cambio ya está activo y queda guardado en SQLite.",
            ephemeral=True,
        )

    @admin_group.command(name="restaurar", description="Restaura un ajuste a su valor predeterminado.")
    async def admin_restaurar(self, interaction: discord.Interaction, clave: str):
        if not await self.require_admin(interaction):
            return
        spec = SETTING_SPECS.get(clave)
        if not spec:
            await interaction.response.send_message("Ajuste inexistente.", ephemeral=True)
            return
        old = setting_display_value(spec)
        try:
            default = self.reset_runtime_setting(clave)
        except (ValueError, KeyError) as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"♻️ `{clave}`: **{format_setting_value(old)} → {format_setting_value(default)}** (predeterminado).",
            ephemeral=True,
        )

    def _admin_key_choices(self, interaction: discord.Interaction, current: str):
        if not self.member_is_admin(interaction):
            return []
        current = current.lower().strip()
        matches = [
            spec for spec in SETTING_SPECS.values()
            if current in spec.key.lower() or current in spec.label.lower()
        ]
        matches.sort(key=lambda spec: (not spec.key.lower().startswith(current), spec.key))
        return [app_commands.Choice(name=spec.key[:100], value=spec.key) for spec in matches[:25]]

    @admin_ver.autocomplete("clave")
    async def admin_ver_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)

    @admin_cambiar.autocomplete("clave")
    async def admin_cambiar_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)

    @admin_restaurar.autocomplete("clave")
    async def admin_restaurar_key_autocomplete(self, interaction: discord.Interaction, current: str):
        return self._admin_key_choices(interaction, current)


async def setup(bot: commands.Bot):
    cog = LudeEconomy(bot)
    await bot.add_cog(cog)
    # Guild-specific: sincroniza /lude inmediatamente al cargar/reloadear el Cog.
    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    except discord.HTTPException as exc:
        print(f"[LudeEconomy] No se pudo sincronizar /lude: {exc}")
