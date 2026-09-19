"""Reproducible final-calibration experiment; never opens Discord or SQLite.

Run from repository root:
  python -m scripts.calibrate_market_engine_21 --runs 40 --days 30 90 365

This script reports observations; it deliberately does not label a parameter set
'approved' from a small sample or silently modify production settings.
"""
import argparse
import json
import math
import random
import statistics
from dataclasses import replace
from pathlib import Path

from scripts.simulate_market_engine_21 import (
    COINS, State, TICK_SECONDS, clamp, engine_step, simulate,
)

SCENARIOS = (
    ('IC', 'normal', None, None, 'sideways'),
    ('NVA', 'normal', None, None, 'sideways'),
    ('FLX', 'normal', None, None, 'sideways'),
    ('FLX', 'crash_059', .59, 38., 'bear'),
    ('FLX', 'crash_061', .61, 38., 'bear'),
    ('NVA', 'bubble_885', 885.31, 274.60, 'sideways'),
    ('NVA', 'bubble_625', 625., 250., 'bull'),
    ('IC', 'storm_1784', 1783.88, 1040., 'storm'),
)


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    low = int(position)
    high = min(len(values) - 1, low + 1)
    return values[low] + (values[high] - values[low]) * (position - low)


def summarize(rows):
    def summary(key):
        values = [float(row[key]) for row in rows]
        return {'p10': percentile(values, .1), 'median': statistics.median(values),
                'p90': percentile(values, .9), 'worst': max(values)}
    return {
        'runs': len(rows), 'final_price': {
            'p10': percentile([r['final'] for r in rows], .1),
            'median': statistics.median(r['final'] for r in rows),
            'p90': percentile([r['final'] for r in rows], .9)},
        'max_drawdown': summary('max_drawdown'),
        'extreme_divergence_time_pct': summary('extreme_pct'),
        'max_bear_streak_hours': summary('max_bear_streak_hours'),
        'near_floor_runs': sum(r['near_floor'] > 0 for r in rows),
        'recovered_pct': 100 * sum(r['recovered_at_hours'] is not None for r in rows) / len(rows),
    }


def paired_order_experiment(symbol, days, seed, amount, side):
    """Common random numbers: compare exactly the same shocks and random draws."""
    cfg = COINS[symbol]
    prices = [cfg['initial'], cfg['initial']]
    states = [State(fundamental=cfg['initial'], anchor=cfg['initial']) for _ in range(2)]
    histories = [[cfg['initial']], [cfg['initial']]]
    rngs = [random.Random(seed), random.Random(seed)]
    ticks = int(days * 86400 / TICK_SECONDS)
    for _ in range(ticks):
        for i in range(2):
            rng = rngs[i]
            states[i].sentiment = clamp(states[i].sentiment * .87 + rng.uniform(-.15, .15), -1., 1.)
            # Identical orders each tick are an intentionally adversarial upper-bound
            # experiment, NOT a feasible account-level trading strategy.
            buy = amount if i == 1 and side == 'buy' else 0.
            sell = amount if i == 1 and side == 'sell' else 0.
            prices[i], states[i] = engine_step(symbol, prices[i], states[i], histories[i],
                                               buy=buy, sell=sell, rng=rng)
            histories[i].append(prices[i]); histories[i] = histories[i][-5:]
    return {'control': prices[0], 'orders': prices[1],
            'log_price_effect': math.log(prices[1] / prices[0]),
            'gross_order_volume': ticks * amount}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=int, default=40)
    parser.add_argument('--days', type=int, nargs='+', default=[30, 90, 365])
    parser.add_argument('--output', type=Path, default=Path('market21_calibration.json'))
    args = parser.parse_args()
    if args.runs < 2 or any(day < 1 for day in args.days):
        parser.error('--runs must be >= 2 and days must be positive')
    report = {'engine': 'experimental 2.1', 'tick_seconds': TICK_SECONDS,
              'seed_policy': 'consecutive seeds starting at zero',
              'caveat': 'Prototype only; no production-engine equivalence or deployment claim',
              'parameters': COINS, 'scenarios': {}, 'paired_orders': {}}
    for symbol, name, price, fundamental, regime in SCENARIOS:
        for days in args.days:
            rows = [simulate(symbol, days, seed, price, fundamental, regime)
                    for seed in range(args.runs)]
            key = f'{symbol}:{name}:{days}d'
            report['scenarios'][key] = summarize(rows)
            print(key, json.dumps(report['scenarios'][key], ensure_ascii=False))
    for symbol in COINS:
        for side in ('buy', 'sell'):
            key = f'{symbol}:{side}:500:7d'
            rows = [paired_order_experiment(symbol, 7, seed, 500., side)
                    for seed in range(args.runs)]
            effects = [r['log_price_effect'] for r in rows]
            report['paired_orders'][key] = {
                'median_log_effect': statistics.median(effects),
                'p10_log_effect': percentile(effects, .1),
                'p90_log_effect': percentile(effects, .9),
                'gross_volume_per_run': rows[0]['gross_order_volume'],
                'note': 'Unlimited artificial orders; no account balances or fees simulated',
            }
            print(key, json.dumps(report['paired_orders'][key], ensure_ascii=False))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {args.output}')


if __name__ == '__main__':
    main()
