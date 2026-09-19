"""Calibrated Market Engine 2.1, shared by the bot and offline simulator.

Pure Python: no Discord, SQLite, wallet mutations, or background tasks.
The new persistent fields must be migrated before enabling it in the live tick loop.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, replace

TICK_SECONDS = 300
REGIMES = ('bull', 'bear', 'sideways', 'storm')
COINS = {
    'IC': dict(initial=1000., auto_min=.002, auto_max=.009, player_max=.02,
               momentum_strength=.12, momentum_cap=.012, liquidity=15000.,
               confirm_hours=48, anchor_tolerance=.15, personality=.75,
               regime_strength=.04, reversion_scale=1.35, adapt_rate=.0008, adapt_cap=.0012),
    'NVA': dict(initial=250., auto_min=.007, auto_max=.026, player_max=.04,
                momentum_strength=.22, momentum_cap=.032, liquidity=7500.,
                confirm_hours=24, anchor_tolerance=.22, personality=1.,
                regime_strength=.065, reversion_scale=1.20, adapt_rate=.0015, adapt_cap=.002),
    'FLX': dict(initial=50., auto_min=.016, auto_max=.055, player_max=.06,
                momentum_strength=.28, momentum_cap=.040, liquidity=3000.,
                confirm_hours=12, anchor_tolerance=.35, personality=1.35,
                regime_strength=.09, reversion_scale=1.18, adapt_rate=.0018, adapt_cap=.0025),
}


@dataclass
class State:
    fundamental: float
    anchor: float
    anchor_ticks: int = 0
    anchor_reference: float = 0.
    regime: str = 'sideways'
    regime_ticks: int = 0
    volatility: float = .35
    pressure: float = 0.
    flow_baseline: float = 0.
    sentiment: float = 0.


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def extreme_reversion_bias(price, fundamental):
    x = abs(math.log(max(.01, price) / max(.01, fundamental)))
    knots = ((0., 0.), (math.log(1.10), .025), (math.log(1.20), .065),
             (math.log(1.50), .16), (math.log(2.), .27), (math.log(4.), .42),
             (math.log(16.), .52))
    strength = knots[-1][1]
    for (x0, y0), (x1, y1) in zip(knots, knots[1:]):
        if x <= x1:
            strength = y0 + (y1 - y0) * (x - x0) / (x1 - x0)
            break
    return -math.copysign(strength, math.log(max(.01, price) / max(.01, fundamental)))


def update_anchor_and_fundamental(symbol, price, state):
    cfg = COINS[symbol]
    candidate = math.exp(.98 * math.log(max(.01, state.anchor)) +
                         .02 * math.log(max(.01, price)))
    reference = state.anchor_reference if state.anchor_reference > 0 else state.anchor
    near = abs(math.log(max(.01, candidate) / max(.01, reference))) <= math.log1p(cfg['anchor_tolerance'])
    ticks = state.anchor_ticks + 1 if near else 1
    anchor_reference = reference if near else candidate
    fundamental = max(.01, state.fundamental)
    required = int(cfg['confirm_hours'] * 3600 / TICK_SECONDS)
    if ticks >= required:
        structural = clamp(math.log(max(.01, candidate) / fundamental) * cfg['adapt_rate'],
                           -cfg['adapt_cap'], cfg['adapt_cap'])
        fundamental = max(.01, fundamental * math.exp(structural))
    return candidate, ticks, fundamental, anchor_reference


def order_impact(cfg, state, buy=0., sell=0.):
    """Impact of flow innovation; repeating an identical order cannot pump forever."""
    buy, sell = max(0., buy), max(0., sell)
    volume = buy + sell
    flow = ((buy - sell) / volume * math.sqrt(volume) /
            (math.sqrt(volume) + math.sqrt(cfg['liquidity']))) if volume else 0.
    innovation = flow - state.flow_baseline
    baseline = clamp(.85 * state.flow_baseline + .15 * flow, -1., 1.)
    pressure = clamp(.55 * state.pressure + .7 * innovation, -1., 1.)
    move = clamp(cfg['player_max'] * (innovation + .20 * pressure),
                 -cfg['player_max'], cfg['player_max'])
    return move, pressure, baseline


def engine_step(symbol, price, state, history, buy=0., sell=0., rng=None, shock=0.):
    """Advance one tick. Returns (new_price, new_state) without mutating input state."""
    rng = rng or random.Random()
    cfg = COINS[symbol]
    price = max(.01, float(price))
    history = list(history[-5:]) or [price]
    returns = [math.log(b / a) for a, b in zip(history[:-1], history[1:]) if a > 0 and b > 0]
    momentum = statistics.fmean(returns[-4:]) if returns else 0.
    anchor, anchor_ticks, fundamental, anchor_reference = update_anchor_and_fundamental(symbol, price, state)
    divergence_bias = extreme_reversion_bias(price, fundamental) * cfg['reversion_scale']
    age = state.regime_ticks + 1
    transition = min(.36, .035 * cfg['personality'] + min(age, 100) * .0006)
    if state.regime == 'bear' and divergence_bias > .15:
        transition += min(.16, (divergence_bias - .15) * .9)
    elif state.regime == 'bull' and divergence_bias < -.15:
        transition += min(.16, (-divergence_bias - .15) * .9)
    transition = min(.50, transition)
    regime = state.regime
    if rng.random() < transition:
        direction = math.tanh(momentum / max(cfg['auto_max'], .0001))
        shared = clamp(state.sentiment, -1, 1)
        fundamental_signal = divergence_bias / .30
        bull = max(.10, 1 + direction + shared * .7 + max(0, fundamental_signal) * .9)
        bear = max(.10, 1 - direction - shared * .7 + max(0, -fundamental_signal) * .9)
        sideways = 1.25 if anchor_ticks > 4 else .9
        storm = .35 + .65 * state.volatility
        regime = rng.choices(REGIMES, weights=[bull, bear, sideways, storm], k=1)[0]
        if regime != state.regime:
            age = 0
    player_move, pressure, flow_baseline = order_impact(cfg, state, buy, sell)
    regime_strength = cfg['regime_strength']
    regime_bias = {'bull': regime_strength, 'bear': -regime_strength,
                   'sideways': 0., 'storm': 0.}[regime]
    momentum_bias = math.tanh(momentum / max(cfg['auto_max'], .0001)) * cfg['momentum_strength'] * .15
    shared_bias = clamp(state.sentiment * .12, -.12, .12)
    up_probability = clamp(.5 + regime_bias + divergence_bias + momentum_bias + shared_bias, .06, .94)
    volatility = clamp(state.volatility * .84 + abs(momentum) /
                       max(cfg['auto_max'], .0001) * .12 + abs(shock) * 1.8, 0, 1)
    sample = rng.random()
    if regime == 'storm' or volatility > .70:
        sample = max(sample, rng.random())
    elif regime == 'sideways' and volatility < .22:
        sample = min(sample, rng.random())
    magnitude = cfg['auto_min'] + (cfg['auto_max'] - cfg['auto_min']) * sample
    auto_move = magnitude if rng.random() < up_probability else -magnitude
    momentum_move = clamp(momentum * cfg['momentum_strength'] *
                          (.7 if regime == 'sideways' else 1),
                          -cfg['momentum_cap'], cfg['momentum_cap'])
    shock_move = clamp(shock, -cfg['auto_max'] * .6, cfg['auto_max'] * .6)
    total = clamp(auto_move + momentum_move + player_move + shock_move, -.85, 1.5)
    new_price = max(.01, round(price * math.exp(total), 4))
    return new_price, replace(state, fundamental=fundamental, anchor=anchor,
                              anchor_ticks=anchor_ticks, anchor_reference=anchor_reference,
                              regime=regime, regime_ticks=age, volatility=volatility,
                              pressure=pressure, flow_baseline=flow_baseline)
