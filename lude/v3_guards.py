"""Fail closed when SQLite tries to promote integer money to REAL on overflow.

SQLite INTEGER arithmetic promotes an overflowing result to floating point. A
financial amount must remain an exact nonnegative signed 64-bit integer.
"""
from __future__ import annotations


def install_guards(conn):
    """Add idempotent database-side safety constraints to a migrated v3 DB."""
    definitions = {
        "economy_users": ("wallet", "bail_due", "judicial_debt"),
        "bank_accounts": ("balance",),
        "crypto_holdings": ("cost_basis_cents",),
        "casino_state_cents": ("value",),
    }
    for table, fields in definitions.items():
        condition = " OR ".join(
            f"typeof(NEW.{field}) != 'integer' OR NEW.{field} < 0" for field in fields
        )
        for action in ("INSERT", "UPDATE"):
            trigger = f"lude_v3_guard_{table}_{action.lower()}"
            conn.execute(f"""CREATE TRIGGER IF NOT EXISTS {trigger}
                BEFORE {action} ON {table}
                FOR EACH ROW WHEN {condition}
                BEGIN
                    SELECT RAISE(ABORT, 'Lude v3: monetary overflow or non-integer amount');
                END""")
    # Runtime changes should not silently create a negative account or debt.
    for table, fields in definitions.items():
        query = "SELECT COUNT(*) FROM " + table + " WHERE " + " OR ".join(
            f"typeof({field}) != 'integer' OR {field} < 0" for field in fields
        )
        if conn.execute(query).fetchone()[0]:
            raise ValueError(f"Se detectaron importes no enteros o negativos en {table}; se rechazó el inicio de Lude v3.")
