# Lude Economy v3 — actualización completa, centavos reales

**Estado: release candidate en rama `feature/lude-full-update-cents-savings`. NO se despliega automáticamente.** Los tests CI usan bases temporales, NO la base real del servidor.

## Incluido

- Todos los saldos, salarios, multas, fianzas, apuestas, comisiones y retenciones expresados internamente en **centavos enteros**. El usuario introduce `7500,25` y ve `INT$ 7.500,25`. El parser admite punto O coma decimal, pero no separadores de miles.
- Cuenta **Ahorro** automática por usuario, sin límite bancario de producto, sin comisiones ni intereses iniciales (límite técnico del entero SQLite). Transferencias propias gratuitas entre Principal, Adicional y Ahorro; depósitos directos Wallet→Ahorro y retiros Ahorro→Wallet.
- `/lude crypto mercado`: una cripto por página, últimas cinco variaciones, tendencia, fundamental, régimen y próximo tick. `/lude crypto cartera`: resumen y detalle individual; botón Vender solo en detalle. Todos los controles públicos son exclusivos de quien abrió el panel.
- `/lude crypto vender`: unidades hasta ocho decimales, porcentaje decimal o **INT$ netos tras comisión y retención judicial**; cuenta Ahorro predeterminada y destinos alternativos; reconfirmación si varía cotización, saldo o destino. Venta SQLite atómica y recibo que evita doble acreditación.
- Configuraciones administrativas monetarias convertidas dinámicamente a centavos; cotizaciones, cantidades y volúmenes del Market Engine 2.1 **conservan su unidad económica original**.
- `/lude estado` se consolida en `/lude panel`; `/lude mover-banco` se sustituye por `/lude mover-fondos` para respetar el límite de 25 comandos directos de Discord.

## Antes de desplegar: imprescindible

1. **Detener el bot en BisectHosting y confirmar que no se reinicia automáticamente** durante el procedimiento. Nadie debe operar mientras se generan las copias. Asegurarse de disponer de Python 3.12 y un método de ejecución de scripts/terminal; si no hay terminal en BisectHosting, realizar el procedimiento en un equipo con Python tras obtener una copia SQLite consistente, sin copiar solo un `.db` mientras sigue escribiendo un proceso.
2. Mantener una copia **independiente** de la versión anterior del código y crear un respaldo SQLite NUEVO mediante la API SQLite (incluye cualquier WAL pendiente):

   ```bash
   python -m scripts.backup_lude_v3 /home/container/lude_economy.db /home/container/lude_economy-pre-v3-backup.db
   ```

   Verificar que devuelve `integrity_check: ok`, ruta nueva y `sha256`. **Descargar el archivo de respaldo fuera del hosting** y conservarlo. El respaldo original no se transforma ni se sobrescribe.
3. Con el bot todavía detenido, generar una SEGUNDA copia migrada usando la rama v3, **sin modificar el archivo original**:

   ```bash
   python -m scripts.prepare_full_v3 /home/container/lude_economy.db /home/container/lude_economy-prepared-v3.db
   ```

   El script rechaza una segunda migración, destino preexistente, falta de Market Engine 2.1, fallos de integridad o diferencias en saldos, deuda, criptomonedas, mercados, XP o jackpot. Debe terminar con `verified.money_unit: cents_v3` y un `sha256`.
4. **Punto de aprobación de producción:** comprobar en la base real detenida que el respaldo externo se puede abrir, las cifras y posiciones actuales coinciden con el informe de preflight y que la copia v3 ha superado la verificación. No sustituir la base hasta confirmar esto con el dueño del bot.
5. Una vez aprobado el cambio, conservar el respaldo anterior, instalar **todos** los módulos de `lude/` y el `lude_economy.py` de la misma revisión de la rama, y sustituir el archivo de datos por **la copia migrada verificada**, con el bot detenido. El nombre activo continuará siendo `/home/container/lude_economy.db`. No mezclar archivos antiguos/nuevos ni ejecutar `migrate_copy` sobre el archivo activo.
6. Arrancar **una sola instancia** del bot; comprobar en Discord `/lude panel`, `/lude ahorro`, `/lude banco`, `/lude crypto mercado`, `/lude crypto cartera`; verificar saldo Wallet, Principal, Adicional, Ahorro, deuda judicial y las unidades FLX/IC/NVA antes de permitir operaciones. Seguir el primer tick real del Market Engine 2.1 y comprobar que no cambian posiciones o saldos sin transacciones.

## Reversión

Detener el bot, recuperar **juntos** el código antiguo y el respaldo SQLite antiguo verificado; nunca arrancar el código antiguo contra la base en centavos, ni el código v3 contra la base antigua. Si ocurrieron transacciones reales durante v3, restaurar el respaldo anterior las perdería: detener y reconciliar esos movimientos antes de decidir volver atrás.

## Tests automatizados y límites

GitHub Actions compila todos los módulos y prueba parsing, migración copy-only, cotización neta, venta atómica/idempotente, transferencias propias, casino Slots, registro de slash commands, precios/volúmenes y ejecución real del tick de Market Engine 2.1 sobre SQLite **ficticia**. Estas pruebas no equivalen a verificar el estado de la base real ni la conectividad de Discord/BisectHosting. La única operación potencialmente irreversible es reemplazar la base activa; requiere aprobación explícita tras verificar el respaldo.
