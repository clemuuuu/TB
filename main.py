import sys
import argparse
import asyncio
import random
import yaml
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bot.exchange import Exchange
from bot.data import LiveFeed
from bot.orders import OrderManager
from db.models import init_db
from utils.logger import log


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _random_amount(exchange, symbol, price):
    """Génère un montant random respectant le minimum notional de la paire."""
    market = exchange.client.markets.get(symbol, {})
    min_cost = market.get("limits", {}).get("cost", {}).get("min", 5.0)
    min_amount = market.get("limits", {}).get("amount", {}).get("min", 0.001)
    # Montant minimum pour respecter le notional
    min_from_cost = min_cost / price if price > 0 else min_amount
    floor = max(min_amount, min_from_cost)
    # 5x à 10x le minimum (Binance calcule le notional sur un prix moyen 5min)
    return round(random.uniform(floor * 5, floor * 10), 6)


async def random_orders(order_manager, exchange, symbol, feed):
    """Toutes les 5 secondes, passe un vrai ordre sandbox random."""
    await asyncio.sleep(10)
    while True:
        if feed._current:
            side = random.choice(["buy", "sell"])
            price = feed._current["close"]
            amount = _random_amount(exchange, symbol, price)
            try:
                if side == "buy":
                    order_manager.buy(symbol, amount)
                else:
                    order_manager.sell(symbol, amount)
            except Exception as e:
                log.error(f"[{symbol}] Ordre {side} échoué: {e}")
        await asyncio.sleep(5)


