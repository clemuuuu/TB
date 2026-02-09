from abc import ABC, abstractmethod
import pandas as pd
from bot.orders import OrderManager


class Strategy(ABC):
    def __init__(self, order_manager: OrderManager):
        self.om = order_manager

    @abstractmethod
    def on_candle(self, candles: pd.DataFrame):
        """Appelé à chaque nouvelle bougie."""
        ...

    @abstractmethod
    def on_tick(self, ticker: dict):
        """Appelé à chaque mise à jour du prix."""
        ...
