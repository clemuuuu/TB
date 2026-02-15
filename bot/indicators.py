
import numpy as np
from scipy.special import eval_hermite
from scipy.signal import hilbert as _hilbert
from math import lgamma, log, pi, sqrt, exp


class QuantumIndicator:
    """
    Modèle quantique de Li Lin (2024) — arXiv:2401.05823.

    Fitte la distribution des log-returns sur les fonctions propres de
    Hermite-Gauss (solutions de l'équation de Schrödinger-like) pour
    estimer le niveau d'énergie du marché.

    Ω=1 (n=0): Gaussienne → marché calme
    Ω=3 (n=1): Bimodale → marché actif, 2 régimes
    Ω=5+ (n=2+): Multimodale → marché très actif
    """
    def __init__(self, lookback: int = 200, max_n: int = 4, vol_window: int = 50,
                 return_period: int = 1):
        self.lookback = lookback
        self.max_n = max_n
        self.vol_window = vol_window
        self.return_period = max(1, return_period)  # en nombre de bougies

        self.prices: list[float] = []
        self.volumes: list[float] = []
        self.initialized = False

        # Outputs principaux
        self.energy_level = 0       # n (best-fit eigenstate)
        self.omega = 1.0            # Ω = 2n+1
        self.sigma = 0.0            # Paramètre d'échelle de volatilité
        self.fit_quality = 0.0      # Log-likelihood normalisée
        self.vol_ratio = 0.0        # volume courant / moyenne

        # Pour compass : distribution fittée
        self.r_grid: np.ndarray | None = None
        self.fitted_pdf: np.ndarray | None = None
        self.empirical_hist: tuple | None = None  # (counts, bin_edges)

        # Pour Lin Compass (ATI) : grille de phase via Hilbert
        self._xi_grid: np.ndarray | None = None
        self._phase_grid: np.ndarray | None = None

    def update(self, close: float, volume: float = 0.0):
        """Met à jour l'indicateur avec une bougie clôturée."""
        self.prices.append(close)
        self.volumes.append(volume)

        # Buffer glissant — on garde assez de prix pour lookback returns
        # Avec return_period=p, les returns sont chevauchants (overlapping) :
        # r_i = log(prix[p+i] / prix[i]), donc lookback+p prix suffisent
        max_prices = self.lookback + self.return_period + 100
        if len(self.prices) > max_prices:
            excess = len(self.prices) - max_prices
            self.prices = self.prices[excess:]
            self.volumes = self.volumes[excess:]

        # Log-returns espacés de return_period bougies :
        # r_t = log(prix_t / prix_{t - return_period})
        p = self.return_period
        if len(self.prices) >= p + self.lookback:
            prices_arr = np.array(self.prices)
            log_returns = np.log(prices_arr[p:]) - np.log(prices_arr[:-p])
            if len(log_returns) >= self.lookback:
                returns = log_returns[-self.lookback:]
                self._fit_eigenstate(returns)
                self.initialized = True

        # Volume ratio
        if len(self.volumes) >= self.vol_window + 1:
            avg_vol = float(np.mean(self.volumes[-(self.vol_window + 1):-1]))
            if avg_vol > 0:
                self.vol_ratio = self.volumes[-1] / avg_vol

    def _log_hermite_gaussian_pdf(self, r: np.ndarray, n: int, sigma: float) -> np.ndarray:
        """Log-densité f_n(r) = |Ψ_n(ξ)|² · |dξ/dr|, ξ = r/(σ√2).

        En log pour stabilité numérique :
        log f_n = log(A_n²) - ξ² + 2·log|H_n(ξ)| - log(σ√2)
        avec A_n = 1 / sqrt(√π · 2^n · n!)
        """
        sqrt2 = sqrt(2.0)
        sigma_sqrt2 = sigma * sqrt2
        xi = r / sigma_sqrt2

        # log(A_n²) = -log(√π) - n·log(2) - log(n!)
        log_an2 = -0.5 * log(pi) - n * log(2.0) - lgamma(n + 1)

        # H_n(ξ) via scipy
        hn = eval_hermite(n, xi)

        # Éviter log(0) : clamp les valeurs très petites
        abs_hn = np.abs(hn)
        abs_hn = np.maximum(abs_hn, 1e-300)

        log_f = log_an2 - xi**2 + 2.0 * np.log(abs_hn) - log(sigma_sqrt2)
        return log_f

    def _fit_eigenstate(self, returns: np.ndarray):
        """Teste chaque eigenstate n=0..max_n, sélectionne celui qui maximise
        la log-vraisemblance des returns observés."""
        var_obs = float(np.var(returns))
        if var_obs < 1e-30:
            # Returns quasi-constants → état fondamental
            self.energy_level = 0
            self.omega = 1.0
            self.sigma = 1e-10
            self.fit_quality = 0.0
            self._build_display(returns)
            self._compute_phase_grid()
            return

        best_n = 0
        best_ll = -np.inf
        best_sigma = sqrt(var_obs)

        for n in range(self.max_n + 1):
            omega_n = 2 * n + 1
            # Relation analytique du paper : Var[r]_n = σ² · (2n+1)
            sigma_n = sqrt(var_obs / omega_n)

            if sigma_n < 1e-15:
                continue

            log_pdf = self._log_hermite_gaussian_pdf(returns, n, sigma_n)

            # Filtrer les -inf (returns où H_n ≈ 0, ie nœuds)
            valid = np.isfinite(log_pdf)
            if valid.sum() < len(returns) * 0.5:
                continue  # Trop de nœuds → mauvais fit

            ll = float(np.mean(log_pdf[valid]))

            if ll > best_ll:
                best_ll = ll
                best_n = n
                best_sigma = sigma_n

        self.energy_level = best_n
        self.omega = 2.0 * best_n + 1.0
        self.sigma = best_sigma
        self.fit_quality = best_ll

        self._build_display(returns)
        self._compute_phase_grid()

    def _build_display(self, returns: np.ndarray):
        """Construit la grille + PDF fittée + histogramme empirique pour le compass."""
        # Histogramme empirique
        n_bins = min(50, max(10, len(returns) // 5))
        counts, bin_edges = np.histogram(returns, bins=n_bins, density=True)
        self.empirical_hist = (counts, bin_edges)

        # Grille pour la courbe fittée
        r_min = float(returns.min())
        r_max = float(returns.max())
        margin = (r_max - r_min) * 0.2
        if margin < 1e-10:
            margin = 1e-6
        self.r_grid = np.linspace(r_min - margin, r_max + margin, 200)

        if self.sigma > 1e-15:
            log_pdf = self._log_hermite_gaussian_pdf(self.r_grid, self.energy_level, self.sigma)
            self.fitted_pdf = np.exp(np.clip(log_pdf, -50, 50))
        else:
            self.fitted_pdf = np.zeros_like(self.r_grid)

    def _compute_phase_grid(self):
        """Calcule la grille de phase θ(ξ) via le signal analytique (Hilbert).

        L'eigenfonction φ_n(ξ) = H_n(ξ)·e^{-ξ²/2} est réelle.
        Le signal analytique (Hilbert) donne la phase instantanée θ(ξ).
        n zeros de H_n → ~n·π de variation de phase.
        """
        n = self.energy_level
        N = 2048
        xi = np.linspace(-6, 6, N)

        # Eigenfonction ψ_n(ξ) = H_n(ξ) · e^{-ξ²/2}
        hn = eval_hermite(n, xi)
        psi = hn * np.exp(-xi**2 / 2)

        # Normalisation
        norm = np.sqrt(np.trapz(psi**2, xi))
        if norm > 0:
            psi /= norm

        # Signal analytique → phase instantanée
        analytic = _hilbert(psi)
        self._phase_grid = np.angle(analytic)
        self._xi_grid = xi

    def compute_phase(self, r: float) -> float | None:
        """Calcule la phase θ pour un return r via interpolation sur la grille.

        ξ = r / (σ√2), puis interpolation linéaire de θ(ξ).
        Retourne θ ∈ [-π, π] ou None si pas initialisé.
        """
        if self._xi_grid is None or self._phase_grid is None:
            return None
        if self.sigma < 1e-15:
            return None
        xi = r / (self.sigma * sqrt(2.0))
        xi = max(float(self._xi_grid[0]), min(float(self._xi_grid[-1]), xi))
        return float(np.interp(xi, self._xi_grid, self._phase_grid))

    def compute_next(self, current_price: float) -> tuple[float, float, float] | None:
        """Prévisualisation live. Retourne (omega, sigma, fit_quality) ou None."""
        if not self.initialized:
            return None
        return self.omega, self.sigma, self.fit_quality

    def current_return(self, current_price: float) -> float | None:
        """Calcule le log-return courant sur return_period bougies."""
        if len(self.prices) < self.return_period:
            return None
        return log(current_price / self.prices[-self.return_period])

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
