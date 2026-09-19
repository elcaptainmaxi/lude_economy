# Market Engine 2.1: migración preparada, sin despliegue

`lude/crypto_21_migration.py` es una migración **opt-in**: no se importa ni se ejecuta desde `init_db` ni se conecta automáticamente a BisectHosting. Este paso NO actualiza la base de datos real.

En una copia SQLite **con el bot detenido**, `migrate_offline_copy(ruta_explicita)` abre una transacción exclusiva, agrega con `ALTER TABLE` solamente `anchor`, `anchor_ticks`, `anchor_reference` y `flow_baseline` cuando faltan; inicializa ancla y referencia desde el **precio existente** de cada moneda, no desde el valor inicial de configuración. No altera `fundamental`, precios, volúmenes pendientes, saldos, tenencias ni historial. Si el estado existente no es válido, revierte toda la transacción. La segunda ejecución no elimina el estado 2.1 ya guardado.

Prueba aislada, sin Discord ni DB de producción: `python -m scripts.test_crypto_21_migration`. La prueba utiliza SQLite `:memory:` con precios de referencia FLX 0.59, NVA 885.31, IC 1783.88 y verifica conservación de tablas, idempotencia y rollback. **Las pruebas de integración del bot, reinicios y despliegue son pasos posteriores**.

**Precaución:** cuando se ejecute deliberadamente la migración sobre el archivo usado por el bot experimental, `CryptoMixin21` detectará las columnas y empezará a utilizar 2.1. Por eso NO ejecutar sobre la DB activa ni copiar el branch a BisectHosting en esta etapa. Antes de un eventual despliegue se necesita una copia de seguridad verificable, parada completa del bot y pruebas de integración.