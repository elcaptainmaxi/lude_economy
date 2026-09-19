# Market Engine 2.1 — calibración final del **prototipo**

**Alcance y estado:** calibración numérica cerrada para el simulador aislado de esta rama. **No** se modificaron `lude/crypto.py`, `lude/config.py`, `lude/database.py`, la interfaz, `main`, BisectHosting ni `lude_economy.db`. El simulador todavía NO llama al engine de producción: este informe **no** autoriza un despliegue. Son trayectorias ficticias estocásticas, no predicciones ni garantías de ausencia de desplomes.

## Reproducibilidad

Desde la raíz del repositorio (Python 3.11+):

```bash
python -m scripts.test_market_engine_21
python -m scripts.calibrate_market_engine_21 --days 30 90 365 --runs 12 --output calibration.json
python -m scripts.stress_final_calibration_21
```

Cada día simulado tiene 288 ticks (5 minutos ficticios por tick). `simulate` no incluye shocks por defecto; la batería independiente `stress_final_calibration_21.py` los agrega explícitamente. Las pruebas de órdenes repetidas **no** simulan saldos, comisiones, impuestos ni posibilidades reales de operar cada tick. Comparaciones con la misma semilla pueden divergir después de que cambian el precio y las transiciones de régimen.

## Parámetros fijados para el prototipo

Se contrastaron las variantes **baseline, moderate, strong y balanced** con las mismas 12 semillas (0–11) durante 90 días. Se seleccionó **strong** para una validación anual con semillas 0–11 y una muestra separada 100–111. Esto **no** es optimización estadística exhaustiva y hay sesgo de selección: se compararon varias configuraciones contra los mismos primeros escenarios.

| Parámetro | IC | NVA | FLX |
|---|---:|---:|---:|
| Amplitud automática por tick, en retornos logarítmicos | 0,2–0,9% | 0,7–2,6% | 1,6–5,5% |
| Fuerza de momentum | 0,12 | 0,22 | 0,28 |
| Tope de momentum | 1,2% | 3,2% | 4,0% |
| Sesgo por régimen alcista/bajista | ±0,04 | ±0,065 | ±0,09 |
| Multiplicador de reversión | 1,35 | 1,20 | 1,18 |
| Adaptación del fundamental confirmada | 0,0008 | 0,0015 | 0,0018 |
| Tope de ajuste del fundamental por tick | 0,12% | 0,20% | 0,25% |
| Confirmación de zona | 48h | 24h | 12h |

La amplitud automática no es el límite del retorno total: régimen, momentum, compras/ventas y shocks pueden combinarse. Se conserva el piso técnico absoluto de INT$0,01, **sin** piso relativo al fundamental. Los parámetros anteriores están guardados en `scripts/simulate_market_engine_21.py`; no son parámetros activos del bot.

## Comparación controlada: 90 días, 12 semillas (0–11), sin shocks ni órdenes

Las cifras son medianas del **máximo drawdown por recorrido** (caída desde un máximo anterior, no variación desde el precio inicial):

| Escenario | Prototipo anterior | Prototipo calibrado |
|---|---:|---:|
| IC normal | 53,18% | **34,08%** |
| NVA normal | 74,71% | **60,10%** |
| FLX normal | 87,14% | **75,58%** |
| FLX desde 0,59; fundamental 38; Bear | 87,59% | **76,03%** |
| NVA desde 885,31; fundamental 274,60 | 85,11% | **80,12%** |

Las variantes `moderate` y `balanced` también se ejecutaron a 90 días con 12 semillas; sus drawdowns medianos normales fueron, respectivamente, IC 38,52% / 42,95%, NVA 63,77% / 64,38% y FLX 79,99% / 80,17%. Estas observaciones motivaron el ajuste de parámetros, pero no implican que cualquier semilla favorezca la misma configuración.

## Validación anual: 365 días, 12 semillas (0–11), sin shocks ni órdenes

