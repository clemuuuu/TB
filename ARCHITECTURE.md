# TB - Trading Bot Crypto (Binance)

## Projet
Bot de trading crypto Binance Spot avec graphique candlestick live et ordres en temps réel.
Le user parle français.

## État actuel
- **Multi-paires** : 1 fenêtre par paire (multiprocessing), avec subcharts intégrés (RSI, MACD)
- Chart live TradingView fonctionnel (bougies custom construites depuis websocket)
- Ordres sandbox (testnet Binance) fonctionnels avec lignes pointillées sur le chart
- PNL tracker **par paire** dans le terminal (unités correctes : USDT, BTC, etc.)
- **Graphique PNL total** temps réel dans une fenêtre dédiée (courbe + topbar)
- DB SQLite pour l'historique des ordres
- Montants d'ordres calculés dynamiquement (respecte le filtre NOTIONAL de Binance)
- Arrêt propre (Ctrl+C) : websockets fermés, fenêtres tuées, aucun process orphelin
- **EMA overlay** configurable sur chaque chart (section `ema:` dans config.yaml)
- **RSI subchart** configurable sous le chart principal (section `rsi:` dans config.yaml)
- **MACD subchart** configurable sous le chart principal (section `macd:` dans config.yaml)
- **Quantum Indicator** : modèle de Li Lin (2024, arXiv:2401.05823) — fitting Hermite-Gauss sur la distribution des log-returns → niveau d'énergie Ω (état du marché). 2 modes : subchart linéaire (Omega/Sigma) + fenêtre distribution (histogramme + courbe fittée)
- **Légende** visible sur le chart principal (OHLC + noms EMA), désactivée sur les subcharts (bug JS)
- Fermeture auto des positions ouvertes au Ctrl+C
- Actuellement : ordres random toutes les 5s par paire pour tester — pas encore de vraie stratégie
- **Prochaine étape** : coder une stratégie dans `bot/strategy.py`

## Environnement
- Python 3.14 — `source ~/spyder-env/bin/activate` (OBLIGATOIRE avant de lancer)
- Projet : `/home/extra/TB` (symlink `~/TB`)
- Venv : `/home/extra/spyder-env` (symlink `~/spyder-env`)
- Lancement : `cd ~/TB && python main.py`
- GTK/gi : symlinké manuellement dans le venv depuis `/usr/lib/python3.14/site-packages/gi`

## Architecture
```
main.py                  Async — boucle sur symbols, 1 feed par paire (asyncio.gather)
├── bot/exchange.py      REST ccxt.binance — ordres, solde, sandbox/réel (partagé entre paires)
├── bot/data.py          Websocket ccxt.pro — trades live → bougies custom N secondes (1 par paire)
├── bot/orders.py        OrderManager — buy/sell + DB + ligne chart + PNL par paire + get_total_pnl
├── bot/indicators.py    Classes EMA, RSI, MACD, QuantumIndicator (update + compute_next)
├── bot/strategy.py      Classe abstraite Strategy (on_candle, on_tick) — À CODER
├── ui/chart.py          lightweight-charts — 1 process par paire (chart + subcharts) + 1 PNL
├── ui/compass.py        Quantum Distribution — fenêtre distribution (histogramme + courbe fittée) par paire
├── db/models.py         Peewee SQLite — Order, Trade
└── utils/logger.py      rich logger
```

## Choix techniques
- **Websocket** (ccxt.pro) pour les données live, pas de polling REST
- **Bougies custom** construites à la volée depuis les trades bruts (pas limité aux timeframes Binance)
- **Multiprocessing** : chaque paire a son propre process (`mp.Process`) avec sa fenêtre pywebview
  - `_ChartProxy` envoie les données via `mp.Queue` (candles, order_lines)
  - `_chart_worker` reçoit et met à jour le chart + subcharts (RSI, MACD) dans son process
  - `_PnlProxy` / `_pnl_chart_worker` : fenêtre PNL dédiée avec `create_line()`
  - `mp.set_start_method("fork")` obligatoire (Python 3.14 utilise `forkserver` par défaut, qui ne transmet pas `gi`)
  - `os.setpgrp()` dans le worker + `os.killpg()` pour tuer le worker ET son sous-process pywebview
  - `daemon=False` obligatoire (lightweight-charts lance son propre sous-process, interdit pour les daemons)
