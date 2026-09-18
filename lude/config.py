from dataclasses import dataclass
from typing import Optional

import discord

GUILD_ID = 1545821075525603358
TESTER_ROLE_ID = 1545942284745576488
ADMIN_OWNER_ID = 1006704642618568735
DB_PATH = "lude_economy.db"

COLOR = discord.Color.from_rgb(88, 101, 242)
COLOR_SUCCESS = discord.Color.from_rgb(46, 204, 113)
COLOR_DANGER = discord.Color.from_rgb(231, 76, 60)
COLOR_GOLD = discord.Color.from_rgb(241, 196, 15)
CURRENCY = "INT$"

WORK_COOLDOWN = 5 * 60
CRIME_COOLDOWN = 5 * 60
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
    "cherry_pair": 0.5, "cherry_triple": 1.5, "lemon_triple": 2.0,
    "bell_triple": 3.0, "diamond_triple": 5.0,
}
BANK_HISTORY_KEEP = 10

CRYPTO_UPDATE_SECONDS = 5 * 60
CRYPTO_FEE_RATE = 0.01
CRYPTO_HISTORY_KEEP = 288
CRYPTO_DYNAMIC_RATE = 0.002
CRYPTO_STABLE_BOOST = 2.5
CRYPTO_FUNDAMENTAL_MAX_STEP = 0.008
CRYPTO_REGIME_SWITCH = 0.035
CRYPTO_SHOCK_CHANCE = 0.003
CRYPTO_GLOBAL_INFLUENCE = 0.12
CRYPTO_UP_EMOJI_ID = 1550285735305941022
CRYPTO_DOWN_EMOJI_ID = 1550285765584625845
MARKET_REGIMES = ("bull", "bear", "sideways", "storm")
MARKET_REGIME_LABELS = {
    "bull": "📈 Alcista", "bear": "📉 Bajista",
    "sideways": "↔️ Consolidación", "storm": "⚡ Volatilidad",
}

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
ADDITIONAL_UPGRADE_COSTS = {5: 100_000, 6: 200_000, 7: 500_000}

GRADE_MULTIPLIERS = {"S": 1.40, "A": 1.20, "B": 1.00, "C": 0.80, "D": 0.55, "F": 0.25}
GRADE_XP_MULTIPLIERS = {"S": 1.40, "A": 1.20, "B": 1.00, "C": 0.80, "D": 0.60, "F": 0.35}

JOBS = {
    "changas": {"name": "Desempleado / Changas", "level": 0, "branch": "Inicial", "salary": (100, 180), "payment": "wallet", "style": "general"},
    "reparador": {"name": "Reparador independiente", "level": 1, "branch": "Oficios", "salary": (100, 180), "payment": "wallet", "style": "trades"},
    "monotributista": {"name": "Monotributista", "level": 1, "branch": "Negocios", "salary": (100, 180), "payment": "wallet", "style": "business"},
    "repartidor": {"name": "Repartidor", "level": 3, "branch": "Servicios", "salary": (140, 230), "payment": "wallet", "style": "services"},
    "cajero": {"name": "Cajero", "level": 3, "branch": "Comercio", "salary": (140, 230), "payment": "bank", "style": "commerce"},
    "mecanico": {"name": "Mecánico", "level": 5, "branch": "Oficios", "salary": (180, 300), "payment": "wallet", "style": "trades"},
    "cocinero": {"name": "Cocinero", "level": 5, "branch": "Gastronomía", "salary": (180, 300), "payment": "bank", "style": "gastronomy"},
    "vendedor": {"name": "Vendedor", "level": 5, "branch": "Comercio", "salary": (180, 300), "payment": "bank", "style": "commerce"},
    "electricista": {"name": "Electricista", "level": 8, "branch": "Oficios", "salary": (230, 360), "payment": "wallet", "style": "trades"},
    "conductor": {"name": "Conductor", "level": 8, "branch": "Servicios", "salary": (230, 360), "payment": "bank", "style": "services"},
    "guardia": {"name": "Guardia de seguridad", "level": 8, "branch": "Seguridad", "salary": (230, 360), "payment": "bank", "style": "security"},
    "tecnico": {"name": "Técnico", "level": 12, "branch": "Tecnología", "salary": (290, 440), "payment": "bank", "style": "technology"},
    "programador-jr": {"name": "Programador Jr.", "level": 12, "branch": "Tecnología", "salary": (290, 440), "payment": "bank", "style": "technology"},
    "administrativo": {"name": "Administrativo", "level": 12, "branch": "Negocios", "salary": (290, 440), "payment": "bank", "style": "business"},
    "policia": {"name": "Policía", "level": 17, "branch": "Seguridad", "salary": (360, 550), "payment": "bank", "style": "security"},
    "enfermero": {"name": "Enfermero", "level": 17, "branch": "Salud", "salary": (360, 550), "payment": "bank", "style": "health"},
    "contador": {"name": "Contador", "level": 17, "branch": "Finanzas", "salary": (360, 550), "payment": "bank", "style": "finance"},
    "ingeniero": {"name": "Ingeniero", "level": 23, "branch": "Tecnología", "salary": (450, 680), "payment": "bank", "style": "technology"},
    "programador-sr": {"name": "Programador Sr.", "level": 23, "branch": "Tecnología", "salary": (450, 680), "payment": "bank", "style": "technology"},
    "arquitecto": {"name": "Arquitecto", "level": 23, "branch": "Profesional", "salary": (450, 680), "payment": "bank", "style": "professional"},
    "medico": {"name": "Médico", "level": 30, "branch": "Salud", "salary": (570, 850), "payment": "bank", "style": "health"},
    "abogado": {"name": "Abogado", "level": 30, "branch": "Derecho", "salary": (570, 850), "payment": "bank", "style": "law"},
    "gerente": {"name": "Gerente", "level": 30, "branch": "Negocios", "salary": (570, 850), "payment": "bank", "style": "business"},
    "cirujano": {"name": "Cirujano", "level": 40, "branch": "Salud", "salary": (750, 1_100), "payment": "bank", "style": "health"},
    "director-ejecutivo": {"name": "Director ejecutivo", "level": 40, "branch": "Negocios", "salary": (750, 1_100), "payment": "bank", "style": "business"},
    "juez": {"name": "Juez", "level": 40, "branch": "Derecho", "salary": (750, 1_100), "payment": "bank", "style": "law"},
    "especialista-elite": {"name": "Especialista élite", "level": 50, "branch": "Profesional", "salary": (950, 1_400), "payment": "bank", "style": "professional"},
}

