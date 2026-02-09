
class EMA:
    """Exponential Moving Average."""
    def __init__(self, period: int):
        self.period = period
        self.value = None
        self.initialized = False
        self._history = []

    def update(self, close: float):
        """Met à jour l'EMA avec une bougie clôturée (confirmed close)."""
        if self.value is None:
            self._history.append(close)
            if len(self._history) >= self.period:
                self.value = sum(self._history[-self.period:]) / self.period
                self.initialized = True
        else:
            k = 2 / (self.period + 1)
            self.value = close * k + self.value * (1 - k)
            self.initialized = True

    def compute_next(self, current_price: float) -> float | None:
        """Calcule une prévisualisation de l'EMA avec le prix actuel (sans modifier l'état)."""
        if self.value is None:
            # Si pas encore assez d'historique, on tente de calculer une SMA avec le prix actuel
            if len(self._history) == self.period - 1:
                temp = self._history + [current_price]
                return sum(temp) / self.period
            return None
        
        # Formule standard: EMA_curr = Price * k + EMA_prev * (1-k)
        k = 2 / (self.period + 1)
        return current_price * k + self.value * (1 - k)


class RSI:
    """Relative Strength Index."""
    def __init__(self, period: int):
        self.period = period
        self.value = None
        self.initialized = False
        self._history = []
        self._avg_gain = None
        self._avg_loss = None

    def update(self, close: float):
        """Met à jour le RSI avec une bougie clôturée (confirmed close)."""
        self._history.append(close)
        
        if self._avg_gain is None:
            # Phase d'initialisation : on attend period + 1 points pour avoir period deltas
            if len(self._history) >= self.period + 1:
                gains = 0.0
                losses = 0.0
                # On calcule les changements sur les 'period' derniers intervalles
                subset = self._history[-(self.period + 1):]
                for i in range(1, len(subset)):
                    delta = subset[i] - subset[i - 1]
                    if delta > 0:
                        gains += delta
                    else:
                        losses += abs(delta)
                self._avg_gain = gains / self.period
                self._avg_loss = losses / self.period
                self._calculate_rsi()
                self.initialized = True
        else:
            # Phase récursive (Wilder's Smoothing)
            delta = close - self._history[-2]
            gain = delta if delta > 0 else 0.0
            loss = abs(delta) if delta < 0 else 0.0
            
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period
            self._calculate_rsi()
            self.initialized = True

    def _calculate_rsi(self):
        if self._avg_loss == 0:
            self.value = 100.0
        else:
            rs = self._avg_gain / self._avg_loss
            self.value = 100.0 - (100.0 / (1.0 + rs))

    def compute_next(self, current_price: float) -> float | None:
        """Calcule une prévisualisation du RSI avec le prix actuel."""
        if not self._history:
            return None

        # Cas 1: Pas encore initialisé
        if self._avg_gain is None:
            # On a besoin de 'period' deltas.
            # Si on a 'period' points dans l'historique, current_price sera le (period+1)ème point
            if len(self._history) == self.period:
                temp_hist = self._history + [current_price]
                gains = 0.0
                losses = 0.0
                for i in range(1, len(temp_hist)):
                    delta = temp_hist[i] - temp_hist[i - 1]
                    if delta > 0:
                        gains += delta
                    else:
                        losses += abs(delta)
                
                est_avg_gain = gains / self.period
                est_avg_loss = losses / self.period
                
                if est_avg_loss == 0:
                    return 100.0
                rs = est_avg_gain / est_avg_loss
                return 100.0 - (100.0 / (1.0 + rs))
            return None

        # Cas 2: Déjà initialisé, calcul incrémental basé sur l'état courant
        last_close = self._history[-1]
        delta = current_price - last_close
        gain = delta if delta > 0 else 0.0
        loss = abs(delta) if delta < 0 else 0.0

        est_avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
        est_avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        if est_avg_loss == 0:
            return 100.0
        rs = est_avg_gain / est_avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


class MACD:
    """Moving Average Convergence Divergence."""
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        self.fast_ema = EMA(fast_period)
        self.slow_ema = EMA(slow_period)
        self.signal_ema = EMA(signal_period)
        
        self.macd = None
        self.signal = None
        self.histogram = None
        self.initialized = False

    def update(self, close: float):
        """Met à jour le MACD avec une bougie clôturée."""
        self.fast_ema.update(close)
        self.slow_ema.update(close)
        
        if self.fast_ema.initialized and self.slow_ema.initialized:
            self.macd = self.fast_ema.value - self.slow_ema.value
            self.signal_ema.update(self.macd)
            
            if self.signal_ema.initialized:
                self.signal = self.signal_ema.value
                self.histogram = self.macd - self.signal
                self.initialized = True

    def compute_next(self, current_price: float) -> tuple[float, float, float] | None:
        """Calcule une prévisualisation (MACD, Signal, Hist)."""
        fast_next = self.fast_ema.compute_next(current_price)
        slow_next = self.slow_ema.compute_next(current_price)
        
        if fast_next is None or slow_next is None:
            return None
            
        macd_next = fast_next - slow_next
        
        # Pour le signal, on doit 'prévoir' ce que serait l'EMA du signal
        # si on lui donnait ce macd_next.
        signal_next = self.signal_ema.compute_next(macd_next)
        
        if signal_next is None:
            return None
            
        hist_next = macd_next - signal_next
        return macd_next, signal_next, hist_next
