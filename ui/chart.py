import multiprocessing as mp
try:
    mp.set_start_method("fork")
except RuntimeError:
    pass  # déjà défini
import os
import queue as _queue
import pandas as pd
from utils.logger import log

# ── Worker (tourne dans un process séparé par paire) ──────────────

def _chart_worker(symbol: str, config: dict, candle_sec: int,
                   ema_config: list, rsi_config: list, macd_config: dict,
                   data_q: mp.Queue, history: list = None):
    """Process séparé : un Chart unique (avec subcharts) par paire."""
    import sys, os, logging
    os.setpgrp()
    gi_path = '/usr/lib/python3.14/site-packages'
    if gi_path not in sys.path:
        sys.path.insert(0, gi_path)
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)
    os.environ['PYWEBVIEW_LOG'] = 'critical'

    import asyncio
    from lightweight_charts import Chart
    from bot.indicators import EMA, RSI, MACD

    # Calcul de la hauteur relative (Main vs Subcharts)
    # Si on a 2 indicateurs (RSI + MACD) -> Main 50%, RSI 25%, MACD 25%
    # Si on a 1 indicateur -> Main 70%, Ind 30%
    # Si 0 -> Main 100%
    
    has_rsi = bool(rsi_config)
    has_macd = bool(macd_config)
    
    inner_h = 1.0
    if has_rsi and has_macd:
        inner_h = 0.5
    elif has_rsi or has_macd:
        inner_h = 0.7

    chart = Chart(
        width=config.get("width", 800),
        height=config.get("height", 600),
        title=symbol,
        inner_height=inner_h
    )
    chart.legend(visible=True, ohlc=True, lines=True, color='#ECECEC', font_size=11)
    chart.time_scale(right_offset=5)
    chart.grid(vert_enabled=False, horz_enabled=False)
    
    chart.topbar.textbox("symbol", f"{symbol} · {candle_sec}s")
    chart.topbar.textbox("price", "")

    # --- EMA Setup ---
    ema_lines = {}
    ema_calculators = {}
    for ema in ema_config:
        period = ema["period"]
        color = ema.get("color", "#2962FF")
        width = ema.get("width", 1)
        line = chart.create_line(f"EMA {period}", color=color, width=width, price_line=False)
        ema_lines[period] = line
        ema_calculators[period] = EMA(period)

    # --- RSI Setup ---
    rsi_lines = {}
    rsi_calculators = {}
    rsi_chart = None
    if has_rsi:
        # Hauteur relative du subchart
        sub_h = 0.25 if (has_rsi and has_macd) else 0.3
        rsi_chart = chart.create_subchart(width=1.0, height=sub_h, sync=True)
        rsi_chart.legend(visible=False)
        rsi_chart.grid(vert_enabled=False, horz_enabled=False)
        
        rsi_chart.horizontal_line(70, color="#787B86", width=1, style="dashed")
        rsi_chart.horizontal_line(30, color="#787B86", width=1, style="dashed")
        
        for rsi in rsi_config:
            period = rsi["period"]
            color = rsi.get("color", "#7E57C2")
            width = rsi.get("width", 1)
            line = rsi_chart.create_line(f"RSI {period}", color=color, width=width)
            rsi_lines[period] = line
            rsi_calculators[period] = RSI(period)

    # --- MACD Setup ---
    macd_objects = {}
    macd_calculator = None
    macd_chart_obj = None
    if has_macd:
        sub_h = 0.25 if (has_rsi and has_macd) else 0.3
        macd_chart_obj = chart.create_subchart(width=1.0, height=sub_h, sync=True)
        macd_chart_obj.legend(visible=False)
        macd_chart_obj.grid(vert_enabled=False, horz_enabled=False)
        
        hist = macd_chart_obj.create_histogram("Hist", color=macd_config["color_hist"])
        macd_line = macd_chart_obj.create_line("MACD", color=macd_config["color_macd"])
        sig_line = macd_chart_obj.create_line("Signal", color=macd_config["color_signal"])
        
        macd_objects = {"hist": hist, "macd": macd_line, "signal": sig_line}
        macd_calculator = MACD(
            macd_config["fast_period"],
            macd_config["slow_period"],
            macd_config["signal_period"]
        )

    # --- Warmup ---
    if history:
        for close in history:
            # EMA
            for calc in ema_calculators.values():
                calc.update(close)
            # RSI
            for calc in rsi_calculators.values():
                calc.update(close)
            # MACD
            if macd_calculator:
                macd_calculator.update(close)

    # --- State variables ---
    current_candle_time = None
    last_processed_close = None
    initialized_chart = False
    
    async def poll():
        nonlocal initialized_chart, current_candle_time, last_processed_close
        while True:
            try:
                while True:
                    msg = data_q.get_nowait()
                    if msg[0] == "candle":
                        candle = msg[1]
                        # Clean candle dict for chart update
                        clean = {k: v for k, v in candle.items() if not k.startswith("_")}
                        
                        this_time = clean["time"]
                        close_price = candle["close"]

                        # 1. Update Main Price Chart
                        if not initialized_chart:
                            chart.set(pd.DataFrame([clean]))
                            initialized_chart = True
                        else:
                            chart.update(pd.Series(clean))
                        chart.topbar["price"].set(f"{close_price:.2f}")

                        # 2. Candle Change Detection (validation cloture)
                        if current_candle_time is not None and this_time != current_candle_time:
                            # Clôture bougie précédente -> update indicateurs (EMA, RSI, MACD)
                            for calc in ema_calculators.values():
                                calc.update(last_processed_close)
                            for calc in rsi_calculators.values():
                                calc.update(last_processed_close)
                            if macd_calculator:
                                macd_calculator.update(last_processed_close)

                        current_candle_time = this_time
                        last_processed_close = close_price

                        # 3. Live Indicator Updates (Compute Next)
                        time_idx = this_time
                        
                        # EMA
                        for period, line in ema_lines.items():
                            val = ema_calculators[period].compute_next(close_price)
                            if val is not None:
                                try:
                                    line.update(pd.Series({"time": time_idx, f"EMA {period}": val}))
                                except Exception:
                                    line.set(pd.DataFrame([{"time": time_idx, f"EMA {period}": val}]))

                        # RSI
                        for period, line in rsi_lines.items():
                            val = rsi_calculators[period].compute_next(close_price)
                            if val is not None:
                                try:
                                    line.update(pd.Series({"time": time_idx, f"RSI {period}": val}))
                                except Exception:
                                    line.set(pd.DataFrame([{"time": time_idx, f"RSI {period}": val}]))

                        # MACD
                        if macd_calculator:
                            res = macd_calculator.compute_next(close_price)
                            if res is not None:
                                m_val, s_val, h_val = res
                                try:
                                    macd_objects["macd"].update(pd.Series({"time": time_idx, "MACD": m_val}))
                                    macd_objects["signal"].update(pd.Series({"time": time_idx, "Signal": s_val}))
                                    macd_objects["hist"].update(pd.Series({"time": time_idx, "Hist": h_val}))
                                except Exception:
                                    macd_objects["macd"].set(pd.DataFrame([{"time": time_idx, "MACD": m_val}]))
                                    macd_objects["signal"].set(pd.DataFrame([{"time": time_idx, "Signal": s_val}]))
                                    macd_objects["hist"].set(pd.DataFrame([{"time": time_idx, "Hist": h_val}]))

                    elif msg[0] == "order_line":
                        _, side, price, amount = msg
                        color = "#26a69a" if side == "buy" else "#ef5350"
                        label = f"{side.upper()} {amount} @ {price:.2f}"
                        chart.horizontal_line(
                            price, color=color, width=1, style="dotted",
                            text=label, axis_label_visible=True,
                        )
                    elif msg[0] == "clear_lines":
                        chart.clear_horizontal_lines()
            except _queue.Empty:
                pass
            except Exception as e:
                # Catch JS or other errors to keep worker alive
                log.error(f"Chart worker error: {e}")
                await asyncio.sleep(1)
            
            await asyncio.sleep(0.1)

    async def main():
        await asyncio.gather(chart.show_async(), poll())

    asyncio.run(main())


