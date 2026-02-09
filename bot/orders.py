from bot.exchange import Exchange
from db.models import Order
from ui.chart import add_order_line
from utils.logger import log


class _PairPNL:
    """PNL tracker pour une paire donnée."""
    def __init__(self, symbol: str):
        self.symbol = symbol
        base, quote = symbol.split("/")
        self.base = base
        self.quote = quote
        self.position = 0.0
        self.cash_flow = 0.0
        self.total_trades = 0
        self.total_buys = 0
        self.total_sells = 0


class OrderManager:
    def __init__(self, exchange: Exchange, charts: dict | None = None):
        self.exchange = exchange
        self.charts = charts or {}       # symbol → Chart
        self._pnl: dict[str, _PairPNL] = {}

    def _get_pnl(self, symbol: str) -> _PairPNL:
        if symbol not in self._pnl:
            self._pnl[symbol] = _PairPNL(symbol)
        return self._pnl[symbol]

    def _log_pnl(self, symbol: str, side: str, fill_price: float, amount: float):
        p = self._get_pnl(symbol)
        if side == "buy":
            p.position += amount
            p.cash_flow -= fill_price * amount
            p.total_buys += 1
        else:
            p.position -= amount
            p.cash_flow += fill_price * amount
            p.total_sells += 1
        p.total_trades += 1

        unrealized = p.position * fill_price
        total_pnl = p.cash_flow + unrealized

        sign = "+" if total_pnl >= 0 else ""
        log.info(
            f"[PNL {symbol}] {sign}{total_pnl:.4f} {p.quote} | "
            f"Position: {p.position:.6f} {p.base} | "
            f"Trades: {p.total_trades} ({p.total_buys}B/{p.total_sells}S)"
        )

    def get_total_pnl(self, prices: dict) -> float:
        """PNL total toutes paires confondues (USDT)."""
        total = 0.0
        for sym, p in self._pnl.items():
            price = prices.get(sym, 0.0)
            total += p.cash_flow + p.position * price
        return total

    def _chart_for(self, symbol: str):
        return self.charts.get(symbol)

    def buy(self, symbol: str, amount: float, price: float | None = None) -> Order:
        result = self.exchange.create_order(symbol, "buy", amount, price)
        fill_price = price or result.get("average") or result.get("price")
        order = Order.create(
            symbol=symbol,
            side="buy",
            order_type="limit" if price else "market",
            price=fill_price,
            amount=amount,
            status="filled" if result["status"] == "closed" else "pending",
            exchange_id=result["id"],
        )
        if fill_price:
            self._log_pnl(symbol, "buy", fill_price, amount)
            chart = self._chart_for(symbol)
            if chart:
                add_order_line(chart, "buy", fill_price, amount)
        return order

    def sell(self, symbol: str, amount: float, price: float | None = None) -> Order:
        result = self.exchange.create_order(symbol, "sell", amount, price)
        fill_price = price or result.get("average") or result.get("price")
        order = Order.create(
            symbol=symbol,
            side="sell",
            order_type="limit" if price else "market",
            price=fill_price,
            amount=amount,
            status="filled" if result["status"] == "closed" else "pending",
            exchange_id=result["id"],
        )
        if fill_price:
            self._log_pnl(symbol, "sell", fill_price, amount)
            chart = self._chart_for(symbol)
            if chart:
                add_order_line(chart, "sell", fill_price, amount)
        return order

    def close_all_positions(self):
        """Ferme toutes les positions ouvertes (vend tout pour revenir en quote)."""
        for sym, p in self._pnl.items():
            if p.position <= 0:
                continue
            try:
                self.sell(sym, p.position)
                log.info(f"[CLOSE] {sym} — vendu {p.position:.6f} {p.base}")
            except Exception as e:
                log.error(f"[CLOSE] {sym} — échec: {e}")

    def cancel(self, order: Order):
        self.exchange.cancel_order(order.exchange_id, order.symbol)
        order.status = "cancelled"
        order.save()

    def get_history(self) -> list:
        return list(Order.select().order_by(Order.created_at.desc()))
