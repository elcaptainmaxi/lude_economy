"""Switch the EXISTING economy to integer cents only on a migrated v3 DB.

All persisted economy_settings remain user-facing INT$ values. Percentages,
crypto prices/liquidity, time intervals, XP and Market Engine 2.1 are unchanged.
"""
from __future__ import annotations

from decimal import Decimal

from .money_v3 import MAX_SQLITE_INT, cents

_ACTIVE = False
_ORIGINAL_APPLY = None
_ORIGINAL_DISPLAY = None


def is_monetary_spec(spec) -> bool:
    key = spec.key
    return (key in {"rob.protection_cost", "casino.min_bet", "slots.jackpot_base",
                    "bank.additional.open_cost"}
            or (key.startswith("bank.level.") and key.endswith((".capacity", ".upgrade_cost")))
            or (key.startswith("bank.additional.level.") and key.endswith(".upgrade_cost"))
            or (key.startswith("job.") and key.endswith((".salary_min", ".salary_max"))))


def activate(config, utils):
    """Activate once per process, before loading persisted admin settings."""
    global _ACTIVE, _ORIGINAL_APPLY, _ORIGINAL_DISPLAY
    if _ACTIVE:
        utils.MONEY_CENTS_ACTIVE = True
        return
    # Scale each distinct config target just once (specs may reference tuples).
    for spec in config.SETTING_SPECS.values():
        if not is_monetary_spec(spec):
            continue
        if spec.target_kind == "global":
            original = getattr(config, spec.target_name)
            scaled = int(original) * 100
            if scaled > MAX_SQLITE_INT:
                raise OverflowError(f"Configuración demasiado grande: {spec.key}")
            setattr(config, spec.target_name, scaled)
        else:
            root = getattr(config, spec.target_name)
            value = config._deep_get(root, spec.path)
            scaled = int(value) * 100
            if scaled > MAX_SQLITE_INT:
                raise OverflowError(f"Configuración demasiado grande: {spec.key}")
            config._deep_set(root, spec.path, scaled)
    _ORIGINAL_APPLY = config.apply_setting_value
    _ORIGINAL_DISPLAY = config.setting_display_value

    def display(spec):
        if is_monetary_spec(spec):
            raw = config._setting_raw_value(spec)
            return float(Decimal(int(raw)) / Decimal(100))
        return _ORIGINAL_DISPLAY(spec)

    def apply(spec, value):
        if not is_monetary_spec(spec):
            return _ORIGINAL_APPLY(spec, value)
        parsed_cents = cents(str(value), allow_zero=True)
        display_value = Decimal(parsed_cents) / Decimal(100)
        # Specs specify validation limits in whole INT$, not in cents.
        if spec.minimum is not None and display_value < Decimal(str(spec.minimum)):
            raise ValueError(f"El mínimo permitido es {spec.minimum}.")
        if spec.maximum is not None and display_value > Decimal(str(spec.maximum)):
            raise ValueError(f"El máximo permitido es {spec.maximum}.")
        if spec.target_kind == "global":
            setattr(config, spec.target_name, parsed_cents)
        else:
            root = getattr(config, spec.target_name)
            config._deep_set(root, spec.path, parsed_cents)
        return int(display_value) if display_value == int(display_value) else float(display_value)

    config.setting_display_value = display
    config.apply_setting_value = apply
    utils.MONEY_CENTS_ACTIVE = True
    _ACTIVE = True


def has_cents_schema(conn) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lude_schema_meta'").fetchone()
    if not row:
        return False
    unit = conn.execute("SELECT value FROM lude_schema_meta WHERE key='money_unit'").fetchone()
    if not unit:
        return False
    if unit[0] != 'cents_v3':
        raise RuntimeError(f"Versión monetaria no reconocida: {unit[0]!r}")
    return True