async def main(use_chart: bool = True):
    config = load_config()
    log.info("Démarrage TB (sandbox)...")

    # Init DB
    init_db(str(Path(__file__).parent / "tb.db"))

    # Parser les symboles (supporte ancien format string et nouveau format dict)
    raw_symbols = config["trading"]["symbols"]
    symbols = []
    symbol_flags = {}  # {symbol: {"ema": bool, "rsi": bool, "macd": bool}}
    for entry in raw_symbols:
        if isinstance(entry, str):
            symbols.append(entry)
            symbol_flags[entry] = {"ema": True, "rsi": True, "macd": True}
        else:
            sym = entry["symbol"]
            symbols.append(sym)
            symbol_flags[sym] = {
                "ema": entry.get("ema", True),
                "rsi": entry.get("rsi", True),
                "macd": entry.get("macd", True),
                "quantum_line": entry.get("quantum_line", False),
                "quantum_window": entry.get("quantum_window", False),
                "lin_compass": entry.get("lin_compass", False),
            }
    candle_sec = config["trading"]["candle_seconds"]

    # Exchange REST (partagé entre toutes les paires)
    exchange = Exchange(config["exchange"])
    exchange.client.load_markets()

    # Charts (1 fenêtre par paire + 1 fenêtre PNL) ou mode terminal seul
    charts = {}
    pnl_chart = None

    if use_chart:
        from ui.chart import (_ChartProxy, update_candle, create_pnl_chart,
                              update_pnl, _all_proxies)
        ema_config = config.get("ema", [])
        rsi_config = config.get("rsi", [])
        macd_config = config.get("macd")
        quantum_config = config.get("quantum")

        # Charger l'historique pour warmup indicateurs (200 bougies 1m, données publiques)
        historical_data = {}
        if ema_config or rsi_config or macd_config or quantum_config:
            import ccxt as _ccxt
            _hist = _ccxt.binance()
            for sym in symbols:
                try:
                    ohlcv = _hist.fetch_ohlcv(sym, '1m', limit=200)
                    historical_data[sym] = [(c[4], c[5]) for c in ohlcv]  # (close, volume)
                    log.info(f"[{sym}] {len(ohlcv)} bougies 1m chargées (warmup indicateurs)")
                except Exception as e:
                    log.warning(f"[{sym}] Historique indisponible: {e}")
                    historical_data[sym] = []

        # Créer les charts par paire (EMA/RSI/MACD conditionnés par symbol_flags)
        for sym in symbols:
            flags = symbol_flags[sym]
            
            sym_ema = ema_config if flags["ema"] else []
            sym_rsi = rsi_config if flags["rsi"] else []
            sym_macd = macd_config if flags["macd"] else None
            
            # On combine la config quantum globale avec les flags locaux
            sym_quantum = None
            if quantum_config and (flags["quantum_line"] or flags["quantum_window"] or flags.get("lin_compass")):
                sym_quantum = quantum_config.copy()
                sym_quantum["show_line"] = flags["quantum_line"]
                sym_quantum["show_window"] = flags["quantum_window"]
                sym_quantum["show_lin_compass"] = flags.get("lin_compass", False)

            history = historical_data.get(sym, [])
            charts[sym] = _ChartProxy(sym, config["chart"], candle_sec, 
                                      sym_ema, sym_rsi, sym_macd, sym_quantum, history)
            
        pnl_chart = create_pnl_chart(config["chart"])

    # OrderManager unique avec tous les charts
    om = OrderManager(exchange, charts=charts)

    # Prix courants par paire (pour calcul PNL temps réel)
    current_prices = {}

    # Un LiveFeed par symbole
    feeds = {}
    tasks = []

    for symbol in symbols:
        feed = LiveFeed(config["exchange"], symbol, candle_sec)
        
        if use_chart and symbol in charts:
            chart = charts[symbol]
            def _on_update(candle, c=chart, s=symbol):
                update_candle(c, candle)
                current_prices[s] = candle["close"]
                if pnl_chart:
                    now = datetime.now(timezone.utc).replace(microsecond=0)
                    total = om.get_total_pnl(current_prices)
                    update_pnl(pnl_chart, now, total)
            feed.on_update = _on_update
            
        feeds[symbol] = feed
        tasks.append(feed.stream())


    # Ordres random par paire
    for symbol in symbols:
        tasks.append(random_orders(om, exchange, symbol, feeds[symbol]))

    mode = "charts" if use_chart else "terminal seul"
    for sym in symbols:
        flags = symbol_flags[sym]
        indicators = []
        if flags["ema"]: indicators.append("EMA")
        if flags["rsi"]: indicators.append("RSI")
        if flags["macd"]: indicators.append("MACD")
        if flags.get("quantum_line"): indicators.append("Quantum(Chart)")
        if flags.get("quantum_window"): indicators.append("Quantum(2D)")
        if flags.get("lin_compass"): indicators.append("Lin Compass")
        ind_str = "+".join(indicators) if indicators else "aucun indicateur"
        log.info(f"  {sym} — {ind_str}")
    log.info(f"Bougies {candle_sec}s ({mode})")
    log.info("Ordres sandbox random toutes les 5s par paire")

    # Supprimer le bruit aiohttp/ccxt (CancelledError dans les callbacks)
    loop = asyncio.get_event_loop()

    def _quiet_handler(l, ctx):
        if isinstance(ctx.get("exception"), (asyncio.CancelledError, KeyboardInterrupt)):
            return
        l.default_exception_handler(ctx)

    loop.set_exception_handler(_quiet_handler)

    running = [asyncio.create_task(t) for t in tasks]
    try:
        await asyncio.gather(*running)
    except (asyncio.CancelledError, KeyboardInterrupt):
        for t in running:
            t.cancel()
        await asyncio.gather(*running, return_exceptions=True)
    finally:
        # Fermer toutes les positions avant de couper
        log.info("Fermeture des positions ouvertes...")
        om.close_all_positions()
        for feed in feeds.values():
            try:
                await feed.exchange.close()
            except Exception:
                pass
        exchange.close()
        if use_chart:
            from ui.chart import _all_proxies
            for proxy in _all_proxies:
                proxy.terminate()
        log.info("TB arrêté.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TB - Trading Bot Crypto")
    parser.add_argument("--no-chart", action="store_true", help="Lancer sans graphiques (terminal seul)")
    args = parser.parse_args()
    try:
        asyncio.run(main(use_chart=not args.no_chart))
    except KeyboardInterrupt:
        pass