# ── Worker PNL (process séparé, fenêtre dédiée) ──────────────────

def _pnl_chart_worker(config: dict, data_q: mp.Queue):
    """Process séparé : fenêtre avec courbe PNL temps réel."""
    import sys, os, logging
    os.setpgrp()
    gi_path = '/usr/lib/python3.14/site-packages'
    if gi_path not in sys.path:
        sys.path.insert(0, gi_path)
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)
    os.environ['PYWEBVIEW_LOG'] = 'critical'

    import asyncio
    from lightweight_charts import Chart

    chart = Chart(
        width=config.get("width", 800),
        height=config.get("height", 500),
        title="PNL",
    )
    chart.legend(visible=True)
    chart.time_scale(right_offset=5)
    chart.topbar.textbox("pnl_text", "PNL: 0.0000 USDT")

    line = chart.create_line("PNL", color="#2962FF", width=2, price_line=True)

    initialized = False

    async def poll():
        nonlocal initialized
        while True:
            try:
                while True:
                    msg = data_q.get_nowait()
                    if msg[0] == "pnl":
                        _, time_val, total_pnl = msg
                        point = {"time": time_val, "PNL": total_pnl}
                        if not initialized:
                            line.set(pd.DataFrame([point]))
                            initialized = True
                        else:
                            line.update(pd.Series(point))
                        sign = "+" if total_pnl >= 0 else ""
                        chart.topbar["pnl_text"].set(f"PNL: {sign}{total_pnl:.4f} USDT")
            except _queue.Empty:
                pass
            await asyncio.sleep(0.05)

    async def main():
        await asyncio.gather(chart.show_async(), poll())

    asyncio.run(main())



