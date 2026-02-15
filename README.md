# TB - Trading Bot Crypto (Binance)

Bot de trading crypto Binance Spot avec graphiques candlestick live, indicateurs techniques et indicateurs quantiques issus de la recherche académique.

Supporte plusieurs paires simultanément (BTC/USDT, ETH/BTC, DOT/USDT, etc.)
avec une fenêtre par paire (un process Python par chart).

### Indicateurs techniques
- **EMA** en overlay sur chaque chart (période, couleur, épaisseur configurables)
- **RSI** en subchart sous le chart principal (période, couleur configurables)
- **MACD** en subchart sous le RSI (fast/slow/signal, couleurs configurables)

### Indicateurs quantiques (BETA) — Li Lin 2024 ([arXiv:2401.05823](https://arxiv.org/abs/2401.05823))

Le modèle fitte la distribution des log-returns sur les fonctions propres de l'oscillateur harmonique quantique (Hermite-Gauss). Le niveau d'énergie **Ω = 2n+1** caractérise l'état du marché :
- **Ω = 1** (n=0) : distribution gaussienne → marché calme
- **Ω = 3** (n=1) : distribution bimodale → 2 régimes de prix
- **Ω ≥ 5** (n≥2) : distribution multimodale → marché volatile

3 modes d'affichage (activables indépendamment par paire) :

| Mode | Flag config | Description |
|------|-------------|-------------|
| **Subchart linéaire** (BETA) | `quantum_line` | Lignes Ω (cyan) + σ en basis points (orange) avec références à n=0 et n=1 |
| **Distribution 2D** (BETA) | `quantum_window` | Histogramme empirique + courbe PDF fittée (Hermite-Gauss) + marqueur du return courant |
| **Lin Compass ATI** (BETA) | `lin_compass` | Compass Active Trading Intention — cercle unitaire avec vecteur e^{iθ(r)} indiquant le sentiment de marché |

Le **Lin Compass (ATI)** extrait la phase θ(r) via la transformée de Hilbert de l'eigenfonction φ_n, et affiche un vecteur sur le plan complexe avec 4 quadrants (fidèle à la Figure 2 du paper) :
- **+Re** : Adding Position (accumulation)
- **-Re** : Trimming Position (allègement)
- **-Im** : Bullish
- **+Im** : Bearish

La distribution et le compass partagent la même fenêtre (layout flex côte à côte) pour économiser la RAM.

> **BETA** : L'indicateur quantique (distribution + compass ATI) est fonctionnel mais en phase de test. Les paramètres et l'interprétation des signaux sont encore en cours d'affinage.

### Autres features
- **Ordres live** : exécution sandbox (testnet) ou réel, avec lignes pointillées sur le chart
- **PNL temps réel** : tracking par paire dans le terminal + graphique PNL total (fenêtre dédiée)
- **Bougies custom** : construites à la volée depuis les trades websocket (timeframe libre)
- **Indicateurs convergents** : 200 bougies 1m chargées au démarrage pour warmup
- Fermeture automatique des positions ouvertes à l'arrêt (`Ctrl+C`)


-----

## Pré-requis

- **Python 3.14+**
- **Packages** : installés via `pip install -r requirements.txt`
- **GTK + WebKitGTK** (pour les fenêtres graphiques via `pywebview`)
  - **Linux** : installer `gtk3` et `webkit2gtk` via votre gestionnaire de paquets
    (ex: `sudo pacman -S webkit2gtk` sur Arch, `sudo apt install gir1.2-webkit2-4.1` sur Debian/Ubuntu)
  - **Windows** : pywebview utilise Edge/Chromium par défaut, pas besoin de GTK.
    Installer `.NET Framework 4.6.2+` si nécessaire
  - **macOS** : pywebview utilise WebKit nativement, rien à installer
- **Clés API Binance testnet** : https://testnet.binance.vision (pour les ordres sandbox)

---

## Installation

```bash
git clone https://github.com/clemuuuu/TB.git
cd TB
python -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

Editer `config.yaml` avec vos clés API Binance testnet.

---

## Lancement

```bash
python main.py                 # avec graphiques
python main.py --no-chart      # terminal seul, sans fenêtres
```

- Une fenêtre s'ouvre par paire (chart + subcharts) + 1 fenêtre PNL
  \+ optionnellement 1 fenêtre Quantum par paire (distribution + compass ATI côte à côte).
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
    ema: true            # afficher EMA overlay
    rsi: true            # afficher subchart RSI
    macd: true           # afficher subchart MACD
    quantum_line: true   # afficher subchart Omega/Sigma (BETA)
    quantum_window: true # afficher fenêtre distribution (BETA)
    lin_compass: true    # afficher compass ATI Li Lin 2024 (BETA)
```
Ancien format aussi supporté : `- BTC/USDT` (tout activé par défaut sauf quantum).
Les flags contrôlent l'affichage des charts, pas le calcul.
La fenêtre Quantum s'ouvre si `quantum_window` ou `lin_compass` est `true` (les deux panneaux partagent la même fenêtre).

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

### Quantum Indicator (optionnel, BETA)