WORK_MINIGAMES = {
    "general": [("Te ofrecen dos changas al mismo tiempo. ¿Cuál priorizás?", ["La que paga mejor y puedo terminar", "Las dos a la vez", "Ninguna"], 0), ("Un cliente cambia el pedido a último momento.", ["Confirmo el cambio y reorganizo", "Lo ignoro", "Me voy"], 0)],
    "trades": [("Detectás una falla antes de entregar el trabajo.", ["La corrijo y pruebo de nuevo", "La tapo", "Entrego igual"], 0), ("Una herramienta empieza a fallar en medio del trabajo.", ["Paro y la reviso", "La fuerzo", "Improviso sin revisar"], 0)],
    "business": [("Un gasto no coincide con el registro.", ["Reviso comprobantes", "Lo redondeo", "Lo borro"], 0), ("Tenés dos tareas urgentes.", ["Priorizo por impacto y plazo", "Hago la más fácil", "Espero"], 0)],
    "services": [("Hay una demora inesperada en la ruta.", ["Busco una alternativa segura", "Acelero de más", "Cancelo sin avisar"], 0), ("El cliente da una dirección dudosa.", ["La confirmo antes de salir", "Adivino", "Lo dejo en cualquier lado"], 0)],
    "commerce": [("La caja no coincide al cierre.", ["Recuento y reviso movimientos", "Cambio el número", "Lo dejo así"], 0), ("Un cliente reclama un precio distinto.", ["Verifico el precio registrado", "Discuto", "Le cobro cualquier cosa"], 0)],
    "gastronomy": [("Un plato sale con un ingrediente equivocado.", ["Lo rehago", "Lo sirvo igual", "Oculto el ingrediente"], 0), ("Se acumulan pedidos.", ["Ordeno por tiempos de cocción", "Cocino al azar", "Dejo de tomar pedidos"], 0)],
    "security": [("Ves una situación sospechosa pero no confirmada.", ["Observo y sigo protocolo", "Actúo sin verificar", "La ignoro"], 0), ("Dos incidentes ocurren a la vez.", ["Priorizo el de mayor riesgo", "Voy al más cercano sin pensar", "No intervengo"], 0)],
    "technology": [("Un cambio rompe una función que antes servía.", ["Revierto y diagnostico", "Lo despliego igual", "Borro los logs"], 0), ("Un error aparece solo a veces.", ["Reproduzco y registro condiciones", "Lo marco resuelto", "Reinicio y olvido"], 0)],
    "health": [("Dos pacientes necesitan atención.", ["Priorizo por gravedad", "Elijo al azar", "Atiendo al que llegó último"], 0), ("Un dato médico no está claro.", ["Lo verifico antes de actuar", "Lo supongo", "Lo omito"], 0)],
    "finance": [("Un número grande no concilia.", ["Rastreo el asiento", "Lo compenso manualmente", "Lo oculto"], 0), ("Detectás un movimiento duplicado.", ["Lo verifico y corrijo", "Lo dejo", "Duplico otro para equilibrar"], 0)],
    "professional": [("El proyecto tiene un riesgo nuevo.", ["Actualizo el plan y mitigaciones", "Lo ignoro", "Lo oculto"], 0), ("Un cálculo crítico parece extraño.", ["Lo reviso antes de continuar", "Confío sin revisar", "Lo redondeo"], 0)],
    "law": [("Un documento tiene una contradicción.", ["La reviso antes de presentarlo", "La dejo", "Borro una parte sin registrar"], 0), ("Falta una fuente importante.", ["La verifico y documento", "La invento", "La omito"], 0)],
}

