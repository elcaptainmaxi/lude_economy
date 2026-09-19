"""Opt-in, additive Market Engine 2.1 schema migration.

This module NEVER opens a database on import, and is NOT invoked by init_db.
Run only against an OFFLINE COPY during preparation. An explicit deployment
procedure will be needed before this can be used on a live economy.
"""
from __future__ import annotations

import math
import sqlite3

# Existing production table keeps its original columns and rows.
NEW_COLUMNS = {
    "anchor": "REAL NOT NULL DEFAULT 0",
    "anchor_ticks": "INTEGER NOT NULL DEFAULT 0",
    "anchor_reference": "REAL NOT NULL DEFAULT 0",
    "flow_baseline": "REAL NOT NULL DEFAULT 0",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate_crypto_21(conn: sqlite3.Connection) -> None:
    """Idempotent schema-only migration with lossless initialization.

    Caller must hold an exclusive transaction / ensure the bot is stopped.
    This function does not commit; the caller controls rollback and commit.
    Existing nonzero anchors and flow baselines are never overwritten.
    """
    present = _columns(conn, "crypto_engine_state")
    if not {"symbol", "fundamental", "regime", "regime_ticks", "volatility", "pressure", "stable_ticks"}.issubset(present):
        raise RuntimeError("Missing or unexpected crypto_engine_state schema")
    if not {"symbol", "price"}.issubset(_columns(conn, "crypto_market")):
        raise RuntimeError("Missing crypto_market schema")

    for name, declaration in NEW_COLUMNS.items():
        if name not in present:
            conn.execute(f"ALTER TABLE crypto_engine_state ADD COLUMN {name} {declaration}")

    # Seed anchors from the LAST EXISTING market price, never the initial
    # coin price: preserving a crashed/bubbled market is essential.
    conn.execute("""
        UPDATE crypto_engine_state
           SET anchor = (SELECT m.price FROM crypto_market AS m
                          WHERE m.symbol = crypto_engine_state.symbol)
         WHERE anchor = 0
           AND EXISTS (SELECT 1 FROM crypto_market AS m
                        WHERE m.symbol = crypto_engine_state.symbol)
    """)
    conn.execute("""
        UPDATE crypto_engine_state SET anchor_reference = anchor
         WHERE anchor_reference = 0 AND anchor > 0
    """)

    # Do not invent a fundamental, alter price or silently clear order volume.
    for symbol, price, fundamental, anchor, reference, ticks, baseline in conn.execute("""
        SELECT e.symbol, m.price, e.fundamental, e.anchor,
               e.anchor_reference, e.anchor_ticks, e.flow_baseline
          FROM crypto_engine_state AS e
          LEFT JOIN crypto_market AS m ON m.symbol = e.symbol
    """):
        if (price is None or not all(math.isfinite(float(v)) for v in
                                    (price, fundamental, anchor, reference, baseline))
                or min(float(price), float(fundamental), float(anchor), float(reference)) <= 0
                or int(ticks) < 0 or abs(float(baseline)) > 1):
            raise RuntimeError(f"Invalid 2.1 market state for {symbol}; rolling back")


def migrate_offline_copy(path: str) -> None:
    """Migrate an explicitly supplied copy; never uses config.DB_PATH."""
    conn = sqlite3.connect(path, timeout=15)
    try:
        conn.execute("BEGIN EXCLUSIVE")
        migrate_crypto_21(conn)
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
