"""Offline Market Engine 2.1 simulator using the identical production engine function.

No Discord, database, or production state is accessed.
"""
import random
import statistics
from dataclasses import replace

from lude.market_engine_21 import (
    COINS, REGIMES, TICK_SECONDS, State, clamp, engine_step,
    extreme_reversion_bias, order_impact, update_anchor_and_fundamental,
)


def simulate(symbol, days, seed, start_price=None, fundamental=None, regime='sideways'):
    cfg = COINS[symbol]
    price = float(start_price if start_price is not None else cfg['initial'])
    f = float(fundamental if fundamental is not None else cfg['initial'])
    state = State(fundamental=f, anchor=price, regime=regime)
    rng = random.Random(seed)
    history = [price]
    minimum = maximum = price
    max_abs_div = 0.
    near_floor = extreme_ticks = 0
    regime_counts = {r: 0 for r in REGIMES}
    ticks = int(days * 86400 / TICK_SECONDS)
    peak = price
    max_drawdown = 0.
    anchor_confirmed = 0
    max_bear_streak = bear_streak = 0
    recovered_at = None
    for tick in range(ticks):
        state.sentiment = clamp(state.sentiment * .87 + rng.uniform(-.15, .15), -1, 1)
        price, state = engine_step(symbol, price, state, history, rng=rng)
        history.append(price)
        history = history[-5:]
        minimum, maximum = min(minimum, price), max(maximum, price)
        peak = max(peak, price)
        max_drawdown = max(max_drawdown, 1 - price / peak)
        div = abs(price / max(.01, state.fundamental) - 1.)
        max_abs_div = max(max_abs_div, div)
        extreme_ticks += div >= .80
        near_floor += price <= .02
        regime_counts[state.regime] += 1
        anchor_confirmed += state.anchor_ticks >= int(cfg['confirm_hours'] * 3600 / TICK_SECONDS)
        bear_streak = bear_streak + 1 if state.regime == 'bear' else 0
        max_bear_streak = max(max_bear_streak, bear_streak)
        if recovered_at is None and start_price is not None and (
            (start_price < f and price >= .8 * f) or
            (start_price > f and price <= 1.2 * f)
        ):
            recovered_at = tick + 1
    return dict(
        final=price, fundamental=state.fundamental, min=minimum, max=maximum,
        max_div=max_abs_div, extreme_pct=100 * extreme_ticks / ticks,
        near_floor=near_floor,
        regimes={k: 100 * v / ticks for k, v in regime_counts.items()},
        max_drawdown=max_drawdown,
        anchor_confirmed_pct=100 * anchor_confirmed / ticks,
        max_bear_streak_hours=max_bear_streak * TICK_SECONDS / 3600,
        recovered_at_hours=(recovered_at * TICK_SECONDS / 3600
                            if recovered_at is not None else None),
    )


def batch(symbol, days, runs, scenario='normal'):
    rows = []
    for seed in range(runs):
        if scenario == 'flx_extreme':
            rows.append(simulate('FLX', days, seed, .61, 38., 'bear'))
        elif scenario == 'nva_bubble':
            rows.append(simulate('NVA', days, seed, 625., 250., 'bull'))
        else:
            rows.append(simulate(symbol, days, seed))
    finals = sorted(row['final'] for row in rows)
    return dict(
        symbol=symbol, scenario=scenario, days=days, runs=runs,
        median_final=statistics.median(finals),
        p10_final=finals[max(0, int(runs * .1) - 1)],
        p90_final=finals[min(runs - 1, int(runs * .9))],
        near_floor_runs=sum(row['near_floor'] > 0 for row in rows),
        median_extreme_pct=statistics.median(row['extreme_pct'] for row in rows),
        median_drawdown=statistics.median(row['max_drawdown'] for row in rows),
        median_anchor_confirmed_pct=statistics.median(row['anchor_confirmed_pct'] for row in rows),
        recovery_pct=100 * sum(row['recovered_at_hours'] is not None for row in rows) / runs,
        median_max_bear_hours=statistics.median(row['max_bear_streak_hours'] for row in rows),
    )


def anchor_hold_test(symbol, zone_multiplier=.60):
    cfg = COINS[symbol]
    zone = cfg['initial'] * zone_multiplier
    state = State(fundamental=cfg['initial'], anchor=zone)
    required = int(cfg['confirm_hours'] * 3600 / TICK_SECONDS)
    first_move = None
    checkpoints = {}
    for tick in range(required * 2):
        old = state.fundamental
        anchor, ticks, fundamental, reference = update_anchor_and_fundamental(symbol, zone, state)
        state = replace(state, anchor=anchor, anchor_ticks=ticks,
                        anchor_reference=reference, fundamental=fundamental)
        if first_move is None and fundamental != old:
            first_move = tick + 1
        if tick + 1 in (required - 1, required, required + 1, required * 2):
            checkpoints[tick + 1] = fundamental
    return dict(symbol=symbol, required=required, first_move=first_move,
                start=cfg['initial'], zone=zone, final=state.fundamental,
                checkpoints=checkpoints)


def transient_crash_test(symbol, crash_hours=2, multiplier=.25):
    cfg = COINS[symbol]
    state = State(fundamental=cfg['initial'], anchor=cfg['initial'])
    for _ in range(int(crash_hours * 3600 / TICK_SECONDS)):
        anchor, ticks, fundamental, reference = update_anchor_and_fundamental(
            symbol, cfg['initial'] * multiplier, state)
        state = replace(state, anchor=anchor, anchor_ticks=ticks,
                        anchor_reference=reference, fundamental=fundamental)
    return state.fundamental / cfg['initial'] - 1, state.anchor_ticks, state.anchor


def manipulation_tick_test(symbol, amount, seed=731):
    cfg = COINS[symbol]
    base = cfg['initial']
    state = State(fundamental=base, anchor=base)
    history = [base] * 8
    p0, _ = engine_step(symbol, base, state, history, rng=random.Random(seed))
    pb, _ = engine_step(symbol, base, state, history, buy=amount, rng=random.Random(seed))
    ps, _ = engine_step(symbol, base, state, history, sell=amount, rng=random.Random(seed))
    return (pb / p0 - 1) * 100, (ps / p0 - 1) * 100
