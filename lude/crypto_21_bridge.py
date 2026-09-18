"""Experimental Market Engine 2.1 tick adapter.

Integration stage only: no schema alterations. Until the additive migration adds
all required columns, the EXISTING 2.0 tick coroutine runs unchanged.
"""
import random
import time

from discord.ext import tasks

from . import config
from .crypto import CryptoMixin
from .market_engine_21 import COINS, State, engine_step


REQUIRED_STATE_COLUMNS = frozenset({
    'anchor', 'anchor_ticks', 'anchor_reference', 'flow_baseline',
})


def state_schema_ready(conn):
    columns = {row['name'] for row in conn.execute('PRAGMA table_info(crypto_engine_state)')}
    return REQUIRED_STATE_COLUMNS.issubset(columns)


class CryptoMixin21(CryptoMixin):
    """Uses calibrated algorithm if state persistence exists, otherwise 2.0."""

    @tasks.loop(seconds=30)
    async def crypto_price_loop(self):
        with self.db_lock:
            conn = self.connect()
            try:
                ready = state_schema_ready(conn)
            finally:
                conn.close()
        if not ready:
            # No partial 2.1 state: preserve the old engine until migration.
            await CryptoMixin.crypto_price_loop.coro(self)
            return

        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor()
                cur.execute('BEGIN IMMEDIATE')
                now = int(time.time())
                due = []
                for symbol in COINS:
                    row = cur.execute(
                        'SELECT price, buy_volume, sell_volume, updated_at FROM crypto_market WHERE symbol = ?',
                        (symbol,),
                    ).fetchone()
                    if row and now - int(row['updated_at']) >= config.CRYPTO_UPDATE_SECONDS:
                        due.append((symbol, row))
                if due:
                    global_state = cur.execute(
                        'SELECT sentiment FROM crypto_global_state WHERE id = 1'
                    ).fetchone()
                    old_sentiment = float(global_state['sentiment']) if global_state else 0.
                    global_sentiment = max(-1., min(1., old_sentiment * .87 + random.uniform(-.15, .15)))
                    shock = (random.choice((-1., 1.)) * random.uniform(.025, .075)
                             if random.random() < config.CRYPTO_SHOCK_CHANCE else 0.)
                    for symbol, row in due:
                        prices = cur.execute(
                            'SELECT price FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT 5',
                            (symbol,),
                        ).fetchall()
                        history = [float(item['price']) for item in reversed(prices)]
                        state_row = cur.execute(
                            'SELECT * FROM crypto_engine_state WHERE symbol = ?', (symbol,)
                        ).fetchone()
                        if state_row is None:
                            # The migration stage must create a complete state row.
                            raise RuntimeError(f'Market Engine 2.1: missing state row for {symbol}')
                        state = State(
                            fundamental=float(state_row['fundamental']),
                            anchor=float(state_row['anchor']),
                            anchor_ticks=int(state_row['anchor_ticks']),
                            anchor_reference=float(state_row['anchor_reference']),
                            regime=state_row['regime'],
                            regime_ticks=int(state_row['regime_ticks']),
                            volatility=float(state_row['volatility']),
                            pressure=float(state_row['pressure']),
                            flow_baseline=float(state_row['flow_baseline']),
                            sentiment=global_sentiment,
                        )
                        new_price, new_state = engine_step(
                            symbol, float(row['price']), state, history,
                            buy=max(0., float(row['buy_volume'])),
                            sell=max(0., float(row['sell_volume'])), shock=shock,
                            rng=random,
                        )
                        cur.execute(
                            'UPDATE crypto_market SET price = ?, buy_volume = 0, sell_volume = 0, updated_at = ? WHERE symbol = ?',
                            (new_price, now, symbol),
                        )
                        cur.execute(
                            '''UPDATE crypto_engine_state SET fundamental = ?, regime = ?, regime_ticks = ?,
                               volatility = ?, pressure = ?, anchor = ?, anchor_ticks = ?,
                               anchor_reference = ?, flow_baseline = ? WHERE symbol = ?''',
                            (new_state.fundamental, new_state.regime, new_state.regime_ticks,
                             new_state.volatility, new_state.pressure, new_state.anchor,
                             new_state.anchor_ticks, new_state.anchor_reference,
                             new_state.flow_baseline, symbol),
                        )
                        cur.execute(
                            'INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)',
                            (symbol, new_price, now),
                        )
                        cur.execute('''
                            DELETE FROM crypto_history WHERE symbol = ? AND id NOT IN (
                                SELECT id FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT ?
                            )
                        ''', (symbol, symbol, int(config.CRYPTO_HISTORY_KEEP)))
                    cur.execute(
                        'UPDATE crypto_global_state SET sentiment = ? WHERE id = 1',
                        (global_sentiment,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @crypto_price_loop.before_loop
    async def before_crypto_loop(self):
        await self.bot.wait_until_ready()
