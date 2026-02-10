import multiprocessing as mp
import time
import json
import webview
import numpy as np

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Quantum Distribution - {symbol}</title>
    <style>
        body {{ margin: 0; padding: 0; background-color: #111; overflow: hidden; font-family: 'Courier New', monospace; }}
        canvas {{ display: block; }}
        #overlay {{ position: absolute; top: 10px; left: 10px; color: #0f0; font-size: 13px; pointer-events: none; line-height: 1.6; }}
        #title {{ position: absolute; top: 10px; right: 10px; color: #888; font-size: 11px; pointer-events: none; }}
    </style>
</head>
<body>
    <div id="overlay">Waiting for data...</div>
    <div id="title">{symbol}</div>
    <canvas id="chart"></canvas>
    <script>
        const canvas = document.getElementById('chart');
        const ctx = canvas.getContext('2d');
        const overlayDiv = document.getElementById('overlay');
        const titleDiv = document.getElementById('title');

        let width, height;
        const MARGIN = {{ top: 40, right: 20, bottom: 40, left: 60 }};

        // State
        let histCounts = null;
        let histEdges = null;
        let rGrid = null;
        let fittedPdf = null;
        let currentReturn = 0;
        let n = 0, omega = 1, sigma = 0, fitQuality = 0;
        let hasData = false;

        function resize() {{
            width = window.innerWidth;
            height = window.innerHeight;
            canvas.width = width;
            canvas.height = height;
            if (hasData) draw();
        }}
        window.addEventListener('resize', resize);
        resize();

        function mapX(val, xMin, xMax) {{
            return MARGIN.left + (val - xMin) / (xMax - xMin) * (width - MARGIN.left - MARGIN.right);
        }}
        function mapY(val, yMax) {{
            const plotH = height - MARGIN.top - MARGIN.bottom;
            return MARGIN.top + plotH * (1 - val / yMax);
        }}

        function draw() {{
            ctx.clearRect(0, 0, width, height);
            ctx.fillStyle = '#111';
            ctx.fillRect(0, 0, width, height);

            if (!hasData || !histCounts || !rGrid) return;

            // Compute ranges
            const xMin = rGrid[0];
            const xMax = rGrid[rGrid.length - 1];
            let yMax = 0;
            for (let i = 0; i < histCounts.length; i++) {{
                if (histCounts[i] > yMax) yMax = histCounts[i];
            }}
            for (let i = 0; i < fittedPdf.length; i++) {{
                if (fittedPdf[i] > yMax) yMax = fittedPdf[i];
            }}
            yMax *= 1.15;
            if (yMax < 1e-10) yMax = 1;

            const plotH = height - MARGIN.top - MARGIN.bottom;

            // Axes
            ctx.strokeStyle = '#444';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.moveTo(MARGIN.left, MARGIN.top);
            ctx.lineTo(MARGIN.left, height - MARGIN.bottom);
            ctx.lineTo(width - MARGIN.right, height - MARGIN.bottom);
            ctx.stroke();

            // Zero line (r=0)
            const zeroX = mapX(0, xMin, xMax);
            if (zeroX > MARGIN.left && zeroX < width - MARGIN.right) {{
                ctx.strokeStyle = '#333';
                ctx.setLineDash([3, 3]);
                ctx.beginPath();
                ctx.moveTo(zeroX, MARGIN.top);
                ctx.lineTo(zeroX, height - MARGIN.bottom);
                ctx.stroke();
                ctx.setLineDash([]);
            }}

            // X axis labels
            ctx.fillStyle = '#888';
            ctx.font = '10px Courier New';
            ctx.textAlign = 'center';
            const nTicks = 5;
            for (let i = 0; i <= nTicks; i++) {{
                const val = xMin + (xMax - xMin) * i / nTicks;
                const x = mapX(val, xMin, xMax);
                ctx.fillText(val.toExponential(1), x, height - MARGIN.bottom + 15);
                ctx.strokeStyle = '#222';
                ctx.beginPath();
                ctx.moveTo(x, MARGIN.top);
                ctx.lineTo(x, height - MARGIN.bottom);
                ctx.stroke();
            }}

            // Histogram bars
            ctx.fillStyle = 'rgba(100, 100, 100, 0.5)';
            ctx.strokeStyle = 'rgba(150, 150, 150, 0.3)';
            for (let i = 0; i < histCounts.length; i++) {{
                const x1 = mapX(histEdges[i], xMin, xMax);
                const x2 = mapX(histEdges[i + 1], xMin, xMax);
                const y = mapY(histCounts[i], yMax);
                const barH = (height - MARGIN.bottom) - y;
                ctx.fillRect(x1, y, x2 - x1, barH);
                ctx.strokeRect(x1, y, x2 - x1, barH);
            }}

            // Fitted PDF curve
            const colors = ['#00FF00', '#00BFFF', '#FFD700', '#FF6347', '#FF00FF'];
            const curveColor = colors[Math.min(n, colors.length - 1)];
            ctx.strokeStyle = curveColor;
            ctx.lineWidth = 2.5;
            ctx.shadowBlur = 8;
            ctx.shadowColor = curveColor;
            ctx.beginPath();
            let started = false;
            for (let i = 0; i < rGrid.length; i++) {{
                const x = mapX(rGrid[i], xMin, xMax);
                const y = mapY(fittedPdf[i], yMax);
                if (!started) {{ ctx.moveTo(x, y); started = true; }}
                else ctx.lineTo(x, y);
            }}
            ctx.stroke();
            ctx.shadowBlur = 0;

            // Current return marker (vertical red line)
            if (currentReturn >= xMin && currentReturn <= xMax) {{
                const crX = mapX(currentReturn, xMin, xMax);
                ctx.strokeStyle = '#FF0000';
                ctx.lineWidth = 2;
                ctx.setLineDash([5, 3]);
                ctx.beginPath();
                ctx.moveTo(crX, MARGIN.top);
                ctx.lineTo(crX, height - MARGIN.bottom);
                ctx.stroke();
                ctx.setLineDash([]);

                // Label
                ctx.fillStyle = '#FF0000';
                ctx.font = '10px Courier New';
                ctx.textAlign = 'center';
                ctx.fillText('r=' + currentReturn.toExponential(2), crX, MARGIN.top - 5);
            }}

            // Overlay text
            const stateNames = ['Calm (Gaussian)', 'Active (Bimodal)', 'Volatile', 'Very Volatile', 'Extreme'];
            const stateName = stateNames[Math.min(n, stateNames.length - 1)];
            overlayDiv.innerHTML =
                `n=<b>${{n}}</b>  \u03A9=<b>${{omega}}</b>  \u03C3=${{sigma.toExponential(3)}}` +
                `<br>fit=${{fitQuality.toFixed(2)}}  [${{stateName}}]`;
        }}

        // Called from Python: update distribution (each candle close)
        window.update_distribution = function(data) {{
            n = data.n;
            omega = data.omega;
            sigma = data.sigma;
            fitQuality = data.fit_quality;
            rGrid = data.r_grid;
            fittedPdf = data.fitted_pdf;
            histCounts = data.hist_counts;
            histEdges = data.hist_edges;
            hasData = true;
            draw();
        }};

        // Called from Python: update current return marker (each tick)
        window.update_tick = function(cr) {{
            currentReturn = cr;
            if (hasData) draw();
        }};

        draw();
    </script>
</body>
</html>
"""

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window


def _compass_process(symbol: str, data_queue: mp.Queue):
    """Process séparé : fenêtre distribution quantique.

    Pas de os.setpgrp() — le compass est lancé depuis _chart_worker
    qui a déjà son propre group. Tué automatiquement par killpg.
    """
    import logging
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)

    api = Api()
    html_content = HTML_TEMPLATE.format(symbol=symbol)

    window = webview.create_window(
        f"Quantum Distribution - {symbol}",
        html=html_content,
        width=500,
        height=400,
        resizable=True,
        on_top=True,
    )
    api.set_window(window)

    def update_loop():
        while True:
            try:
                latest_tick = None
                latest_dist = None
                while not data_queue.empty():
                    msg = data_queue.get_nowait()
                    if msg[0] == "tick":
                        latest_tick = msg
                    elif msg[0] == "dist":
                        latest_dist = msg

                if latest_dist:
                    _, n, omega, sigma, fit_quality, r_grid, fitted_pdf, hist_counts, hist_edges = latest_dist
                    data = json.dumps({
                        "n": n, "omega": omega, "sigma": sigma, "fit_quality": fit_quality,
                        "r_grid": r_grid, "fitted_pdf": fitted_pdf,
                        "hist_counts": hist_counts, "hist_edges": hist_edges,
                    })
                    try:
                        window.evaluate_js(f"window.update_distribution({data})")
                    except Exception:
                        pass

                if latest_tick:
                    _, cr = latest_tick
                    try:
                        window.evaluate_js(f"window.update_tick({cr})")
                    except Exception:
                        pass

            except Exception:
                pass
            time.sleep(0.1)

    import threading
    t = threading.Thread(target=update_loop, daemon=True)
    t.start()

    webview.start(debug=False)


class CompassProxy:
    """Proxy pour lancer la fenêtre depuis le chart worker."""
    def __init__(self, symbol: str):
        self.queue = mp.Queue()
        self.process = mp.Process(target=_compass_process, args=(symbol, self.queue), daemon=False)
        self.process.start()

    def update_tick(self, current_return: float):
        """Met à jour le marqueur de return courant (chaque tick)."""
        if self.process.is_alive():
            self.queue.put(("tick", current_return))

    def update_distribution(self, n, omega, sigma, fit_quality,
                            r_grid, fitted_pdf, hist_counts, hist_edges):
        """Met à jour la distribution complète (chaque bougie)."""
        if self.process.is_alive():
            self.queue.put(("dist", n, omega, sigma, fit_quality,
                            r_grid.tolist(), fitted_pdf.tolist(),
                            hist_counts.tolist(), hist_edges.tolist()))

    def stop(self):
        self.queue.close()
        self.queue.cancel_join_thread()
        if self.process.is_alive() and self.process.pid is not None:
            import os, signal
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.join(timeout=0.1)
