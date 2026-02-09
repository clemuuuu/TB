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
├── bot/indicators.py    Classes EMA, RSI, MACD (update + compute_next pour preview live)
├── bot/strategy.py      Classe abstraite Strategy (on_candle, on_tick) — À CODER
├── ui/chart.py          lightweight-charts — 1 process par paire (chart + subcharts) + 1 PNL
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
  - Format nouveau : `- symbol: BTC/USDT` + `ema: true/false` + `rsi: true/false` + `macd: true/false`
  - Format ancien : `- BTC/USDT` (rétro-compatible, tous les indicateurs activés par défaut)
  - Ces flags contrôlent uniquement l'affichage des **charts**, pas le calcul pour la stratégie
- `trading.candle_seconds` → durée bougie en secondes (configurable, ex: 5)
- `chart.width` / `chart.height` → taille de chaque fenêtre (800x600 par défaut)
- `ema` → liste d'EMA à afficher (period, color, width). Section optionnelle
- `rsi` → liste de RSI à afficher (period, color, width). Section optionnelle
- `macd` → config MACD (fast_period, slow_period, signal_period, couleurs). Section optionnelle

## Indicateurs (`bot/indicators.py`)
- Classes `EMA`, `RSI` et `MACD` séparées du chart — réutilisables dans `bot/strategy.py`
- Chaque classe a `update(close)` (bougie complète) et `compute_next(price)` (preview live sans modifier l'état)
- **Indicateurs convergents** : au démarrage, 200 bougies 1m sont chargées via REST Binance (données publiques) et passées au worker pour warmup. Les indicateurs affichent une valeur convergée dès la première bougie live. Le fetch est fait une seule fois et partagé entre tous les indicateurs.
- **Pour ajouter un indicateur** : créer la classe dans `bot/indicators.py`, ajouter le warmup + compute_next dans `_chart_worker`, ajouter le flag dans `symbol_flags` et `config.yaml`
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

## Pour modifier
- Ajouter une stratégie → créer une classe dans `bot/strategy.py` héritant de `Strategy`
- Ajouter/retirer des paires → `config.yaml` > `trading.symbols` (1 ou N paires)
- Ajouter/modifier EMA → `config.yaml` > `ema` (ajouter/retirer des entrées period/color/width)
- Ajouter/modifier RSI → `config.yaml` > `rsi` (ajouter/retirer des entrées period/color/width)
- Ajouter/modifier MACD → `config.yaml` > `macd` (fast_period, slow_period, signal_period, couleurs)
- Changer le style du chart → `ui/chart.py`
