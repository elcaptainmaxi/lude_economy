"""Offline migration from legacy whole INT$ to integer cents.

NEVER modifies the supplied source database. The bot must be stopped before
using a resulting copy in production, and every original backup must be kept.
"""
from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from .money_v3 import MAX_SQLITE_INT

MONEY_COLUMNS = {
    "economy_users": ("wallet", "bail_due", "judicial_debt"),
    "bank_accounts": ("balance",),
    "bank_history": ("amount", "balance_after"),
}


def _scaled(value, *, legacy_float: bool = False) -> int:
    old = Decimal(str(value))
    if not old.is_finite():
        raise ValueError("El importe original no es finito.")
    new = int((old * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if abs(new) > MAX_SQLITE_INT:
        raise OverflowError("Un importe existente excede el rango SQLite al convertirlo a centavos.")
    if not legacy_float and old != old.to_integral_value():
        raise ValueError("El saldo original contiene fracciones no documentadas; se detuvo la migración.")
    return new


def _schema(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _snapshot(conn):
    names = _schema(conn)
    immutable = {}
    for table in ("crypto_market", "crypto_history", "crypto_engine_state", "crypto_global_state", "job_progress"):
        if table in names:
            immutable[table] = [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY rowid")]
    positions = [tuple(row) for row in conn.execute(
        "SELECT user_id, symbol, quantity, cost_basis FROM crypto_holdings ORDER BY user_id,symbol")]
    return immutable, positions


def migrate_copy(source_path: str, destination_path: str) -> dict:
    """Create and migrate a NEW copy; fail without changing the original.

    Re-running on an already-migrated source is rejected rather than scaling it
    a second time. This function is intentionally not called by bot startup.
    """
    source = Path(source_path).expanduser().resolve(strict=True)
    destination = Path(destination_path).expanduser().resolve()
    if source == destination or destination.exists():
        raise FileExistsError("El destino debe ser un archivo nuevo, distinto del original.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(str(destination))
    try:
        src.backup(dst)
        src.close()
        dst.row_factory = sqlite3.Row
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("La copia original no supera PRAGMA integrity_check.")
        required = set(MONEY_COLUMNS) | {"crypto_holdings", "casino_state", "economy_settings"}
        if not required.issubset(_schema(dst)):
            raise ValueError("Esquema de SQLite no reconocido: faltan tablas de Lude Economy.")
        if "lude_schema_meta" in _schema(dst):
            previous = dst.execute("SELECT value FROM lude_schema_meta WHERE key='money_unit'").fetchone()
            if previous is not None:
                raise ValueError("La base ya tiene una unidad monetaria declarada; no se convierte de nuevo.")
        immutable_before, positions_before = _snapshot(dst)
        dst.execute("BEGIN IMMEDIATE")
        counts = {}
        for table, columns in MONEY_COLUMNS.items():
            records = dst.execute(f"SELECT rowid, {', '.join(columns)} FROM {table}").fetchall()
            for row in records:
                updates = [_scaled(row[col]) for col in columns]
                assignments = ", ".join(f"{col}=?" for col in columns)
                dst.execute(f"UPDATE {table} SET {assignments} WHERE rowid=?", (*updates, row["rowid"]))
            counts[table] = len(records)
        dst.execute("ALTER TABLE crypto_holdings ADD COLUMN cost_basis_cents INTEGER NOT NULL DEFAULT 0")
        positions = dst.execute("SELECT rowid, cost_basis FROM crypto_holdings").fetchall()
        for row in positions:
            dst.execute("UPDATE crypto_holdings SET cost_basis_cents=? WHERE rowid=?",
                        (_scaled(row["cost_basis"], legacy_float=True), row["rowid"]))
        counts["crypto_holdings"] = len(positions)
        # The legacy jackpot has REAL affinity. Use a separate integer table to
        # keep new monetary jackpot accounting exact without rewriting old data.
        dst.execute("CREATE TABLE casino_state_cents (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
        jackpot = dst.execute("SELECT value FROM casino_state WHERE key='slots_jackpot'").fetchone()
        if jackpot is None:
            raise ValueError("Falta el jackpot preexistente.")
        dst.execute("INSERT INTO casino_state_cents(key,value) VALUES ('slots_jackpot',?)",
                    (_scaled(jackpot["value"], legacy_float=True),))
        dst.execute("ALTER TABLE bank_history ADD COLUMN source_account TEXT")
        dst.execute("ALTER TABLE bank_history ADD COLUMN destination_account TEXT")
        dst.execute("ALTER TABLE bank_history ADD COLUMN destination_balance_after INTEGER")
        dst.execute("ALTER TABLE bank_history ADD COLUMN operation_id TEXT")
        dst.execute("CREATE TABLE lude_schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        dst.execute("INSERT INTO lude_schema_meta(key,value) VALUES('money_unit','cents_v3')")
        # Every existing user gets one savings account; bank_accounts PK guards
        # duplicate creation when the new ensure_user() later runs.
        dst.execute("INSERT OR IGNORE INTO bank_accounts(user_id,account_type,level,balance) "
                    "SELECT user_id,'savings',0,0 FROM economy_users")
        immutable_after, positions_after = _snapshot(dst)
        if immutable_before != immutable_after or positions_before != positions_after:
            raise AssertionError("La migración alteró precios, posiciones, trabajo o Market Engine 2.1.")
        for table, columns in MONEY_COLUMNS.items():
            for col in columns:
                rows = dst.execute(f"SELECT {col} FROM {table}").fetchall()
                if any(not isinstance(row[0], int) for row in rows):
                    raise AssertionError(f"Valor monetario no entero: {table}.{col}")
        dst.commit()
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("La copia migrada no supera PRAGMA integrity_check.")
        return {"destination": str(destination), "money_unit": "cents_v3", "converted_rows": counts,
                "savings_accounts": dst.execute("SELECT COUNT(*) FROM bank_accounts WHERE account_type='savings'").fetchone()[0]}
    except Exception:
        dst.rollback()
        dst.close()
        src.close()
        # Remove the incomplete destination, NEVER the source.
        destination.unlink(missing_ok=True)
        raise
    finally:
        try:
            dst.close()
        except Exception:
            pass
        try:
            src.close()
        except Exception:
            pass
