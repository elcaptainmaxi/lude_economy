"""Exercise shared global sentiment and correlated shocks in the isolated 2.1 engine.

Run: python -m scripts.stress_correlated_shocks_21
The same shock is passed to all three coins at a given tick; none uses the DB.
"""
import random
import statistics
from scripts.simulate_market_engine_21 import COINS, State, TICK_SECONDS, clamp, engine_step


def run(days=30, seed=0, shocks=True):
    global_rng = random.Random(seed + 100_000)
    coin_rng = {symbol: random.Random(seed * 37 + i + 123) for i, symbol in enumerate(COINS)}
    prices = {symbol: cfg['initial'] for symbol, cfg in COINS.items()}
    states = {symbol: State(fundamental=price, anchor=price) for symbol, price in prices.items()}
    histories = {symbol: [price] for symbol, price in prices.items()}
    peaks = prices.copy()
    max_drawdowns = {symbol: 0.0 for symbol in COINS}
    shock_ticks = 0
    sentiment = 0.0
    shock_effects = []
    for _ in range(int(days * 86400 / TICK_SECONDS)):
        sentiment = clamp(sentiment * .87 + global_rng.uniform(-.15, .15), -1, 1)
        shock = 0.0
        if shocks and global_rng.random() < .003:
            shock = global_rng.choice((-1, 1)) * global_rng.uniform(.025, .075)
            shock_ticks += 1
        for symbol in COINS:
            old = prices[symbol]
            states[symbol].sentiment = sentiment
            nxt, state = engine_step(symbol, old, states[symbol], histories[symbol],
                                     shock=shock, rng=coin_rng[symbol])
            prices[symbol], states[symbol] = nxt, state
            histories[symbol].append(nxt)
            histories[symbol] = histories[symbol][-5:]
            peaks[symbol] = max(peaks[symbol], nxt)
            max_drawdowns[symbol] = max(max_drawdowns[symbol], 1 - nxt / peaks[symbol])
            assert nxt >= .01 and state.fundamental >= .01
        if shock:
            shock_effects.append(shock)
    assert len(shock_effects) == shock_ticks
    return {'prices': prices, 'max_drawdowns': max_drawdowns, 'shock_ticks': shock_ticks}


def main():
    days, runs = 30, 12
    without = [run(days, seed, shocks=False) for seed in range(runs)]
    with_shocks = [run(days, seed, shocks=True) for seed in range(runs)]
    print(f'Shared-shock stress: {days} days, {runs} seeds, all 3 currencies')
    print('Shock events per run:', [row['shock_ticks'] for row in with_shocks])
    for symbol in COINS:
        base = statistics.median(row['max_drawdowns'][symbol] for row in without)
        shocked = statistics.median(row['max_drawdowns'][symbol] for row in with_shocks)
        print(f'{symbol}: median max drawdown without={base:.1%} with={shocked:.1%}')


if __name__ == '__main__':
    main()