CRIME_CATEGORIES = {
    "minor": {"name": "🟢 Menor", "weight": 35, "success": 0.80, "arrest_if_fail": 0.15, "reward": (0.50, 1.00), "fine": (0.25, 0.50), "bail": 0.50, "crimes": ["Carterismo", "Hurto en una tienda", "Estafa callejera", "Robo de bicicleta"]},
    "moderate": {"name": "🔵 Moderado", "weight": 27, "success": 0.65, "arrest_if_fail": 0.30, "reward": (1.00, 2.00), "fine": (0.50, 1.00), "bail": 1.00, "crimes": ["Robo de un domicilio", "Robo de un comercio", "Estafa online", "Robo de motocicleta"]},
    "considerable": {"name": "🟡 Considerable", "weight": 20, "success": 0.50, "arrest_if_fail": 0.45, "reward": (2.00, 3.50), "fine": (1.00, 1.75), "bail": 2.00, "crimes": ["Robo de vehículo", "Contrabando", "Robo de un depósito", "Fraude financiero"]},
    "grave": {"name": "🔴 Grave", "weight": 12, "success": 0.35, "arrest_if_fail": 0.65, "reward": (3.50, 6.00), "fine": (1.75, 3.00), "bail": 3.50, "crimes": ["Robo de joyería", "Robo de camión de valores", "Gran fraude financiero", "Robo de casino"]},
    "extreme": {"name": "🟣 Extremo", "weight": 6, "success": 0.20, "arrest_if_fail": 0.80, "reward": (6.00, 10.00), "fine": (3.00, 5.00), "bail": 6.00, "crimes": ["Robo bancario", "Robo de bóveda", "Golpe al Banco de Interlude"]},
}

CRYPTO_CONFIG = {
    "IC": {"name": "InterCoin", "initial": 1_000.0, "auto_min": 0.01, "auto_max": 0.04, "player_max": 0.02, "reversion_strength": 0.38, "momentum_strength": 0.30, "momentum_cap": 0.06, "liquidity": 15_000.0},
    "NVA": {"name": "Nova", "initial": 250.0, "auto_min": 0.03, "auto_max": 0.09, "player_max": 0.04, "reversion_strength": 0.22, "momentum_strength": 0.40, "momentum_cap": 0.08, "liquidity": 7_500.0},
    "FLX": {"name": "Flux", "initial": 50.0, "auto_min": 0.07, "auto_max": 0.18, "player_max": 0.06, "reversion_strength": 0.08, "momentum_strength": 0.55, "momentum_cap": 0.10, "liquidity": 3_000.0},
}


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
            clone = list(obj); clone[key] = value
            return tuple(clone)
        obj[key] = value
        return obj
    child = obj[key]
    replacement = _deep_set(child, path[1:], value)
    if replacement is not child:
        if isinstance(obj, tuple):
            clone = list(obj); clone[key] = replacement
            return tuple(clone)
        obj[key] = replacement
    return obj


