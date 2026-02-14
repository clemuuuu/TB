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
                   quantum_config: dict, data_q: mp.Queue, history: list = None):
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
    from lightweight_charts.chart import PyWV
    from webview.errors import JavascriptException as _JsErr
    from bot.indicators import EMA, RSI, MACD, QuantumIndicator

    # Monkey-patch PyWV.loop : avaler les JavascriptException au lieu de
    # crasher Thread-2 (le sync crosshair de lwc lance "Value is null"
    # quand une série synced n'a pas encore de données).
    def _patched_loop(self):
        import webview as _wv
        while self.is_alive:
            i, arg = self.queue.get()
            if i == 'start':
                _wv.start(debug=arg, func=self.loop)
                self.is_alive = False
                self.emit_queue.put('exit')
                return
            if i == 'create_window':
                self.create_window(*arg)
                continue
            window = self.windows[i]
            if arg == 'show':
                window.show()
            elif arg == 'hide':
                window.hide()
            else:
                try:
                    if '_~_~RETURN~_~_' in arg:
                        self.return_queue.put(window.evaluate_js(arg[14:]))
                    else:
                        window.evaluate_js(arg)
                except KeyError:
                    return
                except _JsErr:
                    pass  # Avaler l'erreur JS, Thread-2 survit

    PyWV.loop = _patched_loop

    try:
        from ui.compass import CompassProxy
    except ImportError:
        CompassProxy = None

    # Calcul de la hauteur relative (Main vs Subcharts)
    # Si on a 2 indicateurs (RSI + MACD) -> Main 50%, RSI 25%, MACD 25%
    # Si on a 1 indicateur -> Main 70%, Ind 30%
    # Si 0 -> Main 100%
    
    has_rsi = bool(rsi_config)
    has_macd = bool(macd_config)
    
    # Flags locaux par paire
    show_quantum_line = False
    show_quantum_window = False
    if quantum_config:
        show_quantum_line = quantum_config.get("show_line", False)
        show_quantum_window = quantum_config.get("show_window", False)

    # Le subchart linéaire n'existe que si show_quantum_line est True
    subcharts_count = sum([has_rsi, has_macd, show_quantum_line])
    
    inner_h = 1.0
    if subcharts_count >= 2:
        if subcharts_count == 3:
            inner_h = 0.40  # 40% Main, 20% RSI, 20% MACD, 20% Quantum
        else:
            inner_h = 0.5  # 50% Main, 25% Sub1, 25% Sub2
    elif subcharts_count == 1:
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

    # --- Quantum Setup (Line Chart) ---
    quantum_objects = {}
    quantum_calculator = None
    quantum_chart_obj = None
    compass_proxy = None

    # On instancie le calculateur si on a besoin de la ligne OU de la fenêtre
    if quantum_config:
        quantum_calculator = QuantumIndicator(
            lookback=quantum_config.get("lookback", 200),
            max_n=quantum_config.get("max_n", 4),
            vol_window=quantum_config.get("vol_window", 50),
            return_period=quantum_config.get("return_period", 1),
        )

        # Initialisation Fenêtre 2D
        if show_quantum_window and CompassProxy:
            try:
                compass_proxy = CompassProxy(symbol)
            except Exception as e:
                print(f"Erreur lancement Compass 2D: {e}")

    if show_quantum_line:
        remaining = 1.0 - inner_h
        sub_h = remaining / subcharts_count if subcharts_count > 0 else 0.3

        quantum_chart_obj = chart.create_subchart(width=1.0, height=sub_h, sync=True)
        quantum_chart_obj.legend(visible=False)
        quantum_chart_obj.grid(vert_enabled=False, horz_enabled=False)

        # Lignes de référence
        quantum_chart_obj.horizontal_line(1, color="#4CAF50", width=1, style="dotted")  # n=0 fondamental
        quantum_chart_obj.horizontal_line(3, color="#FFEB3B", width=1, style="dotted")  # n=1 premier excité

        omega_line = quantum_chart_obj.create_line("Omega", color=quantum_config.get("omega_color", "#00BCD4"), width=2)
        sigma_line = quantum_chart_obj.create_line("Sigma bps", color=quantum_config.get("sigma_color", "#FF9800"), width=1)

        quantum_objects = {"omega": omega_line, "sigma": sigma_line}

    # --- Warmup ---
    # history = list of (close, volume) tuples or list of floats (legacy)
    if history:
        for item in history:
            if isinstance(item, (list, tuple)):
                close, volume = item[0], item[1]
            else:
                close, volume = item, 0.0
            # EMA
            for calc in ema_calculators.values():
                calc.update(close)
            # RSI
            for calc in rsi_calculators.values():
                calc.update(close)
            # MACD
            if macd_calculator:
                macd_calculator.update(close)
            # Quantum
            if quantum_calculator:
                quantum_calculator.update(close, volume)

    # --- State variables ---
    current_candle_time = None
    last_processed_close = None
    last_processed_volume = 0.0
    initialized_chart = False

    async def poll():
        nonlocal initialized_chart, current_candle_time, last_processed_close, last_processed_volume
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

                        # 1. Candle Change Detection (validation cloture)
                        if current_candle_time is not None and this_time != current_candle_time:
                            # Clôture bougie précédente -> update indicateurs (EMA, RSI, MACD)
                            for calc in ema_calculators.values():
                                calc.update(last_processed_close)
                            for calc in rsi_calculators.values():
                                calc.update(last_processed_close)
                            if macd_calculator:
                                macd_calculator.update(last_processed_close)
                            if quantum_calculator:
                                quantum_calculator.update(last_processed_close, last_processed_volume)
                                # Envoyer la distribution au compass (après fitting)
                                if compass_proxy and quantum_calculator.initialized:
                                    q = quantum_calculator
                                    if q.r_grid is not None and q.fitted_pdf is not None and q.empirical_hist is not None:
                                        compass_proxy.update_distribution(
                                            q.energy_level, q.omega, q.sigma, q.fit_quality,
                                            q.r_grid, q.fitted_pdf,
                                            q.empirical_hist[0], q.empirical_hist[1]
                                        )

                        current_candle_time = this_time
                        last_processed_close = close_price
                        last_processed_volume = candle.get("volume", candle.get("_vol", 0.0))

                        # 2. Indicator Updates AVANT le chart principal
                        # (le sync crosshair de lwc accède aux séries subcharts
                        #  lors du chart.update → elles doivent avoir des données)
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

                        # Quantum
                        if quantum_calculator:
                            res = quantum_calculator.compute_next(close_price)
                            if res is not None:
                                o_val, s_val, fq_val = res

                                # Update Line Chart (si activé)
                                if show_quantum_line and quantum_objects:
                                    # Sigma en basis points (×10000) pour être visible à côté d'Omega
                                    s_bps = s_val * 10000
                                    try:
                                        quantum_objects["omega"].update(pd.Series({"time": time_idx, "Omega": o_val}))
                                        quantum_objects["sigma"].update(pd.Series({"time": time_idx, "Sigma bps": s_bps}))
                                    except Exception:
                                        quantum_objects["omega"].set(pd.DataFrame([{"time": time_idx, "Omega": o_val}]))
                                        quantum_objects["sigma"].set(pd.DataFrame([{"time": time_idx, "Sigma bps": s_bps}]))

                                # Update compass tick (marqueur return courant)
                                if compass_proxy:
                                    cr = quantum_calculator.current_return(close_price)
                                    if cr is not None:
                                        compass_proxy.update_tick(cr)

                        # 3. Main Chart Update (APRÈS les subcharts pour éviter
                        #    "Value is null" dans le sync crosshair)
                        if not initialized_chart:
                            chart.set(pd.DataFrame([clean]))
                            initialized_chart = True
                        else:
                            chart.update(pd.Series(clean))
                        chart.topbar["price"].set(f"{close_price:.2f}")

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
                 rsi_config: list, macd_config: dict, quantum_config: dict, history: list = None):
        self._q = mp.Queue()
        self._proc = mp.Process(
            target=_chart_worker,
            args=(symbol, config, candle_sec, ema_config, rsi_config, macd_config, quantum_config, self._q, history or []),
            daemon=False,
        )
        self._proc.start()
        _all_proxies.append(self)

    def send(self, *msg):
        self._q.put(msg)

    def terminate(self):
        self._q.close()
        self._q.cancel_join_thread()
        if self._proc.is_alive():
            import signal
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._proc.join(timeout=0.1)


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
        self._q.close()
        self._q.cancel_join_thread()
        if self._proc.is_alive():
            import signal
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self._proc.join(timeout=0.1)


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
