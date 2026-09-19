"""Calibration-only stress runs. Does not connect to Discord, SQLite or production.

From repo root: python -m scripts.stress_final_calibration_21
Shocks are sampled independently per coin here; this is NOT a correlated-market test.
"""
import json
import math
import random
import statistics
from scripts.simulate_market_engine_21 import COINS, State, TICK_SECONDS, clamp, engine_step


def shock_path(symbol, days, seed):
    cfg = COINS[symbol]
    rng = random.Random(seed)
    state = State(fundamental=cfg['initial'], anchor=cfg['initial'])
    price = peak = cfg['initial']
    history = [price]
    max_dd = 0.
    n_shocks = near_floor = 0
    for _ in range(days * 86400 // TICK_SECONDS):
        state.sentiment = clamp(state.sentiment * .87 + rng.uniform(-.15, .15), -1, 1)
        shock = 0.
        if rng.random() < .003:
            shock = rng.choice([-1, 1]) * rng.uniform(.025, .075)
            n_shocks += 1
        price, state = engine_step(symbol, price, state, history, rng=rng, shock=shock)
        history.append(price)
        history = history[-5:]
        peak = max(peak, price)
        max_dd = max(max_dd, 1 - price / peak)
        near_floor += price <= .02
    return {'final': price, 'max_dd': max_dd, 'shocks': n_shocks, 'floor': near_floor}


def paired_orders(symbol, days, seed, amount=500., side='buy'):
    cfg = COINS[symbol]
    prices = [cfg['initial'], cfg['initial']]
    states = [State(fundamental=cfg['initial'], anchor=cfg['initial']) for _ in range(2)]
    histories = [[cfg['initial']], [cfg['initial']]]
    rngs = [random.Random(seed), random.Random(seed)]
    for _ in range(days * 86400 // TICK_SECONDS):
        for i in range(2):
            rng = rngs[i]
            states[i].sentiment = clamp(states[i].sentiment * .87 + rng.uniform(-.15, .15), -1, 1)
            buy = amount if i == 1 and side == 'buy' else 0.
            sell = amount if i == 1 and side == 'sell' else 0.
            prices[i], states[i] = engine_step(symbol, prices[i], states[i], histories[i],
                                               buy=buy, sell=sell, rng=rng)
            histories[i].append(prices[i])
            histories[i] = histories[i][-5:]
    return {'control': prices[0], 'orders': prices[1],
            'log_effect': math.log(prices[1] / prices[0])}


def main():
    for symbol in COINS:
        rows = [shock_path(symbol, 30, seed) for seed in range(30)]
        print(json.dumps({
            'symbol': symbol, 'days': 30, 'seeds': 30,
            'shocked_maxdd_median_pct': round(statistics.median(x['max_dd'] for x in rows) * 100, 2),
            'shocked_maxdd_max_pct': round(max(x['max_dd'] for x in rows) * 100, 2),
            'shocked_price_median': round(statistics.median(x['final'] for x in rows), 4),
            'shocks_median': statistics.median(x['shocks'] for x in rows),
            'floor_runs': sum(x['floor'] > 0 for x in rows),
        }), flush=True)
    for symbol in COINS:
        for side in ('buy', 'sell'):
            rows = [paired_orders(symbol, 7, seed, 500, side) for seed in range(24)]
            median_log = statistics.median(x['log_effect'] for x in rows)
            print(json.dumps({
                'symbol': symbol, 'side': side, 'days': 7, 'runs': 24,
                'median_log_effect': round(median_log, 4),
                'median_price_ratio': round(math.exp(median_log), 4),
                'gross_volume': 500 * 7 * 288,
                'caveat': 'Artificial unlimited orders; paths can diverge despite common initial RNG seeds',
            }), flush=True)


if __name__ == '__main__':
    main()
