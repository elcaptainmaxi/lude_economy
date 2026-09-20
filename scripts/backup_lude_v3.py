"""Create a NEW, verified, independent SQLite backup; NEVER overwrite source.

The bot should be stopped. SQLite's online backup API safely includes WAL data,
unlike copying only a live .db file with a file manager.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def create_backup(source_path: str, target_path: str) -> dict:
    source = Path(source_path).expanduser().resolve(strict=True)
    target = Path(target_path).expanduser().resolve()
    if source == target or target.exists():
        raise FileExistsError("El respaldo debe tener una ruta NUEVA, distinta del origen; no se sobrescribe ningún archivo.")
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite original no supera la comprobación de integridad.")
        src.backup(dst)
        dst.commit()
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("El respaldo no supera la comprobación de integridad.")
        for table in ("economy_users", "bank_accounts", "crypto_holdings", "crypto_market"):
            rows_source = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            rows_copy = dst.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if rows_source != rows_copy:
                raise AssertionError(f"El respaldo tiene distinta cantidad de filas en {table}.")
        dst.close(); dst = None
        with target.open("rb") as handle:
            sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
        return {"backup_path": str(target), "sha256": sha256,
                "integrity_check": "ok", "source_unchanged": True,
                "instruction": "Conservar el respaldo fuera de BisectHosting antes de iniciar la migración."}
    except Exception:
        if dst is not None:
            dst.close(); dst = None
        target.unlink(missing_ok=True)
        raise
    finally:
        src.close()
        if dst is not None:
            dst.close()


def main():
    parser = argparse.ArgumentParser(description="Crear copia de respaldo NUEVA con SQLite y comprobar su integridad.")
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    print(json.dumps(create_backup(args.source, args.destination), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
