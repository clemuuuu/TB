import ccxt
from utils.logger import log


class Exchange:
    """Connexion REST à Binance pour passer des ordres."""

    def __init__(self, config: dict):
        params = {}
        if config.get("api_key"):
            params["apiKey"] = config["api_key"]
            params["secret"] = config["secret"]
        if config.get("sandbox"):
            params["sandbox"] = True

        self.client = ccxt.binance(params)
        log.info("Exchange REST initialisé" + (" (sandbox)" if params.get("sandbox") else ""))

    def create_order(self, symbol: str, side: str, amount: float, price: float | None = None) -> dict:
        if price is None:
            order = self.client.create_market_order(symbol, side, amount)
        else:
            order = self.client.create_limit_order(symbol, side, amount, price)
        log.info(f"Ordre {side} {amount} {symbol} @ {price or 'market'}")
        return order

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        result = self.client.cancel_order(order_id, symbol)
        log.info(f"Ordre {order_id} annulé")
        return result

    def fetch_balance(self) -> dict:
        return self.client.fetch_balance()

    def close(self):
        if hasattr(self.client, 'close'):
            self.client.close()