# ── Proxy (utilisé par le process principal) ──────────────────────

_all_proxies: list = []


class _ChartProxy:
    """Proxy vers un chart dans un process séparé."""
    def __init__(self, symbol: str, config: dict, candle_sec: int, ema_config: list,
                 rsi_config: list, macd_config: dict, history: list = None):
        self._q = mp.Queue()
        self._proc = mp.Process(
            target=_chart_worker,
            args=(symbol, config, candle_sec, ema_config, rsi_config, macd_config, self._q, history or []),
            daemon=False,
        )
        self._proc.start()
        _all_proxies.append(self)

    def send(self, *msg):
        self._q.put(msg)

    def terminate(self):
        if self._proc.is_alive():
            import signal
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class _PnlProxy:
    """Proxy vers le chart PNL dans un process séparé."""
    def __init__(self, config: dict):
        self._q = mp.Queue()
        self._proc = mp.Process(
            target=_pnl_chart_worker,
            args=(config, self._q),
            daemon=False,
        )
        self._proc.start()
        _all_proxies.append(self)

    def send(self, *msg):
        self._q.put(msg)

    def terminate(self):
        if self._proc.is_alive():
            import signal
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def create_pnl_chart(config: dict):
    """Lance un process avec la fenêtre PNL."""
    return _PnlProxy(config)


def update_candle(chart, candle: dict):
    """Envoie la bougie au process du chart."""
    chart.send("candle", candle)



def update_pnl(pnl_chart, time_val, total_pnl: float):
    """Envoie un point PNL au chart dédié."""
    pnl_chart.send("pnl", time_val, total_pnl)


def add_order_line(chart, side: str, price: float, amount: float):
    """Envoie une ligne d'ordre au process du chart."""
    chart.send("order_line", side, price, amount)
    log.info(f"Ligne {side} @ {price:.2f} ajoutée")


def remove_order_lines(chart):
    """Supprime toutes les lignes horizontales."""
    chart.send("clear_lines")
