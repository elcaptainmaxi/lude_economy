"""Week-long order-pressure stress tests for prototype, never uses production DB."""
import random
import statistics
from scripts.simulate_market_engine_21 import COINS, State, TICK_SECONDS, clamp, engine_step


def week(symbol, side='none', amount=500, seed=0):
    cfg = COINS[symbol]
    price = cfg['initial']
    state = State(fundamental=price, anchor=price)
    history = [price]
    rng = random.Random(seed)
    maximum_pressure = 0.
    ticks = 7 * 86400 // TICK_SECONDS
    for _ in range(ticks):
        state.sentiment = clamp(state.sentiment * .87 + rng.uniform(-.15, .15), -1, 1)
        price, state = engine_step(symbol, price, state, history,
                                   buy=amount if side == 'buy' else 0.,
                                   sell=amount if side == 'sell' else 0., rng=rng)
        history.append(price)
        history = history[-5:]
        maximum_pressure = max(maximum_pressure, abs(state.pressure))
        assert -1 <= state.pressure <= 1
        assert price >= .01
    return price, maximum_pressure


def main():
    for symbol in COINS:
        for side in ('none', 'buy', 'sell'):
            results = [week(symbol, side, 500, seed) for seed in range(12)]
            print(f'{symbol} {side:<4} seven-day prices: '
                  f'median={statistics.median(v[0] for v in results):.4f} '
                  f'min={min(v[0] for v in results):.4f} '
                  f'max={max(v[0] for v in results):.4f} '
                  f'max_pressure={max(v[1] for v in results):.4f}', flush=True)


if __name__ == '__main__':
    main()
