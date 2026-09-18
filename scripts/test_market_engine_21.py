"""Deterministic invariants for the standalone Market Engine 2.1 prototype."""
import math
import random
from dataclasses import replace
from scripts.simulate_market_engine_21 import (
    COINS, State, TICK_SECONDS, anchor_hold_test, engine_step,
    extreme_reversion_bias, manipulation_tick_test, transient_crash_test,
    update_anchor_and_fundamental,
)


def run_tests():
    count = 0
    for symbol, cfg in COINS.items():
        required = cfg['confirm_hours'] * 3600 // TICK_SECONDS
        stable = anchor_hold_test(symbol)
        assert stable['required'] == required
        assert stable['first_move'] == required
        assert stable['checkpoints'][required - 1] == cfg['initial']
        assert stable['zone'] < stable['final'] < stable['start']
        assert transient_crash_test(symbol)[0] == 0.0
        count += 5

        # Old anchor -> new zone: count starts after candidate zone discovery.
        zone = cfg['initial'] * .60
        state = State(fundamental=cfg['initial'], anchor=cfg['initial'])
        first_move = None
        for tick in range(2 * required):
            anchor, ticks, fundamental, reference = update_anchor_and_fundamental(symbol, zone, state)
            state = replace(state, anchor=anchor, anchor_ticks=ticks,
                            fundamental=fundamental, anchor_reference=reference)
            if fundamental != cfg['initial'] and first_move is None:
                first_move = tick + 1
        assert first_move is not None and required <= first_move <= 2 * required
        count += 1

        for amount in (500, 5_000, 50_000):
            buying, selling = manipulation_tick_test(symbol, amount)
            assert 0 < buying <= cfg['player_max'] * 110
            assert -cfg['player_max'] * 110 <= selling < 0
            count += 2
        s = State(fundamental=cfg['initial'], anchor=cfg['initial'])
        normal, _ = engine_step(symbol, cfg['initial'], s, [cfg['initial']] * 8,
                                rng=random.Random(731))
        zero, _ = engine_step(symbol, cfg['initial'], s, [cfg['initial']] * 8,
                              buy=0, sell=0, rng=random.Random(731))
        assert normal == zero
        count += 1
    for f in (.2, .5, 2, 4, 8):
        a = extreme_reversion_bias(100 * f, 100)
        b = extreme_reversion_bias(100 / f, 100)
        assert math.isclose(a, -b, abs_tol=1e-12)
        count += 1
    print(f'PASS: {count} Market Engine 2.1 invariant checks')


if __name__ == '__main__':
    run_tests()
