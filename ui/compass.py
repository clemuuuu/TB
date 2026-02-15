import multiprocessing as mp
import time
import json
import webview
import numpy as np

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Quantum - {symbol}</title>
    <style>
        body {{ margin: 0; padding: 0; background-color: #111; overflow: hidden; font-family: 'Courier New', monospace; }}
        #container {{ display: flex; width: 100vw; height: 100vh; }}
        #dist-panel {{ flex: {dist_flex}; display: {dist_display}; position: relative; }}
        #compass-panel {{ flex: {compass_flex}; display: {compass_display}; position: relative; border-left: {border}; }}
        canvas {{ display: block; }}
        #overlay {{ position: absolute; top: 10px; left: 10px; color: #0f0; font-size: 13px; pointer-events: none; line-height: 1.6; z-index: 10; }}
        #title {{ position: absolute; top: 10px; right: 10px; color: #888; font-size: 11px; pointer-events: none; z-index: 10; }}
    </style>
</head>
<body>
    <div id="container">
        <div id="dist-panel">
            <div id="overlay">Waiting for data...</div>
            <div id="title">{symbol}</div>
            <canvas id="chart"></canvas>
        </div>
        <div id="compass-panel">
            <canvas id="compass"></canvas>
        </div>
    </div>
    <script>
        const SHOW_DIST = {show_dist_js};
        const SHOW_COMPASS = {show_compass_js};

        // ═══════════════════════════════════════════════════
        // Distribution (left panel)
        // ═══════════════════════════════════════════════════
        const distCanvas = document.getElementById('chart');
        const distCtx = distCanvas.getContext('2d');
        const overlayDiv = document.getElementById('overlay');
        const distPanel = document.getElementById('dist-panel');

        let dw, dh;
        const MARGIN = {{ top: 40, right: 20, bottom: 40, left: 60 }};

        let histCounts = null, histEdges = null;
        let rGrid = null, fittedPdf = null;
        let currentReturn = 0;
        let n = 0, omega = 1, sigma = 0, fitQuality = 0;
        let hasData = false;

        function resizeDist() {{
            if (!SHOW_DIST) return;
            dw = distPanel.clientWidth;
            dh = distPanel.clientHeight;
            distCanvas.width = dw;
            distCanvas.height = dh;
            if (hasData) drawDist();
        }}

        function mapX(val, xMin, xMax) {{
            return MARGIN.left + (val - xMin) / (xMax - xMin) * (dw - MARGIN.left - MARGIN.right);
        }}
        function mapY(val, yMax) {{
            const plotH = dh - MARGIN.top - MARGIN.bottom;
            return MARGIN.top + plotH * (1 - val / yMax);
        }}

        function drawDist() {{
            if (!SHOW_DIST) return;
            distCtx.clearRect(0, 0, dw, dh);
            distCtx.fillStyle = '#111';
            distCtx.fillRect(0, 0, dw, dh);

            if (!hasData || !histCounts || !rGrid) return;

            const xMin = rGrid[0];
            const xMax = rGrid[rGrid.length - 1];
            let yMax = 0;
            for (let i = 0; i < histCounts.length; i++)
                if (histCounts[i] > yMax) yMax = histCounts[i];
            for (let i = 0; i < fittedPdf.length; i++)
                if (fittedPdf[i] > yMax) yMax = fittedPdf[i];
            yMax *= 1.15;
            if (yMax < 1e-10) yMax = 1;

            // Axes
            distCtx.strokeStyle = '#444';
            distCtx.lineWidth = 1;
            distCtx.beginPath();
            distCtx.moveTo(MARGIN.left, MARGIN.top);
            distCtx.lineTo(MARGIN.left, dh - MARGIN.bottom);
            distCtx.lineTo(dw - MARGIN.right, dh - MARGIN.bottom);
            distCtx.stroke();

            // Zero line
            const zeroX = mapX(0, xMin, xMax);
            if (zeroX > MARGIN.left && zeroX < dw - MARGIN.right) {{
                distCtx.strokeStyle = '#333';
                distCtx.setLineDash([3, 3]);
                distCtx.beginPath();
                distCtx.moveTo(zeroX, MARGIN.top);
                distCtx.lineTo(zeroX, dh - MARGIN.bottom);
                distCtx.stroke();
                distCtx.setLineDash([]);
            }}

            // X labels
            distCtx.fillStyle = '#888';
            distCtx.font = '10px Courier New';
            distCtx.textAlign = 'center';
            for (let i = 0; i <= 5; i++) {{
                const val = xMin + (xMax - xMin) * i / 5;
                const x = mapX(val, xMin, xMax);
                distCtx.fillText(val.toExponential(1), x, dh - MARGIN.bottom + 15);
                distCtx.strokeStyle = '#222';
                distCtx.beginPath();
                distCtx.moveTo(x, MARGIN.top);
                distCtx.lineTo(x, dh - MARGIN.bottom);
                distCtx.stroke();
            }}

            // Histogram bars
            distCtx.fillStyle = 'rgba(100,100,100,0.5)';
            distCtx.strokeStyle = 'rgba(150,150,150,0.3)';
            for (let i = 0; i < histCounts.length; i++) {{
                const x1 = mapX(histEdges[i], xMin, xMax);
                const x2 = mapX(histEdges[i+1], xMin, xMax);
                const y = mapY(histCounts[i], yMax);
                distCtx.fillRect(x1, y, x2-x1, (dh-MARGIN.bottom)-y);
                distCtx.strokeRect(x1, y, x2-x1, (dh-MARGIN.bottom)-y);
            }}

            // Fitted PDF
            const colors = ['#00FF00','#00BFFF','#FFD700','#FF6347','#FF00FF'];
            const curveColor = colors[Math.min(n, colors.length-1)];
            distCtx.strokeStyle = curveColor;
            distCtx.lineWidth = 2.5;
            distCtx.shadowBlur = 8;
            distCtx.shadowColor = curveColor;
            distCtx.beginPath();
            let started = false;
            for (let i = 0; i < rGrid.length; i++) {{
                const x = mapX(rGrid[i], xMin, xMax);
                const y = mapY(fittedPdf[i], yMax);
                if (!started) {{ distCtx.moveTo(x, y); started = true; }}
                else distCtx.lineTo(x, y);
            }}
            distCtx.stroke();
            distCtx.shadowBlur = 0;

            // Current return marker
            if (currentReturn >= xMin && currentReturn <= xMax) {{
                const crX = mapX(currentReturn, xMin, xMax);
                distCtx.strokeStyle = '#FF0000';
                distCtx.lineWidth = 2;
                distCtx.setLineDash([5, 3]);
                distCtx.beginPath();
                distCtx.moveTo(crX, MARGIN.top);
                distCtx.lineTo(crX, dh - MARGIN.bottom);
                distCtx.stroke();
                distCtx.setLineDash([]);
                distCtx.fillStyle = '#FF0000';
                distCtx.font = '10px Courier New';
                distCtx.textAlign = 'center';
                distCtx.fillText('r='+currentReturn.toExponential(2), crX, MARGIN.top - 5);
            }}

            // Overlay text
            const sn = ['Calm (Gaussian)','Active (Bimodal)','Volatile','Very Volatile','Extreme'];
            overlayDiv.innerHTML =
                'n=<b>'+n+'</b>  \\u03A9=<b>'+omega+'</b>  \\u03C3='+sigma.toExponential(3)+
                '<br>fit='+fitQuality.toFixed(2)+'  ['+sn[Math.min(n,sn.length-1)]+']';
        }}

        // ═══════════════════════════════════════════════════
        // Lin Compass ATI (right panel — Li Lin 2024 Fig. 2)
        // ═══════════════════════════════════════════════════
        const compCanvas = document.getElementById('compass');
        const compCtx = compCanvas.getContext('2d');
        const compPanel = document.getElementById('compass-panel');

        let cw, ch;
        let theta = 0;
        let hasPhase = false;

        function resizeComp() {{
            if (!SHOW_COMPASS) return;
            cw = compPanel.clientWidth;
            ch = compPanel.clientHeight;
            compCanvas.width = cw;
            compCanvas.height = ch;
            drawCompass();
        }}

        function drawCompass() {{
            if (!SHOW_COMPASS) return;
            var ctx = compCtx;
            var cx = cw*0.5, cy = ch*0.48;
            var R = Math.min(cw, ch) * 0.32;

            ctx.clearRect(0, 0, cw, ch);
            ctx.fillStyle = '#111';
            ctx.fillRect(0, 0, cw, ch);

            // Quadrant fills
            ctx.fillStyle = 'rgba(38,166,154,0.07)';
            ctx.beginPath(); ctx.moveTo(cx,cy);
            ctx.arc(cx, cy, R, 0, Math.PI/2); ctx.closePath(); ctx.fill();
            ctx.fillStyle = 'rgba(239,83,80,0.07)';
            ctx.beginPath(); ctx.moveTo(cx,cy);
            ctx.arc(cx, cy, R, Math.PI, 3*Math.PI/2); ctx.closePath(); ctx.fill();

            // Circle
            ctx.strokeStyle = '#555';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(cx, cy, R, 0, 2*Math.PI);
            ctx.stroke();

            // Dashed axes
            ctx.setLineDash([3, 3]);
            ctx.strokeStyle = '#444';
            ctx.lineWidth = 0.5;
            ctx.beginPath(); ctx.moveTo(cx-R-15, cy); ctx.lineTo(cx+R+15, cy); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(cx, cy-R-15); ctx.lineTo(cx, cy+R+15); ctx.stroke();
            ctx.setLineDash([]);

            // Axis labels (fidèle Figure 2)
            ctx.font = '10px sans-serif';
            ctx.textAlign = 'left';
            ctx.fillStyle = '#26a69a';
            ctx.fillText('Adding', cx+R+4, cy-4);
            ctx.textAlign = 'right';
            ctx.fillStyle = '#ef5350';
            ctx.fillText('Trimming', cx-R-4, cy-4);
            ctx.textAlign = 'center';
            ctx.fillStyle = '#B71C1C';
            ctx.fillText('Bearish', cx, cy-R-8);
            ctx.fillStyle = '#26a69a';
            ctx.fillText('Bullish', cx, cy+R+14);

            // Sub-axis labels
            ctx.font = '8px sans-serif';
            ctx.fillStyle = '#555';
            ctx.fillText('Emotional', cx, cy-R-18);
            ctx.textAlign = 'left';
            ctx.fillText('Rebalancing', cx+R+4, cy+10);

            // Quadrant labels
            ctx.font = '9px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillStyle = '#555';
            ctx.fillText('mixed', cx+R*0.55, cy-R*0.5);
            ctx.fillStyle = '#ef5350';
            ctx.fillText('short', cx-R*0.55, cy-R*0.5);
            ctx.fillStyle = '#555';
            ctx.fillText('mixed', cx-R*0.55, cy+R*0.55);
            ctx.fillStyle = '#26a69a';
            ctx.fillText('long', cx+R*0.55, cy+R*0.55);

            if (!hasPhase && !hasData) return;

            // ATI Vector: e^{{iθ}}
            var px = cx + R * Math.cos(theta);
            var py = cy - R * Math.sin(theta);

            // Color by quadrant
            var cosT = Math.cos(theta), sinT = Math.sin(theta);
            var col;
            if (cosT >= 0 && sinT <= 0) col = '#26a69a';
            else if (cosT < 0 && sinT > 0) col = '#ef5350';
            else if (cosT >= 0 && sinT > 0) col = '#FFA726';
            else col = '#42A5F5';

            // Arc from +Re to theta
            ctx.strokeStyle = col;
            ctx.globalAlpha = 0.25;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(cx, cy, R*0.25, 0, -theta, theta > 0);
            ctx.stroke();
            ctx.globalAlpha = 1;

            // Vector line
            ctx.strokeStyle = col;
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(px, py);
            ctx.stroke();

            // Arrow head
            var ca = Math.atan2(py - cy, px - cx);
            var hl = 10;
            ctx.fillStyle = col;
            ctx.beginPath();
            ctx.moveTo(px, py);
            ctx.lineTo(px - hl*Math.cos(ca - 0.35), py - hl*Math.sin(ca - 0.35));
            ctx.lineTo(px - hl*Math.cos(ca + 0.35), py - hl*Math.sin(ca + 0.35));
            ctx.closePath();
            ctx.fill();

            // Glowing point
            ctx.shadowColor = col;
            ctx.shadowBlur = 12;
            ctx.fillStyle = col;
            ctx.beginPath();
            ctx.arc(px, py, 4, 0, 2*Math.PI);
            ctx.fill();
            ctx.shadowBlur = 0;

            // Text overlay (top-left of compass panel)
            ctx.font = 'bold 11px monospace';
            ctx.fillStyle = '#ddd';
            ctx.textAlign = 'left';
            ctx.fillText('n='+n+'  \\u03A9='+omega+'  \\u03C3='+(sigma*10000).toFixed(1)+'bp', 6, 16);
            var deg = (theta * 180 / Math.PI).toFixed(1);
            var qN;
            if (cosT >= 0 && sinT <= 0) qN = 'Long';
            else if (cosT < 0 && sinT > 0) qN = 'Short';
            else if (cosT >= 0 && sinT > 0) qN = 'Mixed \\u2191';
            else qN = 'Mixed \\u2193';
            ctx.fillText('\\u03B8='+deg+'\\u00B0  '+qN, 6, 32);
        }}

        // ═══════════════════════════════════════════════════
        // Resize handler
        // ═══════════════════════════════════════════════════
        function onResize() {{
            resizeDist();
            resizeComp();
        }}
        window.addEventListener('resize', onResize);
        onResize();

        // ═══════════════════════════════════════════════════
        // API called from Python
        // ═══════════════════════════════════════════════════
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
            drawDist();
            drawCompass();
        }};

        window.update_tick = function(cr) {{
            currentReturn = cr;
            if (hasData) drawDist();
        }};

        window.update_phase = function(t) {{
            theta = t;
            hasPhase = true;
            drawCompass();
        }};

        drawDist();
        drawCompass();
    </script>
