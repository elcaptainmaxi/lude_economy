"""Offline integration tests against the REAL Discord Cog methods, not copied SQL.

Only uses a temporary SQLite database. Run: python -m scripts.test_crypto_21_real_cog
"""
import asyncio
import math
import random
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from lude import config
from lude.core import LudeEconomy
from lude.crypto_21_bridge import state_schema_ready
from lude.crypto_21_migration import migrate_crypto_21

USER = 420042


class OfflineBot:
    async def wait_until_ready(self):
        return None


def rows(conn, table):
    return [tuple(row) for row in conn.execute('SELECT * FROM ' + table + ' ORDER BY rowid')]


def run_tick(cog, now, seed=731):
    with patch('lude.crypto_21_bridge.time.time', return_value=now), \
         patch('lude.crypto_21_bridge.random.random', return_value=1.0), \
         patch('lude.crypto_21_bridge.random.uniform', return_value=0.0):
        # Directly invoke the actual tasks.loop coroutine, without starting Discord.
        random.seed(seed)
        asyncio.run(cog.crypto_price_loop.coro(cog))


def main():
    with tempfile.TemporaryDirectory(prefix='lude21_real_cog_') as directory:
        database = str(Path(directory) / 'test_only.db')
        old_path = config.DB_PATH
        config.DB_PATH = database
        try:
            cog = LudeEconomy(OfflineBot())
            cog.ensure_user(USER)
            with cog.db_lock:
                conn = cog.connect()
                conn.execute("UPDATE bank_accounts SET level = 4, balance = 100000 WHERE user_id = ? AND account_type = 'primary'", (USER,))
                for symbol, price, fundamental in [('IC', 1783.88, 1040.), ('NVA', 885.31, 274.60), ('FLX', .59, 38.)]:
                    conn.execute('UPDATE crypto_market SET price=?, updated_at=? WHERE symbol=?', (price, 1000000, symbol))
                    conn.execute('UPDATE crypto_engine_state SET fundamental=? WHERE symbol=?', (fundamental, symbol))
                    conn.execute('UPDATE crypto_history SET price=?, created_at=? WHERE symbol=?', (price, 1000000, symbol))
                conn.commit()
                protected = {table: rows(conn, table) for table in ('crypto_market', 'crypto_holdings', 'crypto_history', 'bank_accounts')}
                assert not state_schema_ready(conn), '2.1 must not silently activate without migration'
                conn.execute('BEGIN EXCLUSIVE')
                migrate_crypto_21(conn)
                conn.commit()
                assert state_schema_ready(conn)
                assert protected == {table: rows(conn, table) for table in protected}, 'migration altered protected data'
                anchors = dict(conn.execute('SELECT symbol,anchor FROM crypto_engine_state'))
                assert anchors == {'IC':1783.88, 'NVA':885.31, 'FLX':.59}, anchors
                conn.close()
            print('PASS real Cog DB setup + additive migration preserves protected data and current prices')

            success, message = cog.crypto_buy(USER, 'FLX', 500)
            assert success, message
            conn = cog.connect()
            fee = max(1, int(round(500 * config.CRYPTO_FEE_RATE)))
            balance = conn.execute("SELECT balance FROM bank_accounts WHERE user_id=? AND account_type='primary'", (USER,)).fetchone()[0]
            holding = conn.execute("SELECT quantity,cost_basis FROM crypto_holdings WHERE user_id=? AND symbol='FLX'", (USER,)).fetchone()
            assert balance == 100000 - 500 - fee, (balance, fee)
            assert math.isclose(holding['quantity'], 500/.59, rel_tol=1e-12)
            assert holding['cost_basis'] == 500
            assert conn.execute("SELECT buy_volume FROM crypto_market WHERE symbol='FLX'").fetchone()[0] == 500
            conn.close()
            print(f'PASS real crypto_buy: amount=500, actual fee={fee}, bank debit, units, cost basis and volume')

            now = 1000300
            run_tick(cog, now)
            conn = cog.connect()
            tick_one = {table: rows(conn, table) for table in ('crypto_market','crypto_engine_state','crypto_history','crypto_global_state','bank_accounts','crypto_holdings')}
            assert all(row['updated_at'] == now and row['buy_volume'] == 0 for row in conn.execute('SELECT * FROM crypto_market'))
            assert all(row['anchor_ticks'] >= 1 for row in conn.execute('SELECT * FROM crypto_engine_state'))
            assert conn.execute('SELECT COUNT(*) FROM crypto_history').fetchone()[0] == 6
            conn.close()
            run_tick(cog, now)
            conn = cog.connect()
            assert tick_one == {table: rows(conn, table) for table in tick_one}, 'same-time invocation duplicated a tick'
            conn.close()
            print('PASS actual CryptoMixin21 loop: three ticks, consumed volume, duplicate-time idempotency')

            success, message = cog.crypto_sell(USER, 'FLX', 50)
            assert success, message
            conn = cog.connect()
            new_holding = conn.execute("SELECT quantity,cost_basis FROM crypto_holdings WHERE user_id=? AND symbol='FLX'", (USER,)).fetchone()
            assert math.isclose(new_holding['quantity'], holding['quantity']/2, rel_tol=1e-12)
            assert math.isclose(new_holding['cost_basis'], 250., rel_tol=1e-12)
            pending = conn.execute("SELECT sell_volume,price FROM crypto_market WHERE symbol='FLX'").fetchone()
            assert pending['sell_volume'] > 0
            assert conn.execute("SELECT COUNT(*) FROM bank_history WHERE user_id=? AND action IN ('crypto_buy','crypto_sell')", (USER,)).fetchone()[0] == 2
            conn.close()
            print('PASS real crypto_sell: proportional holdings/cost basis, banking log and sell volume')

            # Reconstruct Cog on the SAME temporary DB, just like a process restart.
            restarted = LudeEconomy(OfflineBot())
            conn = restarted.connect()
            before_restart = {table: rows(conn, table) for table in ('crypto_market','crypto_engine_state','crypto_holdings','bank_accounts')}
            conn.close()
            run_tick(restarted, 1000600, seed=732)
            conn = restarted.connect()
            assert conn.execute("SELECT sell_volume FROM crypto_market WHERE symbol='FLX'").fetchone()[0] == 0
            assert conn.execute("SELECT anchor_ticks FROM crypto_engine_state WHERE symbol='FLX'").fetchone()[0] > 1
            assert rows(conn, 'bank_accounts') == before_restart['bank_accounts']
            assert rows(conn, 'crypto_holdings') == before_restart['crypto_holdings']
            conn.close()
            print('PASS Cog restart restores persisted state and next tick processes sale once')

            conn = restarted.connect()
            baseline = {table: rows(conn, table) for table in ('crypto_market','crypto_engine_state','crypto_history','crypto_global_state')}
            conn.execute("CREATE TRIGGER abort_test_history BEFORE INSERT ON crypto_history BEGIN SELECT RAISE(ABORT, 'forced test failure'); END")
            conn.commit()
            conn.close()
            try:
                run_tick(restarted, 1000900, seed=733)
            except sqlite3.DatabaseError as exc:
                assert 'forced test failure' in str(exc), str(exc)
            else:
                raise AssertionError('Expected forced database failure')
            conn = restarted.connect()
            assert baseline == {table: rows(conn, table) for table in baseline}, 'tick partially committed after SQLite error'
            conn.close()
            print('PASS forced database error rolls back prices, engine state, history and global state')
            print('RESULT: 6 real-Cog offline integration checks passed')
        finally:
            config.DB_PATH = old_path


if __name__ == '__main__':
    main()
