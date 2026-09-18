"""Run reproducible 2.1 prototype stress scenarios without touching production.

    python -m scripts.run_market_engine_21 --days 30 90 365 --runs 8
    python -m scripts.run_market_engine_21 --days 30 --runs 30 --output results.json
"""
import argparse
import json
from pathlib import Path

from scripts.simulate_market_engine_21 import COINS, batch, manipulation_tick_test
from scripts.test_market_engine_21 import run_tests

SCENARIOS = (
    ('IC', 'normal'), ('NVA', 'normal'), ('FLX', 'normal'),
    ('FLX', 'flx_extreme'), ('NVA', 'nva_bubble'),
)


def main():
    parser = argparse.ArgumentParser(description='Market Engine 2.1 isolated simulation')
    parser.add_argument('--days', nargs='+', type=int, default=[30],
                        help='Simulation horizons in days, e.g. 30 90 365')
    parser.add_argument('--runs', type=int, default=8,
                        help='Deterministic seeds per scenario (default: 8)')
    parser.add_argument('--output', type=Path, default=None,
                        help='Optional JSON report file')
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 1000 or not args.days or any(d < 1 or d > 3650 for d in args.days):
        parser.error('Use 1–1000 runs and horizons from 1 to 3650 days')
    run_tests()
    results = []
    for days in args.days:
        for symbol, scenario in SCENARIOS:
            row = batch(symbol, days, args.runs, scenario)
            results.append(row)
            print(f'{days:>4}d {symbol:>3} {scenario:<12} '
                  f'median={row["median_final"]:.4f} '
                  f'p10={row["p10_final"]:.4f} p90={row["p90_final"]:.4f} '
                  f'floor={row["near_floor_runs"]}/{args.runs} '
                  f'peak-to-trough={row["median_drawdown"]:.1%} '
                  f'anchor-confirmed={row["median_anchor_confirmed_pct"]:.1f}%', flush=True)
    impacts = {
        symbol: {str(amount): manipulation_tick_test(symbol, amount)
                 for amount in (500, 5000, 50000)}
        for symbol in COINS
    }
    report = {'note': 'Experimental independent prototype, not production lude/crypto.py',
              'tick_seconds': 300, 'scenarios': results,
              'single_tick_player_impact_pct': impacts}
    if args.output:
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        print(f'Wrote: {args.output}')


if __name__ == '__main__':
    main()
