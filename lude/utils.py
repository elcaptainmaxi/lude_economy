from . import config


def money(value: int | float) -> str:
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