| Moneda | Drawdown mediano anterior | Drawdown mediano calibrado | P90 drawdown calibrado | Precio final mediano calibrado |
|---|---:|---:|---:|---:|
| IC | 64,48% | **45,09%** | 50,61% | INT$981,10 |
| NVA | 83,79% | **72,93%** | 77,84% | INT$225,64 |
| FLX | 94,23% | **83,47%** | 87,98% | INT$65,09 |

**Muestra separada, semillas 100–111, 365 días (12 ejecuciones por moneda):** drawdown máximo mediano IC **43,09%** (P90 48,79%), NVA **67,41%** (P90 71,03%) y FLX **82,31%** (P90 85,81%). Ninguna de estas 72 corridas normales (36 de calibración + 36 de muestra separada) alcanzó INT$0,02, pero la muestra es demasiado pequeña para estimar riesgos extremos. FLX mantiene caídas muy pronunciadas; el precio final mediano no equivale a seguridad ni baja volatilidad.

**Escenarios de capturas:** con FLX empezando en INT$0,59, fundamental 38 y régimen Bear, el precio final mediano a 365 días fue INT$52,05; 12/12 trayectorias cruzaron al menos una vez el 80% del *fundamental inicial* y ninguna tocó el piso. Con NVA empezando en INT$885,31, fundamental 274,60, las 12/12 trayectorias cruzaron al menos una vez 120% del fundamental inicial o menos; precio final mediano INT$242,79. Un cruce temporal no significa recuperación permanente, y estos resultados no predicen el mercado real del servidor. Además, FLX en 30 días con semillas separadas 100–139 recuperó ese umbral en 40/40 recorridos; precio final mediano INT$38,34.

## Shocks y presión de jugadores — pruebas adicionales de calibración

**Shocks independientes por moneda**, probabilidad 0,3% por tick y magnitud de 2,5–7,5% antes del límite específico de cada moneda; 30 días × 30 semillas por moneda. Mediana del máximo drawdown: IC **31,12%**, NVA **55,44%**, FLX **71,61%**; 0/90 recorridos llegaron a INT$0,02. La mediana de shocks generados fue 25,5 / 28 / 27 por recorrido para IC / NVA / FLX. Esta batería **no** verifica shocks correlacionados entre monedas.

**Órdenes constantes ficticias:** 24 semillas, siete días, INT$500 cada tick (2016 órdenes; INT$1.008.000 brutos por escenario). Mediana de la razón precio final *órdenes/control*: compras IC **1,0075×**, NVA **1,0150×**, FLX **1,0168×**; ventas IC **1,0065×**, NVA **1,0263×**, FLX **0,9956×**. Que algunas medianas de ventas superen 1 refleja bifurcaciones de trayectoria; no significa que una venta aislada aumente directamente el precio. El efecto del primer tick se verificó con RNG idéntico: compra de INT$500 suma aproximadamente **0,35% IC / 0,94% NVA / 2,00% FLX** respecto del precio sin compra. Ni estos experimentos ni los límites por tick prueban resistencia completa a manipulación coordinada.

## Comprobaciones ejecutadas y alcance de la decisión

La variante fijada pasó **53 comprobaciones determinísticas** del archivo `scripts/test_market_engine_21.py` y `py_compile` local. Se comprobó que el fundamental se mueve por primera vez tras **576 / 288 / 144 ticks** de zona ya identificada para IC / NVA / FLX; un crash transitorio de dos horas no lo altera. Se hicieron simulaciones anuales y de estrés usando el mismo algoritmo del prototipo (no un modelo aproximado distinto).

**Decisión de esta etapa:** parámetros del *prototipo* fijados para la siguiente fase; **no declarar Market Engine 2.1 listo para producción**. Persisten drawdowns sustanciales, especialmente en FLX, incertidumbre en colas raras, shocks globales y manipulación con restricciones reales. Por pedido del usuario, **no** se inició integración en el bot, migración SQLite, pruebas de integración, cambios de interfaz, merge ni despliegue. El informe anterior describía mediciones de una calibración previa y queda sustituido por estas cifras de la variante fijada.