</body>
</html>
"""

class Api:
    def __init__(self):
        self._window = None

    def set_window(self, window):
        self._window = window


def _compass_process(symbol: str, data_queue: mp.Queue,
                     show_dist: bool = True, show_compass: bool = False):
    """Process séparé : fenêtre distribution quantique + compass ATI.

    Pas de os.setpgrp() — le compass est lancé depuis _chart_worker
    qui a déjà son propre group. Tué automatiquement par killpg.
    """
    import logging
    logging.getLogger('pywebview').setLevel(logging.CRITICAL)

    # Layout flex : largeur selon ce qui est affiché
    both = show_dist and show_compass
    win_width = 900 if both else 500

    html_content = HTML_TEMPLATE.format(
        symbol=symbol,
        show_dist_js="true" if show_dist else "false",
        show_compass_js="true" if show_compass else "false",
        dist_flex="1" if show_dist else "0",
        dist_display="block" if show_dist else "none",
        compass_flex="1" if show_compass else "0",
        compass_display="block" if show_compass else "none",
        border="1px solid #333" if both else "none",
    )

    title_parts = []
    if show_dist:
        title_parts.append("Distribution")
    if show_compass:
        title_parts.append("ATI Compass")
    title = f"Quantum {' + '.join(title_parts)} - {symbol}"

    api = Api()
    window = webview.create_window(
        title,
        html=html_content,
        width=win_width,
        height=450,
        resizable=True,
        on_top=True,
    )
    api.set_window(window)

    def update_loop():
        while True:
            try:
                latest_tick = None
                latest_dist = None
                latest_phase = None
                while not data_queue.empty():
                    msg = data_queue.get_nowait()
                    if msg[0] == "tick":
                        latest_tick = msg
                    elif msg[0] == "dist":
                        latest_dist = msg
                    elif msg[0] == "phase":
                        latest_phase = msg

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

                if latest_phase:
                    _, theta_val = latest_phase
                    try:
                        window.evaluate_js(f"window.update_phase({theta_val})")
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
    def __init__(self, symbol: str, show_dist: bool = True, show_compass: bool = False):
        self.queue = mp.Queue()
        self.process = mp.Process(
            target=_compass_process,
            args=(symbol, self.queue, show_dist, show_compass),
            daemon=False,
        )
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

    def update_phase(self, theta: float):
        """Met à jour la phase θ du compass ATI (chaque tick)."""
        if self.process.is_alive():
            self.queue.put(("phase", theta))

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
