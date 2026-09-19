from . import config

# Enabled only after the v3 schema marker was verified, before any cog runs.
MONEY_CENTS_ACTIVE = False


def money(value: int | float) -> str:
    if MONEY_CENTS_ACTIVE:
        from decimal import Decimal
        from .money_v3 import format_cents, round_cents
        if isinstance(value, int):
            return format_cents(value)
        # Float inputs are legacy market prices/estimated investments in INT$;
        # persisted wallet/account/debt values must always be integer cents.
        return format_cents(round_cents(Decimal(str(value))))
    if isinstance(value, float) and not value.is_integer():
        formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{config.CURRENCY} {formatted}"
    return f"{config.CURRENCY} {int(round(value)):,}".replace(",", ".")


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
