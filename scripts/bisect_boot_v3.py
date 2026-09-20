"""Prepare Lude v3 at the very beginning of bot.py on hosts without a terminal.

This ONLY creates two new files. It never replaces the live DB, imports the
Discord bot, or starts the economy. Remove the temporary bot.py call after
collecting the preparation logs and downloading the original backup.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .backup_lude_v3 import create_backup
from .prepare_full_v3 import prepare, verify_copy


def prepare_from_bot_start(db_path: str = "/home/container/lude_economy.db") -> dict:
    """Produce an independent SQLite backup and a verified cents-v3 copy.

    Call this at the TOP of bot.py, before any Discord bot/cog setup, and then
    raise SystemExit. It must run in exactly one process, with no other bot
    instance writing to the database. Existing outputs are NEVER overwritten.
    """
    source = Path(db_path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise FileNotFoundError(f"No se encuentra la base SQLite: {source}")
    backup = source.with_name(f"{source.stem}.pre-v3-backup.db")
    prepared = source.with_name(f"{source.stem}.prepared-v3.db")
    if backup.exists() or prepared.exists():
        raise FileExistsError(
            "Hay archivos de preparación anteriores. NO se sobrescribió nada. "
            f"Revisá en el File Manager: {backup.name} y {prepared.name}."
        )
    print("[LUDE V3] Modo preparación: el bot NO se conectará a Discord.", flush=True)
    print("[LUDE V3] Creando respaldo SQLite independiente sin modificar la base activa…", flush=True)
    backup_report = create_backup(str(source), str(backup))
    print("[LUDE V3] Respaldo íntegro. Preparando copia en centavos…", flush=True)
    prepared_report = prepare(str(backup), str(prepared))
    # verify_copy checks all monetary columns, position quantities, Market 2.1
    # state, prices, volumes, XP and jackpot against the *backup snapshot*.
    verified = verify_copy(backup, prepared)
    if verified != prepared_report["verified"]:
        raise AssertionError("El informe de verificación cambió entre comprobaciones.")
    with backup.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != backup_report["sha256"]:
            raise AssertionError("El checksum del respaldo no coincide.")
    report = {
        "status": "PREPARED_ONLY_NOT_ACTIVATED",
        "active_database_unchanged": str(source),
        "backup_to_download_outside_hosting": backup_report,
        "prepared_copy": prepared_report,
        "next_step": (
            "NO reinicies el bot normal ni reemplaces la base todavía. "
            "Descargá y verificá el respaldo desde el File Manager; "
            "después confirmá el resultado para preparar la activación separada."
        ),
    }
    print("[LUDE V3] " + json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report
