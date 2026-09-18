"""Market Engine 2.1 prototype simulator.

Development-only. It does not connect to Discord or lude_economy.db.
Run: python -m scripts.simulate_market_engine_21
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, replace

TICK_SECONDS = 300
REGIMES = ("bull", "bear", "sideways", "storm")

COINS = {
    "IC": dict(initial=1000.0, auto_min=.01, auto_max=.04, player_max=.02,
               momentum_strength=.30, momentum_cap=.06, liquidity=15000.0,
               confirm_hours=48, anchor_tolerance=.06, personality=.75),
    "NVA": dict(initial=250.0, auto_min=.03, auto_max=.09, player_max=.04,
                momentum_strength=.40, momentum_cap=.08, liquidity=7500.0,
                confirm_hours=24, anchor_tolerance=.10, personality=1.0),
    "FLX": dict(initial=50.0, auto_min=.07, auto_max=.18, player_max=.06,
                momentum_strength=.55, momentum_cap=.10, liquidity=3000.0,
                confirm_hours=12, anchor_tolerance=.15, personality=1.35),
}


@dataclass
class State:
    fundamental: float
    anchor: float
    anchor_ticks: int = 0
    regime: str = "sideways"
    regime_ticks: int = 0
    volatility: float = .35
    pressure: float = 0.0
    sentiment: float = 0.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def signed_divergence(price, fundamental):
    # log distance is symmetric for bubbles/crashes.
    return math.log(max(.01, price) / max(.01, fundamental))


def extreme_reversion_bias(price, fundamental):
    """Symmetric nonlinear valuation pressure in probability points."""
    x = abs(math.log(max(.01, price) / max(.01, fundamental)))
    a, b, c, d = map(math.log, (1.2, 1.5, 2.0, 4.0))
    if x <= a:
        strength = 0.0
    elif x <= b:
        strength = .10 * (x - a) / (b - a)
    elif x <= c:
        strength = .10 + .14 * (x - b) / (c - b)
    elif x <= d:
        strength = .24 + .16 * (x - c) / (d - c)
    else:
        strength = min(.52, .40 + .12 * min(1.0, (x - d) / math.log(4.0)))
    return -math.copysign(strength, signed_divergence(price, fundamental))


def update_anchor_and_fundamental(symbol, price, state):
    cfg = COINS[symbol]
    tolerance = cfg["anchor_tolerance"]

    # EMA candidate: fast enough to discover a new zone, slow enough to ignore one tick.
    candidate = state.anchor * .92 + price * .08
    near_candidate = abs(price / max(.01, candidate) - 1.0) <= tolerance
    anchor_ticks = state.anchor_ticks + 1 if near_candidate else 0
    anchor = candidate if near_candidate or state.anchor_ticks == 0 else state.anchor

    # Unconfirmed price action does not rewrite structural value.
    fundamental = max(.01, state.fundamental)

    required = int(cfg["confirm_hours"] * 3600 / TICK_SECONDS)
    if anchor_ticks >= required:
        # Confirmed new market reality: convergence becomes meaningful but remains bounded.
        structural = clamp(math.log(max(.01, anchor) / fundamental) * .0035, -.006, .006)
        fundamental = max(.01, fundamental * math.exp(structural))

    return anchor, anchor_ticks, fundamental


def engine_step(symbol, price, state, history, buy=0.0, sell=0.0, rng=None):
    rng = rng or random.Random()
    cfg = COINS[symbol]
    price = max(.01, float(price))
    history = list(history[-24:]) or [price]
    returns = [math.log(b / a) for a, b in zip(history[:-1], history[1:]) if a > 0 and b > 0]
    momentum = statistics.fmean(returns[-4:]) if returns else 0.0

    anchor, anchor_ticks, fundamental = update_anchor_and_fundamental(symbol, price, state)
    divergence_bias = extreme_reversion_bias(price, fundamental)

    age = state.regime_ticks + 1
    transition = min(.36, .035 * cfg["personality"] + min(age, 100) * .0006)

    # Extreme divergence and momentum disagreement make stale regimes easier to leave.
    if state.regime == "bear" and divergence_bias > .15:
        transition += min(.16, (divergence_bias - .15) * .9)
    elif state.regime == "bull" and divergence_bias < -.15:
        transition += min(.16, (-divergence_bias - .15) * .9)
    transition = min(.50, transition)

    regime = state.regime
    if rng.random() < transition:
        direction = math.tanh(momentum / max(cfg["auto_max"], .0001))
        shared = clamp(state.sentiment, -1, 1)
        fundamental_signal = divergence_bias / .30
        bull = max(.10, 1 + direction + shared * .7 + max(0, fundamental_signal) * .9)
        bear = max(.10, 1 - direction - shared * .7 + max(0, -fundamental_signal) * .9)
        sideways = 1.25 if anchor_ticks > 4 else .9
        storm = .35 + .65 * state.volatility
        regime = rng.choices(REGIMES, weights=[bull, bear, sideways, storm], k=1)[0]
        age = 0

    volume = max(0., buy) + max(0., sell)
    signed = (buy - sell) / volume if volume else 0.
    liquidity = cfg["liquidity"]
    flow = signed * math.sqrt(volume) / (math.sqrt(volume) + math.sqrt(liquidity)) if volume else 0.
    pressure = clamp(state.pressure * .55 + flow * .7, -1, 1)
    player_move = clamp(cfg["player_max"] * (flow + .20 * pressure), -cfg["player_max"], cfg["player_max"])

    regime_bias = {"bull": .17, "bear": -.17, "sideways": 0., "storm": 0.}[regime]
    momentum_bias = math.tanh(momentum / max(cfg["auto_max"], .0001)) * cfg["momentum_strength"] * .15
    shared_bias = clamp(state.sentiment * .12, -.12, .12)

    # Fundamental is allowed to challenge a regime instead of being almost disabled by it.
    up_probability = clamp(.5 + regime_bias + divergence_bias + momentum_bias + shared_bias, .06, .94)

    volatility = clamp(state.volatility * .84 + abs(momentum) / max(cfg["auto_max"], .0001) * .12, 0, 1)
    sample = rng.random()
    if regime == "storm" or volatility > .70:
        sample = max(sample, rng.random())
    elif regime == "sideways" and volatility < .22:
        sample = min(sample, rng.random())
    magnitude = cfg["auto_min"] + (cfg["auto_max"] - cfg["auto_min"]) * sample
    auto_move = magnitude if rng.random() < up_probability else -magnitude
    momentum_move = clamp(momentum * cfg["momentum_strength"] * (.7 if regime == "sideways" else 1),
                          -cfg["momentum_cap"], cfg["momentum_cap"])
    total = clamp(auto_move + momentum_move + player_move, -.85, 1.5)
    # Apply movement in log-price space. Symmetric +/- shocks no longer create\n    # an accidental long-run downward bias through multiplicative volatility drag.\n    new_price = max(.01, round(price * math.exp(total), 4))

    return new_price, replace(state, fundamental=fundamental, anchor=anchor,
                              anchor_ticks=anchor_ticks, regime=regime,
                              regime_ticks=age, volatility=volatility, pressure=pressure)


def simulate(symbol, days, seed, start_price=None, fundamental=None, regime="sideways"):
    cfg = COINS[symbol]
    price = float(start_price if start_price is not None else cfg["initial"])
    f = float(fundamental if fundamental is not None else cfg["initial"])
    state = State(fundamental=f, anchor=price, regime=regime)
    rng = random.Random(seed)
    history = [price]
    minimum = maximum = price
    max_abs_div = 0.
    near_floor = 0
    extreme_ticks = 0
    regime_counts = {r: 0 for r in REGIMES}
    ticks = int(days * 86400 / TICK_SECONDS)

    for _ in range(ticks):
        state.sentiment = clamp(state.sentiment * .87 + rng.uniform(-.15, .15), -1, 1)
        price, state = engine_step(symbol, price, state, history, rng=rng)
        history.append(price)
        history = history[-25:]
        minimum, maximum = min(minimum, price), max(maximum, price)
        div = abs(price / max(.01, state.fundamental) - 1)
        max_abs_div = max(max_abs_div, div)
        extreme_ticks += div >= .80
        near_floor += price <= .02
        regime_counts[state.regime] += 1

    return {
        "final": price, "fundamental": state.fundamental, "min": minimum, "max": maximum,
        "max_div": max_abs_div, "extreme_pct": extreme_ticks / ticks * 100,
        "near_floor": near_floor, "regimes": {k: v / ticks * 100 for k, v in regime_counts.items()},
    }


def batch(symbol, days, runs, scenario="normal"):
    rows = []
    for seed in range(runs):
        if scenario == "flx_extreme":
            rows.append(simulate("FLX", days, seed, .61, 38., "bear"))
        elif scenario == "nva_bubble":
            rows.append(simulate("NVA", days, seed, 625., 250., "bull"))
        else:
            rows.append(simulate(symbol, days, seed))
    finals = [r["final"] for r in rows]
    return {
        "symbol": symbol, "scenario": scenario, "days": days, "runs": runs,
        "median_final": statistics.median(finals),
        "p10_final": sorted(finals)[max(0, int(runs * .10) - 1)],
        "p90_final": sorted(finals)[min(runs - 1, int(runs * .90))],
        "near_floor_runs": sum(r["near_floor"] > 0 for r in rows),
        "median_extreme_pct": statistics.median(r["extreme_pct"] for r in rows),
        "median_max_div": statistics.median(r["max_div"] for r in rows),
    }


def main():
    tests = [
        batch("IC", 30, 200),
        batch("NVA", 30, 200),
        batch("FLX", 30, 200),
        batch("FLX", 30, 200, "flx_extreme"),
        batch("NVA", 30, 200, "nva_bubble"),
    ]
    print("Market Engine 2.1 prototype — 5 minute ticks")
    for row in tests:
        print(
            f"{row['symbol']:>3} {row['scenario']:<12} | median={row['median_final']:.4f} "
            f"p10={row['p10_final']:.4f} p90={row['p90_final']:.4f} "
            f"floor_runs={row['near_floor_runs']}/{row['runs']} "
            f"extreme={row['median_extreme_pct']:.2f}% max_div_med={row['median_max_div']:.2f}"
        )


if __name__ == "__main__":
    main()
