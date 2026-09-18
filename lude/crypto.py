import math
import random
import time

import discord
from discord import app_commands
from discord.ext import tasks

from . import config
from .groups import crypto_group
from .utils import money


def market_engine_step(price, cfg, state, history, buy, sell, global_sentiment, shock=0.0, rng=None):
    """Avanza un tick de Market Engine 2.0 sin modificar saldos."""
    rng = rng or random
    price = max(0.01, float(price))
    fundamental = max(0.01, float(state["fundamental"]))
    regime = state["regime"] if state["regime"] in config.MARKET_REGIMES else "sideways"
    age = max(0, int(state["regime_ticks"])) + 1
    volatility = max(0.0, min(1.0, float(state["volatility"])))
    pressure = max(-1.0, min(1.0, float(state["pressure"])))
    prices = [max(0.01, float(item)) for item in history if float(item) > 0]
    if not prices or abs(prices[-1] - price) > max(0.0001, price * 1e-8):
        prices.append(price)
    returns = [math.log(after / before) for before, after in zip(prices[:-1], prices[1:])]
    momentum = sum(returns[-4:]) / min(4, len(returns)) if returns else 0.0
    spread_prices = prices[-12:]
    spread = (max(spread_prices) / min(spread_prices) - 1) if len(spread_prices) >= 3 else 1.0
    stable = len(spread_prices) >= 8 and spread < max(0.025, cfg["auto_max"] * 1.4)
    stable_ticks = int(state["stable_ticks"]) + 1 if stable else 0

    personality = {"IC": 0.75, "NVA": 1.0, "FLX": 1.35}.get(cfg["symbol"], 1.0)
    transition = min(0.36, config.CRYPTO_REGIME_SWITCH * personality + min(age, 100) * 0.0006)
    if rng.random() < transition:
        direction = math.tanh(momentum / max(cfg["auto_max"], 0.0001))
        shared = max(-1.0, min(1.0, global_sentiment))
        bull_weight = max(0.1, 1.0 + direction + shared * 0.7)
        bear_weight = max(0.1, 1.0 - direction - shared * 0.7)
        sideways_weight = 1.8 if stable else 0.9
        storm_weight = 0.35 + 0.65 * volatility
        regime = rng.choices(
            config.MARKET_REGIMES,
            weights=[bull_weight, bear_weight, sideways_weight, storm_weight], k=1,
        )[0]
        age = 0

    volume = max(0.0, buy) + max(0.0, sell)
    signed = (buy - sell) / volume if volume else 0.0
    liquidity = max(1.0, float(cfg["liquidity"]))
    flow = signed * (math.sqrt(volume) / (math.sqrt(volume) + math.sqrt(liquidity))) if volume else 0.0
    pressure = max(-1.0, min(1.0, pressure * 0.55 + flow * 0.7))
    player_move = max(-cfg["player_max"], min(cfg["player_max"], cfg["player_max"] * (flow + 0.20 * pressure)))

    speed = config.CRYPTO_DYNAMIC_RATE * {"IC": 0.6, "NVA": 1.0, "FLX": 1.35}.get(cfg["symbol"], 1.0)
    if stable_ticks >= 8:
        speed *= config.CRYPTO_STABLE_BOOST
    speed *= 1.0 + min(0.35, volume / (volume + liquidity) * 0.35) if volume else 1.0
    fundamental_step = max(
        -config.CRYPTO_FUNDAMENTAL_MAX_STEP,
        min(config.CRYPTO_FUNDAMENTAL_MAX_STEP, speed * math.log(price / fundamental)),
    )
    fundamental = max(0.01, fundamental * math.exp(fundamental_step))

    reversion_factor = {"bull": 0.12, "bear": 0.12, "sideways": 0.65, "storm": 0.04}[regime]
    reversion = -math.tanh(math.log(price / fundamental) * cfg["reversion_strength"]) * 0.20 * reversion_factor
    trend = {"bull": 0.17, "bear": -0.17, "sideways": 0.0, "storm": 0.0}[regime]
    momentum_bias = math.tanh(momentum / max(cfg["auto_max"], 0.0001)) * cfg["momentum_strength"] * 0.15
    shared_bias = max(-0.12, min(0.12, global_sentiment * config.CRYPTO_GLOBAL_INFLUENCE))
    up_probability = max(0.08, min(0.92, 0.5 + trend + reversion + momentum_bias + shared_bias))

    volatility = max(
        0.0,
        min(1.0, volatility * 0.84 + abs(momentum) / max(cfg["auto_max"], 0.0001) * 0.12 + abs(shock) * 1.8),
    )
    floor, ceiling = sorted((max(0.0, cfg["auto_min"]), max(0.0, cfg["auto_max"])))
    sample = rng.random()
    if regime == "storm" or volatility > 0.70:
        sample = max(sample, rng.random())
    elif regime == "sideways" and volatility < 0.22:
        sample = min(sample, rng.random())
    magnitude = floor + (ceiling - floor) * sample
    auto_move = magnitude if rng.random() < up_probability else -magnitude
    momentum_move = max(
        -cfg["momentum_cap"],
        min(cfg["momentum_cap"], momentum * cfg["momentum_strength"] * (0.7 if regime == "sideways" else 1.0)),
    )
    shock_move = max(-ceiling * 0.6, min(ceiling * 0.6, shock))
    total_return = max(-0.85, min(1.5, auto_move + momentum_move + player_move + shock_move))
    new_price = max(0.01, round(price * (1.0 + total_return), 4))
    return new_price, {
        "fundamental": fundamental, "regime": regime, "regime_ticks": age,
        "volatility": volatility, "pressure": pressure, "stable_ticks": stable_ticks,
    }


