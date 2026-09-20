# Lude v3 sin terminal de BisectHosting — preparación mediante `bot.py`

**Primera fase solamente: preparar copias; NO activa la actualización.** El bot no se conectará a Discord mientras esté instalado el bloque temporal. Los tests del repositorio no prueban la DB real.

1. Desde el File Manager de BisectHosting, descargá y guardá fuera del hosting el código anterior. Comprobá que podés detener el bot y que hay **una sola instancia**. No publiques `bot.py` si incluye tu token.
2. Detené el servidor. Subí **todos los archivos de la rama** `feature/lude-full-update-cents-savings`, incluidos `lude/`, `scripts/` y el `lude_economy.py` si se usa como extensión. No borres ni sobreescribas `lude_economy.db` o sus ficheros `-wal` y `-shm`. No mezcles módulos de revisiones distintas. GitHub y BisectHosting no se sincronizan automáticamente.
3. Abrí el `bot.py` de BisectHosting y pegá lo siguiente **en la primera línea, antes de importar/cargar el bot**:

   ```python
   # TEMPORAL: preparar Lude v3 sin terminal. Quitar antes de ejecutar el bot normalmente.
   from scripts.bisect_boot_v3 import prepare_from_bot_start
   prepare_from_bot_start('/home/container/lude_economy.db')
   raise SystemExit('LUDE V3: preparación finalizada; el bot queda detenido a propósito.')
   ```

   Si `bot.py` ejecuta código antes de ese bloque, mové el bloque al comienzo. El directorio `scripts/` debe estar junto a `bot.py` y contener el archivo `bisect_boot_v3.py`.
4. Iniciá el servidor una sola vez y abrí **Console/Logs**. Debe aparecer `"status": "PREPARED_ONLY_NOT_ACTIVATED"` seguido de `"money_unit": "cents_v3"`. El servidor quedará apagado a propósito. Si aparece una excepción, **no continués**: conservá todo y compartí el traceback sin tokens. Si BisectHosting reinicia automáticamente el proceso, detenelo mediante el panel: el programa rechaza sobrescribir sus archivos de salida.
5. En el File Manager deben aparecer **tres** bases: `lude_economy.db` (original, sin cambiar), `lude_economy.pre-v3-backup.db` (respaldo SQLite consistente) y `lude_economy.prepared-v3.db` (copia nueva migrada). Descargá `lude_economy.pre-v3-backup.db` fuera de BisectHosting y comprobá que se puede abrir, que su tamaño no es cero y que su SHA-256 coincide con el valor de los logs. Guardá también una copia del código antiguo. La preparación no reemplaza ni elimina la base original.
6. **No cambies `bot.py` a modo normal, no reemplaces la base y no fusiones el PR todavía.** Compartí solo el resultado de preparación (`status`, `integrity_check`, `verified`, `sha256`; sin tokens, IDs personales ni contenidos privados). La activación requiere una segunda fase con comprobación y autorización explícita tras verificar el respaldo externo.

### Si hay un error o querés cancelar

Detené el servidor y conservá los archivos originales y de respaldo. Restaurá `bot.py` y el **código antiguo junto con la base antigua** para volver a la versión previa. No arranques el código nuevo con la base antigua, ni el antiguo con la base en centavos. No intentes la conversión dos veces ni borres el respaldo para forzar otra ejecución.

La vía con terminal sigue documentada en `scripts/LUDE_V3_RELEASE.md`.
