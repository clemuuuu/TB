=====================================
  TB - Trading Bot Crypto (Binance)
=====================================

DESCRIPTION
-----------
Bot de trading crypto qui se connecte a Binance en temps reel via websocket.
Supporte plusieurs paires simultanement (BTC/USDT, ETH/BTC, DOT/USDT, etc.)
avec une fenetre par paire (un process Python par chart).
Affiche un graphique candlestick live (style TradingView) avec les ordres
du bot marques par des lignes horizontales pointillees (vert = achat, rouge = vente).
Indicateurs EMA en overlay sur chaque chart (periode, couleur, epaisseur configurables).
Indicateurs RSI en subchart sous le chart principal (periode, couleur configurables).
Indicateurs MACD en subchart sous le RSI (fast/slow/signal, couleurs configurables).
Indicateurs convergents : 200 bougies 1m chargees au demarrage via REST Binance
pour que EMA/RSI/MACD affichent des valeurs stables des la premiere bougie live.
Suivi du PNL (Profit & Loss) par paire en temps reel dans le terminal
+ graphique PNL total en temps reel (fenetre dediee avec courbe).
Fermeture automatique des positions ouvertes a l'arret (Ctrl+C).


PRE-REQUIS
----------
- Python 3.14 avec le venv spyder-env
- Packages : ccxt, lightweight-charts, pandas, pyyaml, peewee, rich, aiohttp
- GTK (pywebview) pour la fenetre du graphique
- Cles API testnet Binance (https://testnet.binance.vision)


LANCEMENT
---------
1. Activer l'environnement,

2. Se placer dans le dossier :
   cd ~/TB

3. Lancer le bot :
   python main.py                 (avec graphiques)
   python main.py --no-chart      (terminal seul, sans fenetres)

=> Une fenetre s'ouvre par paire (chart + RSI + MACD) + 1 fenetre PNL
   (2 paires = 2 fenetres chart + 1 fenetre PNL = 3 fenetres).
   Avec --no-chart, seul le terminal affiche les ordres et le PNL.
=> Les bougies se construisent toutes les X secondes (reglable dans config.yaml > candle_seconds).
=> Toutes les Y secondes, un ordre random (buy/sell) est passe par paire (reglable dans main.py > random_orders).
=> Chaque ordre apparait comme une ligne pointillee horizontale sur la bonne fenetre.
=> Le PNL par paire s'affiche dans le terminal apres chaque ordre.
=> Le PNL total s'affiche en temps reel dans la fenetre PNL (courbe + topbar).
=> Ctrl+C dans le terminal pour arreter proprement.


CONFIGURATION (config.yaml)
----------------------------
exchange:
  api_key / secret   -> Cles API Binance (testnet pour le moment)
  sandbox: true      -> true = testnet (argent fictif), false = reel (ATTENTION)

trading:
  symbols            -> Liste de paires avec indicateurs par paire
                        Format : - symbol: BTC/USDT
                                   ema: true     (afficher EMA overlay)
                                   rsi: true     (afficher subchart RSI)
                                   macd: true    (afficher subchart MACD)
                        Ancien format aussi supporte : - BTC/USDT (tout active)
                        ema/rsi/macd controlent l'affichage des charts, pas le calcul
  candle_seconds     -> Duree d'une bougie en secondes (5 = tres rapide)
  type               -> spot

chart:
  width / height     -> Taille de chaque fenetre chart

ema:                   -> Liste d'EMA a afficher en overlay (optionnel)
  - period             -> Periode de l'EMA (ex: 9, 21, 50)
    color              -> Couleur de la courbe (ex: "#2962FF")
    width              -> Epaisseur de la ligne (ex: 1, 2)
                          Supprimer la section ema = pas d'EMA affiche

rsi:                     -> Liste de RSI a afficher en subchart (optionnel)
  - period               -> Periode du RSI (ex: 14, 21)
    color                -> Couleur de la courbe (ex: "#7E57C2")
    width                -> Epaisseur de la ligne (ex: 1, 2)
                            Supprimer la section rsi = pas de RSI affiche
                            Lignes horizontales a 30 (survendu) et 70 (surachete)

macd:                      -> Config MACD en subchart (optionnel)
  fast_period              -> Periode EMA rapide (ex: 12)
  slow_period              -> Periode EMA lente (ex: 26)
  signal_period            -> Periode signal (ex: 9)
  color_macd               -> Couleur ligne MACD
  color_signal             -> Couleur ligne Signal
  color_hist               -> Couleur histogramme
                              Supprimer la section macd = pas de MACD affiche


STRUCTURE DU PROJET
-------------------
TB/
|
+-- config.yaml          Config exchange, paires, timeframe, chart, indicateurs
+-- requirements.txt     Dependances Python (pip install -r requirements.txt)
+-- main.py              Point d'entree -- lance tout en parallele (asyncio)
+-- readme.txt           Ce fichier
+-- tb.db                Base SQLite (creee automatiquement au 1er lancement)
+-- CLAUDE.md            Instructions pour Claude Code
|
+-- bot/                 LOGIQUE TRADING
|   +-- __init__.py
|   +-- exchange.py      Wrapper REST ccxt pour Binance
|   |                      - create_order, cancel_order, fetch_balance
|   |                      - Gere sandbox (testnet) / reel
|   |                      - Partage entre toutes les paires
|   |
|   +-- data.py          Flux de donnees en temps reel (1 LiveFeed par paire)
|   |                      - Websocket Binance via ccxt.pro (watch_trades)
|   |                      - Construit des bougies custom (ex: 5s) a la volee
|   |                      - Callbacks: on_update (chaque trade), on_new_candle
|   |
|   +-- orders.py        Gestionnaire d'ordres (1 OrderManager partage)
|   |                      - buy() / sell() / cancel()
|   |                      - Sauvegarde en DB + affiche la ligne sur le bon chart
|   |                      - PNL par paire (_PairPNL) avec unites correctes
|   |                      - Montants calcules dynamiquement (filtre NOTIONAL)
|   |
|   +-- indicators.py    Classes EMA, RSI, MACD (calcul + preview live)
|   |                      - EMA : update(close) + compute_next(price)
|   |                      - RSI : update(close) + compute_next(price)
|   |                      - MACD : update(close) + compute_next(price) -> (macd, signal, hist)
|   |                      - Reutilisables dans strategy.py pour les decisions
|   |
|   +-- strategy.py      Classe abstraite Strategy (placeholder)
|                          - on_candle() : appele a chaque nouvelle bougie
|                          - on_tick() : appele a chaque update de prix
|
+-- ui/                  INTERFACE GRAPHIQUE
|   +-- __init__.py
|   +-- chart.py         Graphique candlestick live (multiprocessing)
|                          - lightweight-charts (TradingView) via pywebview
|                          - 1 process par paire (mp.Process + mp.Queue)
|                          - _ChartProxy : envoie les donnees, _chart_worker affiche
|                          - Chart principal (bougies + EMA overlay)
|                          - Subchart RSI (create_subchart, lignes 30/70)
|                          - Subchart MACD (histogramme + ligne MACD + Signal)
|                          - _PnlProxy / _pnl_chart_worker : fenetre PNL dediee
|                          - update_candle() : met a jour la bougie en cours
|                          - update_pnl() : envoie un point PNL au chart dedie
|                          - add_order_line() : ligne pointillee horizontale
|                          - Topbar : symbole + prix en temps reel
|
+-- db/                  BASE DE DONNEES
|   +-- __init__.py
|   +-- models.py        Modeles Peewee (SQLite)
|                          - Order : symbol, side, price, amount, status, exchange_id
|                          - Trade : order, price, amount, fee
|                          - init_db() : cree les tables automatiquement
|
+-- utils/               UTILITAIRES
    +-- __init__.py
    +-- logger.py        Logger avec rich (couleurs, timestamps)


FLUX DE DONNEES (par paire)
---------------------------

  Binance Websocket (trades publics)
       |
       v
  LiveFeed (data.py)             1 instance par paire
       |  Construit des bougies de N secondes
       |
       +-->  Chart (chart.py)            Bougie + EMA + RSI + MACD (via mp.Queue)
       |
       v
  Strategy (strategy.py)              Decide quand acheter/vendre
       |
       v
  OrderManager (orders.py)            Passe l'ordre sur Binance
       |
       +-->  Exchange (exchange.py)    Envoie l'ordre REST a Binance
       +-->  DB (models.py)           Sauvegarde l'ordre en SQLite
       +-->  Chart (chart.py)         Ligne pointillee sur la bonne fenetre
       +-->  Terminal                  [PNL ETH/BTC] +0.0012 BTC | Position: 0.02 ETH
       +-->  Chart PNL                Courbe PNL total temps reel (fenetre dediee)


PNL (PROFIT & LOSS)
--------------------
Apres chaque ordre, le terminal affiche le PNL de la paire concernee :

  [PNL BTC/USDT] +12.35 USDT | Position: 0.0023 BTC | Trades: 8 (5B/3S)
  [PNL ETH/BTC] -0.0004 BTC | Position: 0.015 ETH | Trades: 3 (2B/1S)

- PNL      : gain/perte total dans la devise quote (USDT, BTC, etc.)
- Position : quantite de la devise base detenue en net
- Trades   : nombre total (Buys / Sells)

Calcul : PNL = (quote recu des ventes - quote depense en achats) + (base detenu x prix actuel)


PROCHAINES ETAPES
-----------------
- Coder une vraie strategie dans bot/strategy.py (basee sur RSI/EMA/MACD)
- Remplacer les ordres random par la strategie
- Backtesting sur donnees historiques
- Passer en mode reel quand c'est pret (sandbox: false)


LEGENDE
-------
- Le chart principal affiche une legende (OHLC + noms EMA) en haut a gauche
- Les subcharts (RSI, MACD) n'ont PAS de legende : bug JS dans lightweight-charts
  (legendHandler crash sur t.seriesData.get undefined quand legend est activee sur un subchart)
- legend(visible=True) = OK sur chart principal, legend(visible=False) = obligatoire sur subcharts


NOTES
-----
- Les donnees websocket (prix, trades) sont publiques = pas besoin de cle API
- Les cles API sont necessaires uniquement pour passer des ordres
- En mode sandbox, l'argent est fictif, aucun risque
- Ne JAMAIS mettre de vraies cles API dans un fichier versionne (git)
- Le bot ferme proprement les connexions a l'arret (Ctrl+C) : websockets, fenetres, aucun orphelin
- Chaque chart tourne dans son propre process Python (multiprocessing) pour contourner ( prévoyer 700Mb de RAM par chart)
  la limitation de lightweight-charts (1 seul show_async par process)
- Communication main -> charts via mp.Queue (candles, order_lines, clear_lines, pnl)
- mp.set_start_method("fork") obligatoire (Python 3.14 utilise forkserver par defaut)
- Les montants d'ordres respectent le filtre NOTIONAL Binance (min_cost / prix x 5-10)