- **Subcharts** (`create_subchart()`) pour RSI et MACD dans la même fenêtre que le chart principal
  - `inner_height` sur le chart principal pour répartir l'espace (0.5 si 2 subcharts, 0.7 si 1)
  - `sync=True` pour synchroniser les axes temporels
  - `grid(vert_enabled=False, horz_enabled=False)` pour un rendu propre
  - **BUG crosshair sync** : `sync=True` + `series.update()` → le mécanisme de sync itère sur TOUTES les séries synced. Si une série n'a pas de données → `Value is null` JS error qui tue Thread-2 (le thread d'évaluation JS de PyWV). Le crash est **bidirectionnel** : update du main chart OU d'un subchart peut trigger le sync sur les autres.
  - **Fix** : monkey-patch de `PyWV.loop` dans `_chart_worker` pour avaler `JavascriptException` au lieu de `raise` (Thread-2 survit). Hérité par le process PyWV via `mp.set_start_method("fork")`.
  - **Ordre des updates** : les indicator line updates sont pushées AVANT le `chart.set()`/`chart.update()` du main chart. Réduit la fréquence de l'erreur (les subcharts ont déjà des données quand le sync fire). Le monkey-patch est le filet de sécurité.
- **Légende** : `legend(visible=True, ohlc=True, lines=True)` sur le chart principal UNIQUEMENT
  - **BUG** : `legend(visible=True)` sur les subcharts crash le legendHandler JS (`t.seriesData.get` undefined)
  - Les subcharts DOIVENT avoir `legend(visible=False)` — c'est un bug dans lightweight-charts, pas contournable
  - Le chart principal affiche les noms OHLC + EMA sans problème
- **Lignes horizontales pointillées** pour marquer les ordres (vert=buy, rouge=sell)
- **chart.update(pd.Series)** pour mettre à jour la bougie en cours, **chart.set(df)** pour la première
- Le champ `_ms` dans les candles est interne — filtré avant envoi au chart
- Le LiveFeed n'utilise PAS le sandbox (données publiques), seul l'Exchange REST utilise sandbox
- **Filtre NOTIONAL** : les montants d'ordres sont calculés via `min_cost / price * 5-10x` pour respecter le minimum notional Binance (qui utilise un prix moyen 5min)
- **Arrêt propre** : exception handler silencieux pour les CancelledError ccxt/aiohttp, `killpg` pour les fenêtres

## Config (config.yaml)
- `exchange.sandbox: true` → testnet Binance (clés API testnet déjà configurées)
- `trading.symbols` → liste de paires avec indicateurs par paire :
  - Format nouveau : `- symbol: BTC/USDT` + `ema: true/false` + `rsi: true/false` + `macd: true/false` + `quantum_line: true/false` + `quantum_window: true/false`
  - Format ancien : `- BTC/USDT` (rétro-compatible, tous les indicateurs activés par défaut)
  - Ces flags contrôlent uniquement l'affichage des **charts**, pas le calcul pour la stratégie
- `trading.candle_seconds` → durée bougie en secondes (configurable, ex: 5)
- `chart.width` / `chart.height` → taille de chaque fenêtre (800x600 par défaut)
- `ema` → liste d'EMA à afficher (period, color, width). Section optionnelle
- `rsi` → liste de RSI à afficher (period, color, width). Section optionnelle
- `macd` → config MACD (fast_period, slow_period, signal_period, couleurs). Section optionnelle
- `quantum` → config Quantum Indicator (lookback, return_period, max_n, vol_window, omega_color, sigma_color). Section optionnelle. `return_period` est en nombre de **bougies** (pas en secondes) — le timeframe effectif dépend de `candle_seconds`

