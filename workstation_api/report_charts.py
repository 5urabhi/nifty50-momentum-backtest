"""Export bounded saved QuantLab chart snapshots to safe SVG and PDF vectors.

No JS, HTML injection or network assets. This module visualizes the archived
model points and does not re-estimate parameters or invent extra observations.
"""
from __future__ import annotations

import html
import math

COLORS = ("#139e80", "#cb773e", "#4576bd", "#9959bd", "#c34f68",
          "#407f98", "#9c8d2e", "#5764aa")


def _finite(value):
    return (isinstance(value, (int, float)) and
            not isinstance(value, bool) and math.isfinite(value))


def _series(plot: dict):
    kind = plot.get("kind")
    if kind not in {"line2d", "bar2d", "fan2d", "histogram2d"}:
        return None
    xs = plot.get("x")
    raw = plot.get("traces")
    if not isinstance(xs, list) or not 2 <= len(xs) <= 600:
        return None
    if not isinstance(raw, list) or not 1 <= len(raw) <= 20:
        return None
    series = []
    for trace in raw:
        if not isinstance(trace, dict):
            return None
        ys = trace.get("y")
        if not isinstance(ys, list) or len(ys) != len(xs):
            return None
        if any(v is not None and not _finite(v) for v in ys):
            return None
        series.append((str(trace.get("name","Series"))[:80], ys))
    vals = [float(v) for _, ys in series for v in ys if _finite(v)]
    if not vals:
        return None
    low, high = min(vals), max(vals)
    if kind in {"bar2d","histogram2d"}:
        low = min(0., low)
        high = max(0., high)
    if high <= low:
        high = low + max(abs(low)*0.1, 1e-6)
    spread = high-low
    return kind, xs, series, low - .04*spread, high + .04*spread


def svg(plot: dict) -> str:
    """Safe static vector chart, suitable for embedding into an HTML report."""
    data = _series(plot)
    if data is None:
        return "<p>Saved figure is a 3D surface or unsupported plot; inspect in QuantLab.</p>"
    kind, xs, series, low, high = data
    left, right, top, bottom = 58, 790, 24, 262
    w, h = right-left, bottom-top
    xx = lambda i: left + w*i/max(1, len(xs)-1)
    yy = lambda v: bottom-h*(v-low)/(high-low)
    items = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 325" '
        'role="img" aria-label="' + html.escape(str(plot.get("title","Saved figure"))[:140], quote=True) + '">',
        '<rect x="0" y="0" width="840" height="325" fill="#f8fbfc"/>',
    ]
    for t in range(5):
        y = top+(h*t/4)
        val = high-(high-low)*t/4
        items.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#dbe5e9"/>')
        items.append(f'<text x="51" y="{y+4:.2f}" fill="#4b6871" font-size="11" text-anchor="end">{val:.3g}</text>')
    for j, (name, ys) in enumerate(series):
        color = COLORS[j % len(COLORS)]
        if kind in {"bar2d","histogram2d"}:
            bw = max(1.2, min(19, 0.67*w/len(xs)/len(series)))
            for i, value in enumerate(ys):
                if not _finite(value):
                    continue
                x = xx(i)+(j-(len(series)-1)/2)*bw
                y, zero = yy(float(value)), yy(0)
                items.append(f'<rect x="{x-bw*.45:.2f}" y="{min(y,zero):.2f}" '
                             f'width="{bw*.9:.2f}" height="{max(1,abs(y-zero)):.2f}" '
                             f'fill="{color}"/>')
        else:
            chunks, current = [], []
            for i, value in enumerate(ys):
                if not _finite(value):
                    if len(current) > 1:
                        chunks.append(current)
                    current = []
                else:
                    current.append(f"{xx(i):.2f},{yy(float(value)):.2f}")
            if len(current) > 1:
                chunks.append(current)
            for chunk in chunks:
                items.append('<polyline fill="none" stroke="'+color+
                             '" stroke-width="2" points="'+" ".join(chunk)+'"/>')
        legend_x = left+(j % 3)*244
        legend_y = 289+(j//3)*11
        if legend_y < 320:
            items.append(f'<circle cx="{legend_x}" cy="{legend_y-4}" r="4" fill="{color}"/>')
            items.append(f'<text x="{legend_x+10}" y="{legend_y}" fill="#193d4b" '
                         f'font-size="10">{html.escape(name[:34])}</text>')
    items.append('<text x="58" y="277" fill="#486671" font-size="10">'+
                 html.escape(str(xs[0])[:24])+'</text>')
    items.append('<text x="790" y="277" text-anchor="end" fill="#486671" font-size="10">'+
                 html.escape(str(xs[-1])[:24])+'</text>')
    items.append('</svg>')
    return "".join(items)


def pdf_drawing(plot: dict):
    """Return a selectable vector drawing for supported saved 2D plots."""
    data = _series(plot)
    if data is None:
        return None
    from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
    from reportlab.lib.colors import HexColor
    kind, xs, series, low, high = data
    left, right, top, bottom = 44, 450, 203, 22
    w, h = right-left, top-bottom
    xx = lambda i: left + w*i/max(1, len(xs)-1)
    yy = lambda v: bottom+h*(v-low)/(high-low)
    drawing = Drawing(480, 252)
    drawing.add(Rect(0, 0, 480, 252, fillColor=HexColor("#f7fbfc"), strokeColor=None))
    for t in range(5):
        y = bottom+(h*t/4)
        drawing.add(Line(left,y,right,y,strokeColor=HexColor("#d8e6e8")))
    for j, (name, ys) in enumerate(series):
        color = HexColor(COLORS[j%len(COLORS)])
        if kind in {"bar2d","histogram2d"}:
            bw = max(1.1,min(15,0.65*w/len(xs)/len(series)))
            for i,value in enumerate(ys):
                if not _finite(value):
                    continue
                x = xx(i)+(j-(len(series)-1)/2)*bw
                y, zero = yy(float(value)), yy(0)
                drawing.add(Rect(x-bw*.45,min(y,zero),bw*.9,max(1,abs(y-zero)),
                                 strokeColor=None, fillColor=color))
        else:
            points=[]
            for i,value in enumerate(ys):
                if not _finite(value):
                    if len(points) >= 4:
                        drawing.add(PolyLine(points,strokeColor=color,strokeWidth=1.7,fillColor=None))
                    points=[]
                    continue
                points.extend([xx(i),yy(float(value))])
            if len(points) >= 4:
                drawing.add(PolyLine(points,strokeColor=color,strokeWidth=1.7,fillColor=None))
        k=j%3
        legend_y = 239-(j//3)*10
        if legend_y > 205:
            drawing.add(Line(left+k*145,legend_y,left+k*145+12,legend_y,
                             strokeColor=color,strokeWidth=3))
            drawing.add(String(left+k*145+16,legend_y-4,name[:23],
                               fontName="Helvetica",fontSize=7))
    drawing.add(String(left,9,str(xs[0])[:18],fontName="Helvetica",fontSize=8))
    drawing.add(String(right,9,str(xs[-1])[:18],fontName="Helvetica",fontSize=8,
                       textAnchor="end"))
    return drawing
