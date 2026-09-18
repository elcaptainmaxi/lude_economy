# Market Engine 2.1 — informe experimental de calibración

**Estado:** código de simulación aislado, **NO** integrado en `lude/crypto.py`, **NO** desplegado en BisectHosting. Los valores son datos ficticios y no predicciones. Ninguna prueba utiliza `lude_economy.db`.

## Ejecutar desde la raíz del repositorio

```bash
python -m scripts.test_market_engine_21
python -m scripts.run_market_engine_21 --days 30 90 --runs 12 --output market21_results.json
python -m scripts.stress_market_engine_21
python -m scripts.stress_correlated_shocks_21
```

Cada día simulado contiene 288 ticks, sin esperas reales. El prototipo ahora recibe `shock` en `engine_step`, pero el ejecutor `run_market_engine_21` simula **sin shocks** por defecto. Para shocks globales correlacionados entre las tres monedas se usa `stress_correlated_shocks_21.py`. No confundir sus métricas ni sumar sus muestras.

## Cambios calibrados en esta iteración

- Reversión de valoración simétrica en distancia logarítmica, más sensible desde desviaciones moderadas. No fija un piso artificial relativo al fundamental ni garantiza recuperación.
- Menor sesgo por regímenes, y amplitud/momentum de FLX reducidos sin igualar su volatilidad a IC o NVA.
- **Antimanipulación por flujo persistente:** `flow_baseline` recuerda el flujo habitual; el impacto responde a la *innovación* (cambio respecto de ese flujo), no vuelve a otorgar el mismo aumento en cada tick idéntico. Requiere persistir `flow_baseline` en la futura migración. La compra inicial sigue influyendo, pero su repetición constante decae. Puede haber impacto residual y transiciones de régimen; no es una garantía contra manipulación coordinada.
- `engine_step` admite un shock exógeno opcional; su impacto se limita a ±60% del `auto_max` de la moneda. La prueba de correlación pasa el **mismo shock** y sentimiento a las tres monedas.

## Resultados medidos — ejecutor sin shocks

12 semillas (0–11), 90 días; mediana del precio **final** y mediana del *drawdown máximo* (desde máximo previo, no respecto del inicio):

| Escenario | Precio final mediano (INT$) | Drawdown máximo mediano | Llegó a ≤INT$0,02 |
|---|---:|---:|---:|
| IC normal | 1.128,59 | 53,2% | 0/12 |
| NVA normal | 252,94 | 74,7% | 0/12 |
| FLX normal | 52,68 | 87,1% | 0/12 |
| FLX desde 0,61 / fundamental 38 / Bear | 56,37 | 86,5% | 0/12 |
| NVA burbuja 625 / fundamental 250 | 272,06 | 81,6% | 0/12 |

La amplitud y los drawdowns continúan siendo elevados: **NO** interpretar la mediana final como evidencia de poco riesgo. Una corrida de 365 días con **6 semillas** alcanzó IC mediana 1.189,64 / drawdown 61,8%, NVA mediana 291,56 / drawdown 82,1%, FLX mediana 127,02 / drawdown 94,8%; la ejecución fue interrumpida antes de completar los otros dos escenarios, por lo que **no es una batería anual completa**. No se han ejecutado aún las 40 semillas anuales propuestas.

## Órdenes repetidas y shocks compartidos

Estrés de siete días con 12 semillas, compras de INT$500 **cada tick** (2016 órdenes; volumen bruto INT$1.008.000), precios finales medianos:

| Moneda | Sin órdenes | Compras continuas | Ventas continuas |
|---|---:|---:|---:|
| IC | 982,33 | 1.047,60 | 927,37 |
| NVA | 221,12 | 228,06 | 229,37 |
| FLX | 45,58 | 48,57 | 47,06 |

Las trayectorias divergen por bifurcaciones de RNG y retroalimentación de régimen: son resultados de estrés, **no** una estimación causal de cada orden. Las ventas no tienen por qué garantizar un cierre menor en todas las semillas.

En una simulación conjunta de 30 días × 12 semillas, se registraron **17–29 shocks por corrida**, todos aplicados simultáneamente a IC/NVA/FLX. Drawdown máximo mediano **sin / con shocks**: IC 46,4% / 50,1%; NVA 71,3% / 70,7%; FLX 82,7% / 83,1%. Las dos variantes comparten semillas, pero bifurcan su consumo aleatorio después de ciertos shocks; no son diferencias causales exactas.

## Pruebas y pendientes

Se ejecutaron localmente **53 comprobaciones determinísticas** (incluidas confirmación del fundamental FLX 12h / NVA 24h / IC 48h, caída de dos horas, saturación de flujo y shock de ambos signos) y `py_compile` de los scripts correspondientes. Las ejecuciones no certifican todavía la integración de producción.

**Bloqueos antes de desplegar:** integrar y probar el mismo engine en `lude/crypto.py` en esta rama, migración SQLite puramente aditiva que preserve precios, holdings, balances e historial, reinicios con `flow_baseline` persistente, shocks realmente compartidos en el loop de producción y pruebas de cargas/concurrencia con límites de saldo y comisiones. Hacen falta muestras anuales mayores y revisar drawdowns persistentes, sobre todo FLX. No hacer merge ni sustituir archivos en BisectHosting todavía.
