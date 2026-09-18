"""Isolated prototype of Market Engine 2.1. Never accesses Discord or a database."""
from __future__ import annotations
import math
import random
import statistics
from dataclasses import dataclass, replace

TICK_SECONDS = 300
REGIMES = ('bull','bear','sideways','storm')
COINS = {
 'IC': dict(initial=1000.,auto_min=.002,auto_max=.009,player_max=.02,momentum_strength=.12,momentum_cap=.012,liquidity=15000.,confirm_hours=48,anchor_tolerance=.15,personality=.75,regime_strength=.04,reversion_scale=1.35,adapt_rate=.0008,adapt_cap=.0012),
 'NVA': dict(initial=250.,auto_min=.007,auto_max=.026,player_max=.04,momentum_strength=.22,momentum_cap=.032,liquidity=7500.,confirm_hours=24,anchor_tolerance=.22,personality=1.,regime_strength=.065,reversion_scale=1.20,adapt_rate=.0015,adapt_cap=.002),
 'FLX': dict(initial=50.,auto_min=.016,auto_max=.055,player_max=.06,momentum_strength=.28,momentum_cap=.040,liquidity=3000.,confirm_hours=12,anchor_tolerance=.35,personality=1.35,regime_strength=.09,reversion_scale=1.18,adapt_rate=.0018,adapt_cap=.0025),
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

def clamp(v,lo,hi): return max(lo,min(hi,v))

def extreme_reversion_bias(price, fundamental):
 x=abs(math.log(max(.01,price)/max(.01,fundamental)))
 # Probability-based valuation brake: weak for noise, meaningful before a death spiral.
 knots=((0.,0.),(math.log(1.10),.025),(math.log(1.20),.065),
        (math.log(1.50),.16),(math.log(2.),.27),(math.log(4.),.42),
        (math.log(16.),.52))
 strength=knots[-1][1]
 for (x0,y0),(x1,y1) in zip(knots,knots[1:]):
  if x<=x1:
   strength=y0+(y1-y0)*(x-x0)/(x1-x0)
   break
 return -math.copysign(strength,math.log(max(.01,price)/max(.01,fundamental)))

def update_anchor_and_fundamental(symbol,price,state):
 cfg=COINS[symbol]
 # Smooth noisy ticks into a candidate zone; test stability of the ZONE,
 # not every individual price, which would make 12h/24h/48h impossible.
 candidate=math.exp(.98*math.log(max(.01,state.anchor))+.02*math.log(max(.01,price)))
 reference=state.anchor_reference if state.anchor_reference>0 else state.anchor
 near=abs(math.log(max(.01,candidate)/max(.01,reference)))<=math.log1p(cfg['anchor_tolerance'])
 ticks=state.anchor_ticks+1 if near else 1
 anchor=candidate
 anchor_reference=reference if near else candidate
 fundamental=max(.01,state.fundamental)
 required=int(cfg['confirm_hours']*3600/TICK_SECONDS)
 if ticks>=required:
  structural=clamp(math.log(max(.01,anchor)/fundamental)*cfg.get('adapt_rate',.0035),-cfg.get('adapt_cap',.006),cfg.get('adapt_cap',.006))
  fundamental=max(.01,fundamental*math.exp(structural))
 return anchor,ticks,fundamental,anchor_reference

def order_impact(cfg, state, buy=0., sell=0.):
 """One-tick liquidity response. Persistent identical flow has bounded total effect."""
 buy,sell=max(0.,buy),max(0.,sell)
 volume=buy+sell
 flow=((buy-sell)/volume*math.sqrt(volume)/(math.sqrt(volume)+math.sqrt(cfg['liquidity']))) if volume else 0.
 innovation=flow-state.flow_baseline
 baseline=clamp(.85*state.flow_baseline+.15*flow,-1.,1.)
 pressure=clamp(.55*state.pressure+.7*innovation,-1.,1.)
 move=clamp(cfg['player_max']*(innovation+.20*pressure),-cfg['player_max'],cfg['player_max'])
 return move,pressure,baseline

def engine_step(symbol,price,state,history,buy=0.,sell=0.,rng=None,shock=0.):
 rng=rng or random.Random()
 cfg=COINS[symbol]
 price=max(.01,float(price))
 history=list(history[-5:]) or [price]
 returns=[math.log(b/a) for a,b in zip(history[:-1],history[1:]) if a>0 and b>0]
 momentum=statistics.fmean(returns[-4:]) if returns else 0.
 anchor,anchor_ticks,fundamental,anchor_reference=update_anchor_and_fundamental(symbol,price,state)
 divergence_bias=extreme_reversion_bias(price,fundamental)*cfg.get('reversion_scale',1.)
 age=state.regime_ticks+1
 transition=min(.36,.035*cfg['personality']+min(age,100)*.0006)
 if state.regime=='bear' and divergence_bias>.15: transition+=min(.16,(divergence_bias-.15)*.9)
 elif state.regime=='bull' and divergence_bias<-.15: transition+=min(.16,(-divergence_bias-.15)*.9)
 transition=min(.50,transition)
 regime=state.regime
 if rng.random()<transition:
  direction=math.tanh(momentum/max(cfg['auto_max'],.0001))
  shared=clamp(state.sentiment,-1,1)
  fundamental_signal=divergence_bias/.30
  bull=max(.10,1+direction+shared*.7+max(0,fundamental_signal)*.9)
  bear=max(.10,1-direction-shared*.7+max(0,-fundamental_signal)*.9)
  sideways=1.25 if anchor_ticks>4 else .9
  storm=.35+.65*state.volatility
  regime=rng.choices(REGIMES,weights=[bull,bear,sideways,storm],k=1)[0]
  if regime!=state.regime: age=0
 player_move,pressure,flow_baseline=order_impact(cfg,state,buy,sell)
 regime_strength=cfg.get('regime_strength',{'IC':.07,'NVA':.105,'FLX':.12}[symbol])
 regime_bias={'bull':regime_strength,'bear':-regime_strength,'sideways':0.,'storm':0.}[regime]
 momentum_bias=math.tanh(momentum/max(cfg['auto_max'],.0001))*cfg['momentum_strength']*cfg.get('momentum_probability',.15)
 shared_bias=clamp(state.sentiment*.12,-.12,.12)
 up_probability=clamp(.5+regime_bias+divergence_bias+momentum_bias+shared_bias,.06,.94)
 volatility=clamp(state.volatility*.84+abs(momentum)/max(cfg['auto_max'],.0001)*.12+abs(shock)*1.8,0,1)
 sample=rng.random()
 if regime=='storm' or volatility>.70: sample=max(sample,rng.random())
 elif regime=='sideways' and volatility<.22: sample=min(sample,rng.random())
 magnitude=cfg['auto_min']+(cfg['auto_max']-cfg['auto_min'])*sample
 auto_move=magnitude if rng.random()<up_probability else -magnitude
 momentum_move=clamp(momentum*cfg['momentum_strength']*(.7 if regime=='sideways' else 1),-cfg['momentum_cap'],cfg['momentum_cap'])
 shock_move=clamp(shock,-cfg['auto_max']*.6,cfg['auto_max']*.6)
 total=clamp(auto_move+momentum_move+player_move+shock_move,-.85,1.5)
 new_price=max(.01,round(price*math.exp(total),4))
 return new_price,replace(state,fundamental=fundamental,anchor=anchor,anchor_ticks=anchor_ticks,anchor_reference=anchor_reference,regime=regime,regime_ticks=age,volatility=volatility,pressure=pressure,flow_baseline=flow_baseline)

def simulate(symbol,days,seed,start_price=None,fundamental=None,regime='sideways'):
 cfg=COINS[symbol]
 price=float(start_price if start_price is not None else cfg['initial'])
 f=float(fundamental if fundamental is not None else cfg['initial'])
 state=State(fundamental=f,anchor=price,regime=regime)
 rng=random.Random(seed)
 history=[price]
 minimum=maximum=price
 max_abs_div=0.
 near_floor=extreme_ticks=0
 regime_counts={r:0 for r in REGIMES}
 ticks=int(days*86400/TICK_SECONDS)
 peak=price
 max_drawdown=0.
 anchor_confirmed=0
 max_bear_streak=bear_streak=0
 recovered_at=None
 for tick in range(ticks):
  state.sentiment=clamp(state.sentiment*.87+rng.uniform(-.15,.15),-1,1)
  price,state=engine_step(symbol,price,state,history,rng=rng)
  history.append(price);history=history[-5:]
  minimum,maximum=min(minimum,price),max(maximum,price)
  peak=max(peak,price);max_drawdown=max(max_drawdown,1-price/peak)
  div=abs(price/max(.01,state.fundamental)-1.)
  max_abs_div=max(max_abs_div,div)
  extreme_ticks+=div>=.80
  near_floor+=price<=.02
  regime_counts[state.regime]+=1
  anchor_confirmed+=state.anchor_ticks>=int(cfg['confirm_hours']*3600/TICK_SECONDS)
  bear_streak=bear_streak+1 if state.regime=='bear' else 0
  max_bear_streak=max(max_bear_streak,bear_streak)
  if recovered_at is None and start_price is not None and ((start_price<f and price>=.8*f) or (start_price>f and price<=1.2*f)): recovered_at=tick+1
 return dict(final=price,fundamental=state.fundamental,min=minimum,max=maximum,max_div=max_abs_div,extreme_pct=100*extreme_ticks/ticks,near_floor=near_floor,regimes={k:100*v/ticks for k,v in regime_counts.items()},max_drawdown=max_drawdown,anchor_confirmed_pct=100*anchor_confirmed/ticks,max_bear_streak_hours=max_bear_streak*TICK_SECONDS/3600,recovered_at_hours=recovered_at*TICK_SECONDS/3600 if recovered_at is not None else None)

def batch(symbol,days,runs,scenario='normal'):
 rows=[]
 for seed in range(runs):
  if scenario=='flx_extreme': rows.append(simulate('FLX',days,seed,.61,38.,'bear'))
  elif scenario=='nva_bubble': rows.append(simulate('NVA',days,seed,625.,250.,'bull'))
  else: rows.append(simulate(symbol,days,seed))
 finals=sorted(r['final'] for r in rows)
 return dict(symbol=symbol,scenario=scenario,days=days,runs=runs,median_final=statistics.median(finals),p10_final=finals[max(0,int(runs*.1)-1)],p90_final=finals[min(runs-1,int(runs*.9))],near_floor_runs=sum(r['near_floor']>0 for r in rows),median_extreme_pct=statistics.median(r['extreme_pct'] for r in rows),median_drawdown=statistics.median(r['max_drawdown'] for r in rows),median_anchor_confirmed_pct=statistics.median(r['anchor_confirmed_pct'] for r in rows),recovery_pct=100*sum(r['recovered_at_hours'] is not None for r in rows)/runs,median_max_bear_hours=statistics.median(r['max_bear_streak_hours'] for r in rows))

def anchor_hold_test(symbol,zone_multiplier=.60):
 cfg=COINS[symbol];zone=cfg['initial']*zone_multiplier
 state=State(fundamental=cfg['initial'],anchor=zone)
 required=int(cfg['confirm_hours']*3600/TICK_SECONDS)
 first_move=None;checkpoints={}
 for tick in range(required*2):
  old=state.fundamental
  anchor,ticks,fundamental,anchor_reference=update_anchor_and_fundamental(symbol,zone,state)
  state=replace(state,anchor=anchor,anchor_ticks=ticks,anchor_reference=anchor_reference,fundamental=fundamental)
  if first_move is None and fundamental!=old: first_move=tick+1
  if tick+1 in (required-1,required,required+1,required*2): checkpoints[tick+1]=fundamental
 return dict(symbol=symbol,required=required,first_move=first_move,start=cfg['initial'],zone=zone,final=state.fundamental,checkpoints=checkpoints)

def transient_crash_test(symbol,crash_hours=2,multiplier=.25):
 cfg=COINS[symbol];state=State(fundamental=cfg['initial'],anchor=cfg['initial'])
 for _ in range(int(crash_hours*3600/TICK_SECONDS)):
  anchor,ticks,fundamental,anchor_reference=update_anchor_and_fundamental(symbol,cfg['initial']*multiplier,state)
  state=replace(state,anchor=anchor,anchor_ticks=ticks,anchor_reference=anchor_reference,fundamental=fundamental)
 return state.fundamental/cfg['initial']-1, state.anchor_ticks,state.anchor

def manipulation_tick_test(symbol,amount,seed=731):
 cfg=COINS[symbol];base=cfg['initial'];state=State(fundamental=base,anchor=base);history=[base]*8
 p0,_=engine_step(symbol,base,state,history,rng=random.Random(seed))
 pb,_=engine_step(symbol,base,state,history,buy=amount,rng=random.Random(seed))
 ps,_=engine_step(symbol,base,state,history,sell=amount,rng=random.Random(seed))
 return (pb/p0-1)*100,(ps/p0-1)*100