# TB - Trading Bot Crypto (Binance)

Bot de trading crypto qui se connecte à Binance en temps réel via websocket.
Supporte plusieurs paires simultanément (BTC/USDT, ETH/BTC, DOT/USDT, etc.)
avec une fenêtre par paire (un process Python par chart).

Affiche un graphique candlestick live (style TradingView) avec :
- **Ordres** marqués par des lignes horizontales pointillées (vert = achat, rouge = vente)
- **EMA** en overlay sur chaque chart (période, couleur, épaisseur configurables)
- **RSI** en subchart sous le chart principal (période, couleur configurables)
- **MACD** en subchart sous le RSI (fast/slow/signal, couleurs configurables)
- **Indicateurs convergents** : 200 bougies 1m chargées au démarrage via REST Binance
  pour que EMA/RSI/MACD affichent des valeurs stables dès la première bougie live

Suivi du PNL (Profit & Loss) par paire en temps réel dans le terminal
\+ graphique PNL total en temps réel (fenêtre dédiée avec courbe).

Fermeture automatique des positions ouvertes à l'arrêt (`Ctrl+C`).


-

## Pré-requis

- Python 3.14 avec le venv `spyder-env`
- Packages : `ccxt`, `lightweight-charts`, `pandas`, `pyyaml`, `peewee`, `rich`, `aiohttp`
- GTK (`pywebview`) pour la fenêtre du graphique
- Clés API testnet Binance (https://testnet.binance.vision)

---

## Lancement

1. Activer l'environnement
2. Se placer dans le dossier :
   ```bash
   cd ~/TB
   ```
3. Lancer le bot :
   ```bash
   python main.py                 # avec graphiques
   python main.py --no-chart      # terminal seul, sans fenêtres
   ```

- Une fenêtre s'ouvre par paire (chart + RSI + MACD) + 1 fenêtre PNL
  (2 paires = 2 fenêtres chart + 1 fenêtre PNL = 3 fenêtres).
  Avec `--no-chart`, seul le terminal affiche les ordres et le PNL.
- Les bougies se construisent toutes les X secondes (réglable dans `config.yaml` > `candle_seconds`).
- Toutes les Y secondes, un ordre random (buy/sell) est passé par paire (réglable dans `main.py` > `random_orders`).
- Chaque ordre apparaît comme une ligne pointillée horizontale sur la bonne fenêtre.
- Le PNL par paire s'affiche dans le terminal après chaque ordre.
- Le PNL total s'affiche en temps réel dans la fenêtre PNL (courbe + topbar).
- `Ctrl+C` dans le terminal pour arrêter proprement.

---

## Configuration (`config.yaml`)

### Exchange

| Clé | Description |
|-----|-------------|
| `api_key` / `secret` | Clés API Binance (testnet pour le moment) |
| `sandbox: true` | `true` = testnet (argent fictif), `false` = réel (**ATTENTION**) |

### Trading

| Clé | Description |
|-----|-------------|
| `symbols` | Liste de paires avec indicateurs par paire (voir format ci-dessous) |
| `candle_seconds` | Durée d'une bougie en secondes (5 = très rapide) |
| `type` | `spot` |

**Format symbols :**
```yaml
symbols:
  - symbol: BTC/USDT
    ema: true       # afficher EMA overlay
    rsi: true       # afficher subchart RSI
    macd: true      # afficher subchart MACD
```
Ancien format aussi supporté : `- BTC/USDT` (tout activé par défaut).
`ema`/`rsi`/`macd` contrôlent l'affichage des charts, pas le calcul.

### Chart

| Clé | Description |
|-----|-------------|
| `width` / `height` | Taille de chaque fenêtre chart |

### EMA (optionnel)

```yaml
ema:
  - period: 9        # Période de l'EMA
    color: "#2962FF"  # Couleur de la courbe
    width: 1          # Épaisseur de la ligne
```
Supprimer la section `ema` = pas d'EMA affiché.

### RSI (optionnel)

```yaml
rsi:
  - period: 14        # Période du RSI
    color: "#7E57C2"   # Couleur de la courbe
    width: 1           # Épaisseur de la ligne
```
Supprimer la section `rsi` = pas de RSI affiché.
Lignes horizontales à 30 (survendu) et 70 (suracheté).

### MACD (optionnel)

```yaml
macd:
  fast_period: 12       # Période EMA rapide
  slow_period: 26       # Période EMA lente
  signal_period: 9      # Période signal
  color_macd: "#2962FF" # Couleur ligne MACD
  color_signal: "#FF6D00" # Couleur ligne Signal
  color_hist: "#26A69A"   # Couleur histogramme
```
Supprimer la section `macd` = pas de MACD affiché.

---

## Structure du projet

```
TB/
│
├── config.yaml          Config exchange, paires, timeframe, chart, indicateurs
├── requirements.txt     Dépendances Python (pip install -r requirements.txt)
├── main.py              Point d'entrée — lance tout en parallèle (asyncio)
├── README.md            Ce fichier
├── tb.db                Base SQLite (créée automatiquement au 1er lancement)
├── CLAUDE.md            Instructions pour Claude Code
│
├── bot/                 LOGIQUE TRADING
│   ├── __init__.py
│   ├── exchange.py      Wrapper REST ccxt pour Binance
│   │                      - create_order, cancel_order, fetch_balance
│   │                      - Gère sandbox (testnet) / réel
│   │                      - Partagé entre toutes les paires
│   │
│   ├── data.py          Flux de données en temps réel (1 LiveFeed par paire)
│   │                      - Websocket Binance via ccxt.pro (watch_trades)
│   │                      - Construit des bougies custom (ex: 5s) à la volée
│   │                      - Callbacks: on_update (chaque trade), on_new_candle
│   │
│   ├── orders.py        Gestionnaire d'ordres (1 OrderManager partagé)
│   │                      - buy() / sell() / cancel()
│   │                      - Sauvegarde en DB + affiche la ligne sur le bon chart
│   │                      - PNL par paire (_PairPNL) avec unités correctes
│   │                      - Montants calculés dynamiquement (filtre NOTIONAL)
│   │
│   ├── indicators.py    Classes EMA, RSI, MACD (calcul + preview live)
│   │                      - EMA : update(close) + compute_next(price)
│   │                      - RSI : update(close) + compute_next(price)
│   │                      - MACD : update(close) + compute_next(price) → (macd, signal, hist)
│   │                      - Réutilisables dans strategy.py pour les décisions
│   │
│   └── strategy.py      Classe abstraite Strategy (placeholder)
│                          - on_candle() : appelé à chaque nouvelle bougie
│                          - on_tick() : appelé à chaque update de prix
│
├── ui/                  INTERFACE GRAPHIQUE
│   ├── __init__.py
│   └── chart.py         Graphique candlestick live (multiprocessing)
│                          - lightweight-charts (TradingView) via pywebview
│                          - 1 process par paire (mp.Process + mp.Queue)
│                          - _ChartProxy : envoie les données, _chart_worker affiche
│                          - Chart principal (bougies + EMA overlay)
│                          - Subchart RSI (create_subchart, lignes 30/70)
│                          - Subchart MACD (histogramme + ligne MACD + Signal)
│                          - _PnlProxy / _pnl_chart_worker : fenêtre PNL dédiée
│                          - update_candle() : met à jour la bougie en cours
│                          - update_pnl() : envoie un point PNL au chart dédié
│                          - add_order_line() : ligne pointillée horizontale
│                          - Topbar : symbole + prix en temps réel
│
├── db/                  BASE DE DONNÉES
│   ├── __init__.py
│   └── models.py        Modèles Peewee (SQLite)
│                          - Order : symbol, side, price, amount, status, exchange_id
│                          - Trade : order, price, amount, fee
│                          - init_db() : crée les tables automatiquement
│
└── utils/               UTILITAIRES
    ├── __init__.py
    └── logger.py        Logger avec rich (couleurs, timestamps)
```

---

## Flux de données (par paire)

```
Binance Websocket (trades publics)
     │
     v
LiveFeed (data.py)             1 instance par paire
     │  Construit des bougies de N secondes
     │
     ├──>  Chart (chart.py)            Bougie + EMA + RSI + MACD (via mp.Queue)
     │
     v
Strategy (strategy.py)              Décide quand acheter/vendre
     │
     v
OrderManager (orders.py)            Passe l'ordre sur Binance
     │
     ├──>  Exchange (exchange.py)    Envoie l'ordre REST à Binance
     ├──>  DB (models.py)           Sauvegarde l'ordre en SQLite
     ├──>  Chart (chart.py)         Ligne pointillée sur la bonne fenêtre
     ├──>  Terminal                  [PNL ETH/BTC] +0.0012 BTC | Position: 0.02 ETH
     └──>  Chart PNL                Courbe PNL total temps réel (fenêtre dédiée)
```

---

## PNL (Profit & Loss)

Après chaque ordre, le terminal affiche le PNL de la paire concernée :

```
[PNL BTC/USDT] +12.35 USDT | Position: 0.0023 BTC | Trades: 8 (5B/3S)
[PNL ETH/BTC] -0.0004 BTC | Position: 0.015 ETH | Trades: 3 (2B/1S)
```

| Champ | Description |
|-------|-------------|
| **PNL** | Gain/perte total dans la devise quote (USDT, BTC, etc.) |
| **Position** | Quantité de la devise base détenue en net |
| **Trades** | Nombre total (Buys / Sells) |

**Calcul** : `PNL = (quote reçu des ventes - quote dépensé en achats) + (base détenu × prix actuel)`

---

## Prochaines étapes

- [ ] Coder une vraie stratégie dans `bot/strategy.py` (basée sur RSI/EMA/MACD)
- [ ] Remplacer les ordres random par la stratégie
- [ ] Backtesting sur données historiques
- [ ] Passer en mode réel quand c'est prêt (`sandbox: false`)

---

## Légende

- Le chart principal affiche une légende (OHLC + noms EMA) en haut à gauche
- Les subcharts (RSI, MACD) n'ont **PAS** de légende : bug JS dans lightweight-charts
  (`legendHandler` crash sur `t.seriesData.get` undefined quand legend est activée sur un subchart)
- `legend(visible=True)` = OK sur chart principal, `legend(visible=False)` = obligatoire sur subcharts

---

## Notes

- Les données websocket (prix, trades) sont **publiques** = pas besoin de clé API
- Les clés API sont nécessaires uniquement pour passer des ordres
- En mode sandbox, l'argent est fictif, aucun risque
- **Ne JAMAIS mettre de vraies clés API dans un fichier versionné (git)**
- Le bot ferme proprement les connexions à l'arrêt (`Ctrl+C`) : websockets, fenêtres, aucun orphelin
- Chaque chart tourne dans son propre process Python (multiprocessing) pour contourner
  la limitation de lightweight-charts (1 seul `show_async` par process) — prévoir ~700 Mo de RAM par chart
- Communication `main` → charts via `mp.Queue` (candles, order_lines, clear_lines, pnl)
- `mp.set_start_method("fork")` obligatoire (Python 3.14 utilise `forkserver` par défaut)
- Les montants d'ordres respectent le filtre NOTIONAL Binance (`min_cost / prix × 5-10`)
- Les timestamps affichés sur les charts sont en **UTC** (heure Binance), pas en heure locale