## Indicateurs (`bot/indicators.py`)
- Classes `EMA`, `RSI` et `MACD` séparées du chart — réutilisables dans `bot/strategy.py`
- Chaque classe a `update(close)` (bougie complète) et `compute_next(price)` (preview live sans modifier l'état)
- **Indicateurs convergents** : au démarrage, 200 bougies 1m sont chargées via REST Binance (données publiques) et passées au worker pour warmup. Les indicateurs affichent une valeur convergée dès la première bougie live. Le fetch est fait une seule fois et partagé entre tous les indicateurs.
- **Pour ajouter un indicateur** : créer la classe dans `bot/indicators.py`, ajouter le warmup + compute_next dans `_chart_worker` (section 2 "Indicator Updates", AVANT le main chart update section 3), ajouter le flag dans `symbol_flags` et `config.yaml`. **IMPORTANT** : les line updates des subcharts DOIVENT être dans la section 2 (avant `chart.set()`/`chart.update()`) sinon le crosshair sync crash.
- **EMA** : overlay via `create_line()` sur le chart candlestick principal
  - Configurable dans `config.yaml` section `ema:` (liste de {period, color, width})
  - Calcul : SMA initial puis EMA classique
  - `update()` appelé au changement de bougie, `compute_next()` pour le preview live (pas de double smoothing)
- **RSI** : subchart sous le chart principal
  - Configurable dans `config.yaml` section `rsi:` (liste de {period, color, width})
  - Lignes horizontales à 30 (survendu) et 70 (suracheté)
  - Calcul : Wilder's smoothing (SMA initial + lissage exponentiel)
  - `update()` au changement de bougie, `compute_next()` pour preview live
- **MACD** : subchart sous le RSI
  - Configurable dans `config.yaml` section `macd:` (fast_period, slow_period, signal_period, couleurs)
  - 3 composants : ligne MACD, ligne Signal, histogramme (`create_histogram`)
  - Utilise 3 EMA internes (fast, slow, signal)
  - `update()` au changement de bougie, `compute_next()` retourne (macd, signal, histogram)
- **Quantum Indicator** : modèle de Li Lin (2024) — "Quantum Probability Theoretic Asset Return Modeling" (arXiv:2401.05823)
  - Fitte la distribution des log-returns sur les fonctions propres de Hermite-Gauss (solutions de l'équation de Schrödinger-like)
  - Relation clé : `Var[r] = σ² · (2n+1)` → `σ_n = sqrt(Var_obs / Ω)` pour chaque eigenstate n
  - Sélection du meilleur n (0..max_n) par maximum de log-vraisemblance
  - Ω=1 (n=0) : Gaussienne → marché calme ; Ω=3 (n=1) : bimodale → 2 régimes ; Ω=5+ : multimodale → volatile
  - `return_period` : écart en **nombre de bougies** pour calculer un return (`log(prix_t / prix_{t-period})`). Permet de découpler le timeframe de l'indicateur de celui des bougies. Ex: `return_period=60` + `candle_seconds=1` → returns sur 1 minute ; `return_period=60` + `candle_seconds=60` → returns sur 1 heure
  - Outputs : `energy_level` (n), `omega` (Ω=2n+1), `sigma` (échelle), `fit_quality` (log-vraisemblance), `vol_ratio`
  - `update(close, volume)` au changement de bougie, `compute_next(price)` retourne `(omega, sigma, fit_quality)`
  - `current_return(price)` retourne le log-return courant sur `return_period` bougies pour le marqueur du compass
  - Sigma affiché en **basis points** (×10000) sur le subchart pour être visible à côté d'Omega
  - 2 modes d'affichage par paire (flags `quantum_line` et `quantum_window` dans config.yaml) :
    - **Subchart linéaire** : lignes Omega (cyan) + Sigma bps (orange) avec références à Ω=1 et Ω=3
    - **Fenêtre Distribution** : histogramme empirique + courbe PDF fittée + marqueur return courant (`ui/compass.py`)

## Pour modifier
- Ajouter une stratégie → créer une classe dans `bot/strategy.py` héritant de `Strategy`
- Ajouter/retirer des paires → `config.yaml` > `trading.symbols` (1 ou N paires)
- Ajouter/modifier EMA → `config.yaml` > `ema` (ajouter/retirer des entrées period/color/width)
- Ajouter/modifier RSI → `config.yaml` > `rsi` (ajouter/retirer des entrées period/color/width)
- Ajouter/modifier MACD → `config.yaml` > `macd` (fast_period, slow_period, signal_period, couleurs)
- Ajouter/modifier Quantum → `config.yaml` > `quantum` (lookback, return_period, max_n, vol_window, omega_color, sigma_color) + flags par paire (`quantum_line`, `quantum_window`)
- Changer le style du chart → `ui/chart.py`