class CryptoMixin:
    def crypto_snapshot(self):
        with self.db_lock:
            conn = self.connect()
            rows = conn.execute("SELECT * FROM crypto_market ORDER BY symbol").fetchall()
            conn.close()
            return rows

    def crypto_buy(self, user_id: int, symbol: str, amount: int) -> tuple[bool, str]:
        symbol = symbol.upper()
        self.ensure_user(user_id)
        if symbol not in config.CRYPTO_CONFIG:
            return False, "Criptomoneda inválida. Usa IC, NVA o FLX."
        if amount <= 0:
            return False, "El monto debe ser mayor que 0."
        fee = max(1, int(round(amount * config.CRYPTO_FEE_RATE)))
        total = amount + fee
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            bank = cur.execute(
                "SELECT balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (user_id,)
            ).fetchone()
            market = cur.execute("SELECT price FROM crypto_market WHERE symbol = ?", (symbol,)).fetchone()
            if bank["balance"] < total:
                conn.rollback(); conn.close()
                return False, f"Necesitas **{money(total)}** en tu Cuenta Principal (incluye {config.CRYPTO_FEE_RATE * 100:g}% de comisión)."
            quantity = amount / float(market["price"])
            new_balance = int(bank["balance"]) - total
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            cur.execute(
                "INSERT OR IGNORE INTO crypto_holdings(user_id, symbol, quantity, cost_basis) VALUES(?, ?, 0, 0)",
                (user_id, symbol),
            )
            cur.execute(
                "UPDATE crypto_holdings SET quantity = quantity + ?, cost_basis = cost_basis + ? WHERE user_id = ? AND symbol = ?",
                (quantity, amount, user_id, symbol),
            )
            cur.execute("UPDATE crypto_market SET buy_volume = buy_volume + ? WHERE symbol = ?", (amount, symbol))
            self.log_bank(cur, user_id, "primary", "crypto_buy", total, new_balance, f"Compra {symbol}: {quantity:.8f} unidades")
            conn.commit(); conn.close()
            return True, f"📈 Compraste **{quantity:.8f} {symbol}** por **{money(amount)}** + **{money(fee)}** de comisión."

    def crypto_sell(self, user_id: int, symbol: str, percent: int) -> tuple[bool, str]:
        symbol = symbol.upper()
        self.ensure_user(user_id)
        if symbol not in config.CRYPTO_CONFIG:
            return False, "Criptomoneda inválida. Usa IC, NVA o FLX."
        if percent < 1 or percent > 100:
            return False, "El porcentaje debe estar entre 1 y 100."
        with self.db_lock:
            conn = self.connect(); cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
            holding = cur.execute(
                "SELECT quantity, cost_basis FROM crypto_holdings WHERE user_id = ? AND symbol = ?",
                (user_id, symbol),
            ).fetchone()
            if not holding or holding["quantity"] <= 0:
                conn.rollback(); conn.close()
                return False, f"No tienes {symbol} para vender."
            market = cur.execute("SELECT price FROM crypto_market WHERE symbol = ?", (symbol,)).fetchone()
            qty = float(holding["quantity"]) * (percent / 100)
            if percent == 100:
                qty = float(holding["quantity"])
            cost_portion = float(holding["cost_basis"]) * (qty / float(holding["quantity"]))
            gross = qty * float(market["price"])
            fee = max(1, int(round(gross * config.CRYPTO_FEE_RATE)))
            after_fee = max(0, int(round(gross)) - fee)
            profit = max(0, int(round(gross - cost_portion)))
            user = cur.execute("SELECT judicial_debt FROM economy_users WHERE user_id = ?", (user_id,)).fetchone()
            withheld = min(int(user["judicial_debt"]), int(round(profit * config.JUDICIAL_RATE))) if profit > 0 else 0
            credited = max(0, after_fee - withheld)
            bank = cur.execute(
                "SELECT level, balance FROM bank_accounts WHERE user_id = ? AND account_type = 'primary'", (user_id,)
            ).fetchone()
            reserved = self.bank_reservations.get(user_id, 0)
            free = config.BANK_LEVELS[bank["level"]]["capacity"] - bank["balance"] - reserved
            if free < credited:
                conn.rollback(); conn.close()
                return False, f"Tu Cuenta Principal no tiene espacio suficiente para acreditar **{money(credited)}**."
            remaining_qty = max(0.0, float(holding["quantity"]) - qty)
            remaining_cost = max(0.0, float(holding["cost_basis"]) - cost_portion)
            new_balance = int(bank["balance"]) + credited
            cur.execute(
                "UPDATE crypto_holdings SET quantity = ?, cost_basis = ? WHERE user_id = ? AND symbol = ?",
                (remaining_qty, remaining_cost, user_id, symbol),
            )
            cur.execute(
                "UPDATE bank_accounts SET balance = ? WHERE user_id = ? AND account_type = 'primary'",
                (new_balance, user_id),
            )
            if withheld:
                cur.execute("UPDATE economy_users SET judicial_debt = judicial_debt - ? WHERE user_id = ?", (withheld, user_id))
            cur.execute("UPDATE crypto_market SET sell_volume = sell_volume + ? WHERE symbol = ?", (gross, symbol))
            self.log_bank(cur, user_id, "primary", "crypto_sell", credited, new_balance, f"Venta {symbol}: {qty:.8f} unidades; fee {fee}; retención {withheld}")
            conn.commit(); conn.close()
            text = f"📉 Vendiste **{qty:.8f} {symbol}**. Bruto: **{money(gross)}** · Comisión: **{money(fee)}** · Acreditado: **{money(credited)}**."
            if withheld:
                text += f"\n⚖️ Retención judicial sobre ganancia: **{money(withheld)}**."
            return True, text

    @tasks.loop(seconds=30)
    async def crypto_price_loop(self):
        with self.db_lock:
            conn = self.connect()
            try:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                now = int(time.time())
                due = []
                for symbol, values in config.CRYPTO_CONFIG.items():
                    row = cur.execute(
                        "SELECT price, buy_volume, sell_volume, updated_at FROM crypto_market WHERE symbol = ?",
                        (symbol,),
                    ).fetchone()
                    if row and now - int(row["updated_at"]) >= config.CRYPTO_UPDATE_SECONDS:
                        due.append((symbol, values, row))
                if due:
                    global_state = cur.execute("SELECT sentiment FROM crypto_global_state WHERE id = 1").fetchone()
                    old_sentiment = float(global_state["sentiment"]) if global_state else 0.0
                    global_sentiment = max(-1.0, min(1.0, old_sentiment * 0.87 + random.uniform(-0.15, 0.15)))
                    shock = random.choice((-1.0, 1.0)) * random.uniform(0.025, 0.075) if random.random() < config.CRYPTO_SHOCK_CHANCE else 0.0
                    for symbol, values, row in due:
                        prices = cur.execute(
                            "SELECT price FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT 13", (symbol,)
                        ).fetchall()
                        history = [float(item["price"]) for item in reversed(prices)]
                        state_row = cur.execute("SELECT * FROM crypto_engine_state WHERE symbol = ?", (symbol,)).fetchone()
                        if not state_row:
                            cur.execute(
                                "INSERT OR IGNORE INTO crypto_engine_state(symbol, fundamental) VALUES(?, ?)",
                                (symbol, float(values["initial"])),
                            )
                            state_row = cur.execute("SELECT * FROM crypto_engine_state WHERE symbol = ?", (symbol,)).fetchone()
                        new_price, new_state = market_engine_step(
                            row["price"], dict(values, symbol=symbol), dict(state_row), history,
                            max(0.0, float(row["buy_volume"])), max(0.0, float(row["sell_volume"])),
                            global_sentiment, shock,
                        )
                        cur.execute(
                            "UPDATE crypto_market SET price = ?, buy_volume = 0, sell_volume = 0, updated_at = ? WHERE symbol = ?",
                            (new_price, now, symbol),
                        )
                        cur.execute(
                            """UPDATE crypto_engine_state SET fundamental = ?, regime = ?, regime_ticks = ?,
                               volatility = ?, pressure = ?, stable_ticks = ? WHERE symbol = ?""",
                            (new_state["fundamental"], new_state["regime"], new_state["regime_ticks"],
                             new_state["volatility"], new_state["pressure"], new_state["stable_ticks"], symbol),
                        )
                        cur.execute(
                            "INSERT INTO crypto_history(symbol, price, created_at) VALUES(?, ?, ?)",
                            (symbol, new_price, now),
                        )
                        cur.execute("""
                            DELETE FROM crypto_history WHERE symbol = ? AND id NOT IN (
                                SELECT id FROM crypto_history WHERE symbol = ? ORDER BY id DESC LIMIT ?
                            )
                        """, (symbol, symbol, int(config.CRYPTO_HISTORY_KEEP)))
                    cur.execute("UPDATE crypto_global_state SET sentiment = ? WHERE id = 1", (global_sentiment,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    @crypto_price_loop.before_loop
    async def before_crypto_loop(self):
        await self.bot.wait_until_ready()

    @crypto_group.command(name="mercado", description="Mercado, tendencias y últimos cinco movimientos.")
    async def crypto_mercado(self, interaction: discord.Interaction):
        await self.show_qol(interaction, "mercado")

    @crypto_group.command(name="comprar", description="Compra criptomonedas desde tu Cuenta Principal.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_comprar(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], monto: int):
        ok, text = self.crypto_buy(interaction.user.id, moneda.value, monto)
        await interaction.response.send_message(text, ephemeral=False)

    @crypto_group.command(name="vender", description="Vende un porcentaje de una criptomoneda y cobra al banco.")
    @app_commands.choices(moneda=[
        app_commands.Choice(name="InterCoin (IC)", value="IC"),
        app_commands.Choice(name="Nova (NVA)", value="NVA"),
        app_commands.Choice(name="Flux (FLX)", value="FLX"),
    ])
    async def crypto_vender(self, interaction: discord.Interaction, moneda: app_commands.Choice[str], porcentaje: int):
        ok, text = self.crypto_sell(interaction.user.id, moneda.value, porcentaje)
        await interaction.response.send_message(text, ephemeral=False)

    @crypto_group.command(name="cartera", description="Muestra tu cartera y ganancias no realizadas.")
    async def crypto_cartera(self, interaction: discord.Interaction):
        await self.show_qol(interaction, "cartera")
