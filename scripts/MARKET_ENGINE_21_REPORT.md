# Market Engine 2.1 — resultados reproducibles (prototipo)

**Estado:** experimental; NO integrado en `lude/crypto.py`, NO desplegado en BisectHosting, NO usa `lude_economy.db`. Valores ficticios y semillas determinísticas consecutivas desde cero. No se debe tratar como una garantía del comportamiento futuro.

## Ejecución

Desde la raíz del repositorio (Python 3.11+):

```bash
python -m scripts.test_market_engine_21
python -m scripts.run_market_engine_21 --days 30 90 365 --runs 8 --output market21_results.json
python -m scripts.stress_market_engine_21
```

El simulador ejecuta 288 ticks por día, sin esperar cinco minutos reales. Los resultados de distintos tamaños de muestra pueden variar. Para obtener una muestra mayor, incrementar `--runs`, teniendo en cuenta el tiempo de ejecución.

## Corridas medidas en una ejecución local

Mediana del precio FINAL por escenario (en INT$; no es rentabilidad). Cada columna representa una batería con semillas 0 a N-1; las muestras no son predicciones.

| Escenario | Inicio | 30 días: 30 semillas | 90 días: 12 semillas | 365 días: 8 semillas |
|---|---:|---:|---:|---:|
| IC normal | 1.000 | 982,62 | 1.019,87 | 1.191,93 |
| NVA normal | 250 | 267,68 | 247,91 | 405,00 |
| FLX normal | 50 | 56,96 | 60,97 | 55,47 |
| FLX crash + Bear, fundamental 38 | 0,61 | 31,16 | 59,79 | 108,54 |
| NVA burbuja, fundamental 250 | 625 | 238,84 | 280,95 | 320,14 |

**Cercanía al piso absoluto `INT$0,01`:** ninguna de las corridas anteriores llegó a `INT$0,02` o menos; el tamaño de la muestra NO demuestra ausencia de riesgo.

**Drawdown mediano máximo dentro del recorrido de 365 días** (caída desde un máximo anterior, NO pérdida desde el precio inicial): IC **76,3%**, NVA **89,9%**, FLX **97,5%**. Este es un problema abierto: incluso con medianas finales razonables, los recorridos pueden ser demasiado extremos. En el escenario FLX crash, con ocho semillas y 365 días, el mínimo final en la muestra fue cercano a 2,93 y el máximo superó 800: dispersión considerable.

## Confirmación de fundamental

Con una zona nueva ya establecida al iniciar la prueba: FLX mueve el fundamental recién en el tick 144 (12h); NVA en el 288 (24h); IC en el 576 (48h). Una caída transitoria de dos horas NO mueve el fundamental de ninguna moneda. Desde un ancla VIEJA con un salto inmediato a 60% del precio original, la fase adicional de identificación de zona hace que el primer ajuste ocurra aproximadamente a las 15,58h FLX, 30,33h NVA y 55,25h IC. El reloj de confirmación se cuenta desde que se identifica la zona, no desde el instante del primer salto.

El candidato se calcula con media móvil exponencial en espacio logarítmico; la estabilidad se mide contra una referencia persistente. Comparar cada precio individual con una franja estrecha bloqueaba prácticamente todas las confirmaciones durante las pruebas previas. La referencia y el tiempo de confirmación se mantienen SOLO en la simulación: faltan columnas/migración aditiva para producción.

## Manipulación

En el mismo tick con la misma secuencia aleatoria, una compra de INT$500 causa aproximadamente +0,35% en IC, +0,94% en NVA y +2,00% en FLX frente al escenario sin orden. No garantiza que el tick sea verde.

Doce semillas de **siete días** con **INT$500 de compra en cada tick** (2016 compras, INT$1.008.000 de volumen bruto): mediana de precio final IC **2.667,17**, NVA **776,28**, FLX **259,41**; sin órdenes fueron respectivamente **982,14**, **257,96** y **46,69**. Con INT$500 de venta en cada tick: **434,18**, **89,36** y **10,60**. Aunque la presión individual está acotada, el impacto acumulado es considerable y exige revisión antifraude/de manipulación antes del despliegue. Son trayectorias distintas por RNG, no una medición causal exacta del efecto acumulado.

## Comprobaciones y limitaciones

La prueba local `test_market_engine_21.py` pasó **44 invariantes**: simetría de reversión logarítmica, ventanas de confirmación, crash transitorio, presión de órdenes de ambos signos y ausencia de efecto con volumen cero. `py_compile` pasó para los archivos del prototipo y su ejecutor. **No se han ejecutado los 100 seeds a 90 días ni los 40 seeds a 365 días previamente planteados**: los resultados aquí indicados corresponden a las cantidades realmente ejecutadas.

Faltan todavía integrar y probar shocks globales correlacionados, el bucle/DB reales, migración aditiva, recuperación con distintos estados iniciales e impacto de órdenes repetidas en una economía con restricciones de saldo, comisiones e impuestos. El prototipo no llama a `lude.crypto.market_engine_step`, así que las simulaciones NO certifican el código de producción. No hacer merge ni subir a BisectHosting hasta resolver estos bloqueos.