```yaml
quantum:
  lookback: 200           # Nombre de returns pour le fitting
  return_period: 60       # Écart entre 2 prix pour calculer un return (en BOUGIES)
                          #   return_period=60 + candle_seconds=1  → returns sur 1 minute
                          #   return_period=60 + candle_seconds=60 → returns sur 1 heure
  max_n: 4                # Max eigenstate (n=0..4, Ω jusqu'à 9)
  vol_window: 50          # Fenêtre pour le ratio de volume
  omega_color: '#00BCD4'  # Cyan  ligne Omega sur le subchart
  sigma_color: '#FF9800'  # Orange  ligne Sigma sur le subchart
```
Supprimer la section `quantum` = pas de Quantum affiché.

> Cet indicateur implémente le modèle complet de Li Lin (2024) — *"Quantum Probability
> Theoretic Asset Return Modeling: A Novel Schrödinger-Like Trading Equation and Multimodal
> Distribution"* ([arXiv:2401.05823](https://arxiv.org/abs/2401.05823)).
>
> **Partie 1 — Distribution (|Ψ|²)** : fitte la distribution des log-returns sur les
> fonctions propres de Hermite-Gauss (oscillateur harmonique quantique). Le niveau d'énergie
> Ω = 2n+1 caractérise l'état du marché : Ω=1 (gaussien, calme), Ω=3 (bimodal, 2 régimes),
> Ω≥5 (multimodal, volatile).
>
> **Partie 2 — Phase (ATI Compass)** : la fonction d'onde complète est Ψ(r) = φ(r)·e^{iθ(r)}.
> La partie 1 donne le module |Ψ|² (distribution). Le compass ATI extrait la phase θ(r) via la
> transformée de Hilbert du signal analytique de l'eigenfonction φ_n, puis affiche le vecteur
> e^{iθ} sur un plan complexe à 4 quadrants (Figure 2 du paper) :
> Adding/Trimming × Bullish/Bearish.

---

## Structure du projet

```
TB/
│
├── config.yaml          Config exchange, paires, timeframe, chart, indicateurs
├── requirements.txt     Dépendances Python (pip install -r requirements.txt)
├── main.py              Point d'entrée lance tout en parallèle (asyncio)
├── README.md            Ce fichier
├── tb.db                Base SQLite (créée automatiquement au 1er lancement)
├── ARCHITECTURE.md      Architecture et documentation technique
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
│   ├── indicators.py    Classes EMA, RSI, MACD, QuantumIndicator
│   │                      - EMA : update(close) + compute_next(price)
│   │                      - RSI : update(close) + compute_next(price)
│   │                      - MACD : update(close) + compute_next(price) → (macd, signal, hist)
│   │                      - QuantumIndicator (BETA) : update(close, volume) + compute_next(price)
│   │                        + compute_phase(r) pour le Lin Compass ATI
│   │                      - Réutilisables dans strategy.py pour les décisions
│   │
│   └── strategy.py      Classe abstraite Strategy (placeholder)
│                          - on_candle() : appelé à chaque nouvelle bougie
│                          - on_tick() : appelé à chaque update de prix
│
├── ui/                  INTERFACE GRAPHIQUE
│   ├── __init__.py
│   ├── compass.py       Fenêtre Quantum (BETA) (distribution + Lin Compass ATI)
│   │                      - Layout flex : distribution (gauche) + compass ATI (droite)
│   │                      - Panneaux conditionnels via show_dist / show_compass
│   │                      - Process séparé par paire (pywebview + canvas HTML)
│   └── chart.py         Graphique candlestick live (multiprocessing)
│                          - lightweight-charts (TradingView) via pywebview
│                          - 1 process par paire (mp.Process + mp.Queue)
│                          - _ChartProxy : envoie les données, _chart_worker affiche
│                          - Chart principal (bougies + EMA overlay)
│                          - Subchart RSI (create_subchart, lignes 30/70)
│                          - Subchart MACD (histogramme + ligne MACD + Signal)
│                          - Subchart Quantum (Omega + Sigma bps) (BETA)
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
     ├──>  Chart (chart.py)            Bougie + EMA + RSI + MACD + Quantum (via mp.Queue)
     │       └──> Compass (compass.py)   Distribution + ATI Compass (sous-process)
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

- [ ] Coder une vraie stratégie dans `bot/strategy.py` (basée sur RSI/EMA/MACD/Quantum)
- [ ] Remplacer les ordres random par la stratégie
- [ ] Affiner les paramètres du Quantum Indicator
- [ ] Backtesting sur données historiques
- [ ] Passer en mode réel quand c'est prêt (`sandbox: false`)

---

## Légende

- Le chart principal affiche une légende (OHLC + noms EMA) en haut à gauche
- Les subcharts (RSI, MACD) n'ont **PAS** de légende : bug JS dans lightweight-charts, ne pas activer
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
  la limitation de lightweight-charts (1 seul `show_async` par process)  prévoir ~700 Mo de RAM par chart
- Communication `main` → charts via `mp.Queue` (candles, order_lines, clear_lines, pnl)
- `mp.set_start_method("fork")` obligatoire (Python 3.14 utilise `forkserver` par défaut)
- Les montants d'ordres respectent le filtre NOTIONAL Binance (`min_cost / prix × 5-10`)
- Les timestamps affichés sur les charts sont en **UTC** (heure Binance), pas en heure locale
