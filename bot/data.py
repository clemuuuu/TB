import asyncio
from datetime import datetime, timezone
import pandas as pd
import ccxt.pro as ccxtpro
from utils.logger import log


class LiveFeed:
    """Reçoit les trades en websocket et construit des bougies de N secondes."""

    def __init__(self, exchange_config: dict, symbol: str, candle_seconds: int = 10):
        self.symbol = symbol
        self.candle_seconds = candle_seconds
        self.exchange = self._create_exchange(exchange_config)

        # Bougie en cours
        self._current: dict | None = None
        # Historique des bougies fermées
        self.candles: list[dict] = []
        # Callback appelé à chaque update
        self.on_update = None
        # Callback appelé quand une bougie se ferme
        self.on_new_candle = None

    def _create_exchange(self, config: dict):
        # Pas de sandbox pour le websocket — données publiques, pas besoin
        return ccxtpro.binance()

    def _candle_start_ms(self, timestamp_ms: int) -> int:
        """Arrondit un timestamp ms au début de la bougie."""
        interval_ms = self.candle_seconds * 1000
        return (timestamp_ms // interval_ms) * interval_ms

    def _process_trade(self, price: float, amount: float, timestamp_ms: int):
        candle_time_ms = self._candle_start_ms(timestamp_ms)

        if self._current is None or self._current["_ms"] != candle_time_ms:
            # Nouvelle bougie — fermer l'ancienne
            if self._current is not None:
                self.candles.append(self._current.copy())
                if self.on_new_candle:
                    self.on_new_candle(self._current.copy())

            self._current = {
                "time": datetime.fromtimestamp(candle_time_ms / 1000, tz=timezone.utc),
                "_ms": candle_time_ms,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": amount,
            }
        else:
            # Mise à jour de la bougie en cours
            self._current["high"] = max(self._current["high"], price)
            self._current["low"] = min(self._current["low"], price)
            self._current["close"] = price
            self._current["volume"] += amount

        if self.on_update:
            self.on_update(self._current.copy())

    async def stream(self):
        log.info(f"Connexion websocket {self.symbol} (bougies {self.candle_seconds}s)...")
        try:
            while True:
                trades = await self.exchange.watch_trades(self.symbol)
                for trade in trades:
                    try:
                        self._process_trade(trade["price"], trade["amount"], trade["timestamp"])
                    except Exception as e:
                        log.error(f"Erreur process_trade: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"Erreur websocket: {e}")
        finally:
            await self.exchange.close()
            log.info("Websocket fermé")

    def get_dataframe(self) -> pd.DataFrame:
        if not self.candles:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        return pd.DataFrame(self.candles)