def build_setting_specs() -> dict[str, SettingSpec]:
    specs: dict[str, SettingSpec] = {}

    def add_global(key, category, label, target, default, value_type="float", scale=1.0, minimum=None, maximum=None, choices=()):
        specs[key] = SettingSpec(key, category, label, value_type, default, "global", target, (), scale, minimum, maximum, tuple(choices))

    def add_dict(key, category, label, target, path, default, value_type="float", scale=1.0, minimum=None, maximum=None, choices=()):
        specs[key] = SettingSpec(key, category, label, value_type, default, "dict", target, tuple(path), scale, minimum, maximum, tuple(choices))

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
    symbol_keys = {"🍒": "cherry", "🍋": "lemon", "🔔": "bell", "💎": "diamond", "7️⃣": "seven"}
    for symbol_name, weight in SLOTS_SYMBOL_WEIGHTS.items():
        add_dict(f"casino.slots.weight.{symbol_keys[symbol_name]}", "casino", f"Slots · peso {symbol_name}", "SLOTS_SYMBOL_WEIGHTS", (symbol_name,), weight, minimum=0, maximum=1_000_000)
    for payout_key, payout in SLOTS_PAYOUTS.items():
        add_dict(f"casino.slots.payout.{payout_key}", "casino", f"Slots · retorno {payout_key} (x)", "SLOTS_PAYOUTS", (payout_key,), payout, minimum=0, maximum=10000)
    add_global("bank.history_keep", "bank", "Movimientos bancarios conservados", "BANK_HISTORY_KEEP", 10, "int", minimum=1, maximum=1000)
    add_global("crypto.update_min", "crypto", "Intervalo de actualización cripto (min)", "CRYPTO_UPDATE_SECONDS", 5.0, scale=60, minimum=1, maximum=1440)
    add_global("crypto.fee_pct", "crypto", "Comisión compra/venta cripto (%)", "CRYPTO_FEE_RATE", 1.0, scale=0.01, minimum=0, maximum=100)
    add_global("crypto.history_keep", "crypto", "Registros históricos por cripto", "CRYPTO_HISTORY_KEEP", 288, "int", minimum=2, maximum=10000)
    for level, values in BANK_LEVELS.items():
        add_dict(f"bank.level.{level}.capacity", "bank", f"Capacidad banco nivel {level}", "BANK_LEVELS", (level, "capacity"), values["capacity"], "int", minimum=1)
        add_dict(f"bank.level.{level}.upgrade_cost", "bank", f"Costo mejora banco nivel {level}", "BANK_LEVELS", (level, "upgrade_cost"), values["upgrade_cost"], "int", minimum=0)
    add_global("bank.additional.open_level", "bank", "Nivel inicial cuenta adicional", "ADDITIONAL_OPEN_LEVEL", ADDITIONAL_OPEN_LEVEL, "int", minimum=1, maximum=7)
    add_global("bank.additional.open_cost", "bank", "Costo apertura cuenta adicional", "ADDITIONAL_OPEN_COST", ADDITIONAL_OPEN_COST, "int", minimum=0)
    for level, cost in ADDITIONAL_UPGRADE_COSTS.items():
        add_dict(f"bank.additional.level.{level}.upgrade_cost", "bank", f"Costo adicional nivel {level}", "ADDITIONAL_UPGRADE_COSTS", (level,), cost, "int", minimum=0)
    for grade, value in GRADE_MULTIPLIERS.items():
        add_dict(f"work.grade.{grade}.salary_multiplier", "work", f"Multiplicador salario nota {grade}", "GRADE_MULTIPLIERS", (grade,), value, minimum=0, maximum=20)
    for grade, value in GRADE_XP_MULTIPLIERS.items():
        add_dict(f"work.grade.{grade}.xp_multiplier", "work", f"Multiplicador XP nota {grade}", "GRADE_XP_MULTIPLIERS", (grade,), value, minimum=0, maximum=20)
    for job_id, job in JOBS.items():
        add_dict(f"job.{job_id}.level", "jobs", f"{job['name']} · Work Level", "JOBS", (job_id, "level"), job["level"], "int", minimum=0, maximum=100)
        add_dict(f"job.{job_id}.salary_min", "jobs", f"{job['name']} · salario mínimo", "JOBS", (job_id, "salary", 0), job["salary"][0], "int", minimum=0)
        add_dict(f"job.{job_id}.salary_max", "jobs", f"{job['name']} · salario máximo", "JOBS", (job_id, "salary", 1), job["salary"][1], "int", minimum=0)
        add_dict(f"job.{job_id}.payment", "jobs", f"{job['name']} · destino de pago", "JOBS", (job_id, "payment"), job["payment"], "str", choices=("wallet", "bank"))
    for crime_id, values in CRIME_CATEGORIES.items():
        prefix = f"crime.{crime_id}"
        add_dict(f"{prefix}.weight", "crime", f"{values['name']} · peso de aparición", "CRIME_CATEGORIES", (crime_id, "weight"), values["weight"], minimum=0, maximum=10000)
        add_dict(f"{prefix}.success_pct", "crime", f"{values['name']} · éxito (%)", "CRIME_CATEGORIES", (crime_id, "success"), values["success"] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"{prefix}.arrest_if_fail_pct", "crime", f"{values['name']} · arresto si falla (%)", "CRIME_CATEGORIES", (crime_id, "arrest_if_fail"), values["arrest_if_fail"] * 100, scale=0.01, minimum=0, maximum=100)
        for field, label in (("reward", "recompensa"), ("fine", "multa")):
            add_dict(f"{prefix}.{field}_min_pct", "crime", f"{values['name']} · {label} mínima (% salario)", "CRIME_CATEGORIES", (crime_id, field, 0), values[field][0] * 100, scale=0.01, minimum=0, maximum=10000)
            add_dict(f"{prefix}.{field}_max_pct", "crime", f"{values['name']} · {label} máxima (% salario)", "CRIME_CATEGORIES", (crime_id, field, 1), values[field][1] * 100, scale=0.01, minimum=0, maximum=10000)
        add_dict(f"{prefix}.bail_pct", "crime", f"{values['name']} · fianza (% salario)", "CRIME_CATEGORIES", (crime_id, "bail"), values["bail"] * 100, scale=0.01, minimum=0, maximum=10000)
    add_global("crypto.dynamic_rate", "crypto", "Adaptación base del fundamental por tick", "CRYPTO_DYNAMIC_RATE", 0.002, minimum=0, maximum=0.03)
    add_global("crypto.stable_boost", "crypto", "Aceleración cuando consolida", "CRYPTO_STABLE_BOOST", 2.5, minimum=1, maximum=8)
    add_global("crypto.fundamental_max_step_pct", "crypto", "Variación máxima del fundamental por tick (%)", "CRYPTO_FUNDAMENTAL_MAX_STEP", 0.8, scale=0.01, minimum=0, maximum=5)
    add_global("crypto.regime_switch_pct", "crypto", "Cambio base de régimen por tick (%)", "CRYPTO_REGIME_SWITCH", 3.5, scale=0.01, minimum=0, maximum=100)
    add_global("crypto.shock_chance_pct", "crypto", "Probabilidad de shock global por tick (%)", "CRYPTO_SHOCK_CHANCE", 0.3, scale=0.01, minimum=0, maximum=10)
    add_global("crypto.global_influence", "crypto", "Influencia del mercado global", "CRYPTO_GLOBAL_INFLUENCE", 0.12, minimum=0, maximum=1)
    for symbol, values in CRYPTO_CONFIG.items():
        add_dict(f"crypto.{symbol}.fundamental", "crypto", f"{symbol} · fijar fundamental manualmente", "CRYPTO_CONFIG", (symbol, "initial"), values["initial"], minimum=0.01)
        for field, label in (("auto_min", "volatilidad mínima por tick"), ("auto_max", "volatilidad máxima por tick"), ("player_max", "impacto máximo jugadores"), ("momentum_cap", "tope momentum por tick")):
            add_dict(f"crypto.{symbol}.{field}_pct", "crypto", f"{symbol} · {label} (%)", "CRYPTO_CONFIG", (symbol, field), values[field] * 100, scale=0.01, minimum=0, maximum=100)
        add_dict(f"crypto.{symbol}.reversion_strength", "crypto", f"{symbol} · fuerza de reversión", "CRYPTO_CONFIG", (symbol, "reversion_strength"), values["reversion_strength"], minimum=0, maximum=10)
        add_dict(f"crypto.{symbol}.momentum_strength", "crypto", f"{symbol} · fuerza de momentum", "CRYPTO_CONFIG", (symbol, "momentum_strength"), values["momentum_strength"], minimum=0, maximum=10)
        add_dict(f"crypto.{symbol}.liquidity", "crypto", f"{symbol} · liquidez de referencia", "CRYPTO_CONFIG", (symbol, "liquidity"), values["liquidity"], minimum=1)
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
        raise ValueError("El valor debe ser numérico.") from None
    if spec.minimum is not None and parsed < spec.minimum:
        raise ValueError(f"El mínimo permitido es {spec.minimum}.")
    if spec.maximum is not None and parsed > spec.maximum:
        raise ValueError(f"El máximo permitido es {spec.maximum}.")
    return parsed


def apply_setting_value(spec: SettingSpec, display_value):
    parsed = parse_setting_value(spec, display_value)
    raw = parsed if spec.value_type == "str" else parsed * spec.scale
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
