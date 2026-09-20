"""Prepare a verified NEW cents-v3 SQLite copy without touching the source.

Run with the Discord bot STOPPED. This tool never changes the original DB,
never replaces a file, and never deploys a resulting copy automatically.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from lude.migrate_money_v3 import MONEY_COLUMNS, migrate_copy

REQUIRED_MARKET21 = {"anchor", "anchor_ticks", "anchor_reference", "flow_baseline"}


def _read_only(path: Path):
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _rows(conn, sql):
    return [tuple(row) for row in conn.execute(sql)]


def _source_checks(conn):
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("La base original no supera PRAGMA integrity_check.")
    table_names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    required = set(MONEY_COLUMNS) | {"crypto_holdings", "crypto_market", "crypto_history", "crypto_engine_state", "casino_state"}
    if not required.issubset(table_names):
        raise ValueError("El archivo no es la base SQLite esperada de Lude Economy.")
    if "lude_schema_meta" in table_names and conn.execute("SELECT value FROM lude_schema_meta WHERE key='money_unit'").fetchone():
        raise ValueError("La base ya tiene una versión monetaria; no se convierte dos veces.")
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crypto_engine_state)")}
    if not REQUIRED_MARKET21.issubset(columns):
        raise ValueError("La base todavía no contiene el esquema de Market Engine 2.1.")
    return {
        "users": conn.execute("SELECT COUNT(*) FROM economy_users").fetchone()[0],
        "accounts": conn.execute("SELECT COUNT(*) FROM bank_accounts").fetchone()[0],
        "positions": conn.execute("SELECT COUNT(*) FROM crypto_holdings").fetchone()[0],
    }


def _money_cents(value):
    return int((Decimal(str(value)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def verify_copy(source: Path, destination: Path) -> dict:
    original, migrated = _read_only(source), _read_only(destination)
    try:
        if migrated.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("La copia migrada no supera PRAGMA integrity_check.")
        marker = migrated.execute("SELECT value FROM lude_schema_meta WHERE key='money_unit'").fetchone()
        if not marker or marker[0] != "cents_v3":
            raise AssertionError("La copia no declara explícitamente centavos v3.")
        for table, columns in MONEY_COLUMNS.items():
            pk = "user_id" if table == "economy_users" else ("user_id,account_type" if table == "bank_accounts" else "id")
            original_sql = f"SELECT {pk},{','.join(columns)} FROM {table}"
            converted_sql = f"SELECT {pk},{','.join(columns)} FROM {table} WHERE 1=1"
            if table == "bank_accounts":
                converted_sql += " AND account_type!='savings'"
            before = _rows(original, original_sql + f" ORDER BY {pk}")
            after = _rows(migrated, converted_sql + f" ORDER BY {pk}")
            expected = [(*row[:-len(columns)], *(_money_cents(v) for v in row[-len(columns):])) for row in before]
            if expected != after:
                raise AssertionError(f"Saldos monetarios cambiaron inesperadamente: {table}.")
        for table, order in (("crypto_market", "symbol"), ("crypto_history", "id"),
                             ("crypto_engine_state", "symbol"), ("crypto_global_state", "id"),
                             ("job_progress", "user_id,job_id")):
            if _rows(original, f"SELECT * FROM {table} ORDER BY {order}") != _rows(migrated, f"SELECT * FROM {table} ORDER BY {order}"):
                raise AssertionError(f"Se alteró un dato no monetario: {table}.")
        base = _rows(original, "SELECT user_id,symbol,quantity,cost_basis FROM crypto_holdings ORDER BY user_id,symbol")
        positions = _rows(migrated, "SELECT user_id,symbol,quantity,cost_basis,cost_basis_cents FROM crypto_holdings ORDER BY user_id,symbol")
        if len(base) != len(positions):
            raise AssertionError("Cambió el número de posiciones de criptomonedas.")
        for a, b in zip(base, positions):
            if a != b[:4] or _money_cents(a[3]) != b[4]:
                raise AssertionError("Se modificó una cantidad cripto o costo de adquisición.")
        original_jackpot = original.execute("SELECT value FROM casino_state WHERE key='slots_jackpot'").fetchone()[0]
        migrated_jackpot = migrated.execute("SELECT value FROM casino_state_cents WHERE key='slots_jackpot'").fetchone()[0]
        if _money_cents(original_jackpot) != migrated_jackpot:
            raise AssertionError("El jackpot no conserva su valor histórico.")
        return {"users": len(_rows(original, "SELECT user_id FROM economy_users")),
                "savings": migrated.execute("SELECT COUNT(*) FROM bank_accounts WHERE account_type='savings'").fetchone()[0],
                "positions": len(positions), "money_unit": marker[0]}
    finally:
        original.close()
        migrated.close()


def prepare(source_path: str, destination_path: str) -> dict:
    source = Path(source_path).expanduser().resolve(strict=True)
    destination = Path(destination_path).expanduser().resolve()
    if source == destination or destination.exists():
        raise FileExistsError("El destino debe ser un archivo NUEVO y diferente; nunca se sobrescribe el original.")
    conn = _read_only(source)
    try:
        preflight = _source_checks(conn)
    finally:
        conn.close()
    result = migrate_copy(str(source), str(destination))
    try:
        verified = verify_copy(source, destination)
        with destination.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        return {"prepared_file": str(destination), "source_unchanged": True,
                "preflight": preflight, "verified": verified, "sha256": digest,
                "next_step": "NO reemplazar ni iniciar el bot: verificar primero respaldo externo y autorizar el despliegue."}
    except Exception:
        # Only unlink the NEW destination created by this function, never source.
        destination.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description="Preparar copia nueva de Lude v3 con centavos; nunca toca la original.")
    parser.add_argument("source", help="Ruta al archivo SQLite ORIGINAL (bot detenido)")
    parser.add_argument("destination", help="Ruta NUEVA para la copia preparada; no debe existir")
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.destination), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
