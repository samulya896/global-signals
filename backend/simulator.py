"""Deterministic market quotes, virtual portfolio, and synthetic backtest."""

from datetime import datetime, timezone
import random
import threading


SYMBOLS = ("NIFTYBEES", "BANKBEES", "ITBEES", "GOLDBEES")
BASE_PRICES = {"NIFTYBEES": 280.0, "BANKBEES": 560.0, "ITBEES": 42.0, "GOLDBEES": 100.0}


def get_quote(symbol):
    symbol = symbol.upper()
    if symbol not in BASE_PRICES:
        raise ValueError("Unknown simulated symbol.")
    # Stable day-to-day demo values: repeatable and never sourced from a broker.
    offsets = {"NIFTYBEES": 0.003, "BANKBEES": -0.002, "ITBEES": 0.006, "GOLDBEES": 0.001}
    change_percent = offsets[symbol]
    return {
        "symbol": symbol,
        "price": round(BASE_PRICES[symbol] * (1 + change_percent), 2),
        "change_percent": round(change_percent * 100, 2),
        "source": "synthetic INR demo quote — not an exchange price",
    }


class Portfolio:
    """In-memory long-only paper account. Restarting the server resets it."""

    def __init__(self, starting_cash=100_000.0):
        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.positions = {}
        self.trades = []
        self._lock = threading.RLock()

    def trade(self, symbol, side, quantity, price):
        symbol = symbol.upper()
        if symbol not in SYMBOLS:
            raise ValueError("Symbol is not in the simulated market.")
        if side not in ("buy", "sell"):
            raise ValueError("Side must be buy or sell.")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive whole number.")

        with self._lock:
            position = self.positions.get(symbol, {"quantity": 0, "average_cost": 0.0})
            total = quantity * price
            if side == "buy":
                if total > self.cash:
                    raise ValueError("Insufficient virtual cash.")
                old_quantity = position["quantity"]
                new_quantity = old_quantity + quantity
                position["average_cost"] = (
                    old_quantity * position["average_cost"] + total
                ) / new_quantity
                position["quantity"] = new_quantity
                self.positions[symbol] = position
                self.cash -= total
                realized_pnl = 0.0
            else:
                if quantity > position["quantity"]:
                    raise ValueError("Cannot sell more shares than the portfolio holds.")
                realized_pnl = quantity * (price - position["average_cost"])
                position["quantity"] -= quantity
                self.cash += total
                if position["quantity"] == 0:
                    self.positions.pop(symbol, None)
                else:
                    self.positions[symbol] = position

            trade_record = {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": round(price, 2),
                "value": round(total, 2),
                "realized_pnl": round(realized_pnl, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "simulation",
            }
            self.trades.append(trade_record)
            return trade_record

    def snapshot(self):
        with self._lock:
            holdings = []
            market_value = 0.0
            unrealized_pnl = 0.0
            for symbol, position in self.positions.items():
                quote = get_quote(symbol)
                value = position["quantity"] * quote["price"]
                pnl = position["quantity"] * (quote["price"] - position["average_cost"])
                market_value += value
                unrealized_pnl += pnl
                holdings.append({
                    "symbol": symbol,
                    "quantity": position["quantity"],
                    "average_cost": round(position["average_cost"], 2),
                    "price": quote["price"],
                    "market_value": round(value, 2),
                    "unrealized_pnl": round(pnl, 2),
                })
            return {
                "mode": "simulation",
                "starting_cash": round(self.starting_cash, 2),
                "cash": round(self.cash, 2),
                "market_value": round(market_value, 2),
                "equity": round(self.cash + market_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "holdings": holdings,
                "recent_trades": list(reversed(self.trades[-10:])),
            }

    def performance(self):
        with self._lock:
            realized = sum(trade["realized_pnl"] for trade in self.trades)
            state = self.snapshot()
            equity = state["equity"]
            return {
                "mode": "simulation",
                "starting_cash": round(self.starting_cash, 2),
                "equity": equity,
                "total_return": round((equity / self.starting_cash - 1) * 100, 2),
                "realized_pnl": round(realized, 2),
                "unrealized_pnl": state["unrealized_pnl"],
                "trade_count": len(self.trades),
            }


def run_backtest(days=90, starting_cash=100_000.0):
    """Run a repeatable synthetic news-pulse strategy, not a historical backtest."""
    rng = random.Random(20261017)
    equity = float(starting_cash)
    exposure = 0.0
    daily_returns = []
    for _ in range(days):
        event = rng.choice(("positive", "negative", "neutral", "neutral"))
        if event == "positive":
            exposure = 1.0
        elif event == "negative":
            exposure = 0.0
        market_return = rng.gauss(0.0003, 0.012)
        strategy_return = exposure * market_return
        equity *= 1 + strategy_return
        daily_returns.append(strategy_return)

    peak = starting_cash
    max_drawdown = 0.0
    curve_equity = float(starting_cash)
    for daily_return in daily_returns:
        curve_equity *= 1 + daily_return
        peak = max(peak, curve_equity)
        max_drawdown = max(max_drawdown, (peak - curve_equity) / peak)
    return {
        "mode": "synthetic simulation",
        "days": days,
        "starting_cash": round(starting_cash, 2),
        "ending_equity": round(equity, 2),
        "return_percent": round((equity / starting_cash - 1) * 100, 2),
        "max_drawdown_percent": round(max_drawdown * 100, 2),
        "note": "Synthetic deterministic data for demonstration; not historical performance.",
    }
