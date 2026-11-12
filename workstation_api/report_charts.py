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


def _saved_regions(plot: dict, dates: list) -> list[tuple[int,int,str]]:
    """Render only exact saved X values and valid, ordered regions."""
    result=[]
    if not isinstance(plot.get("regions"),list):
        return result
    for entry in plot["regions"][:3]:
        if not isinstance(entry,dict):
            continue
        start,end=entry.get("start"),entry.get("end")
        try:
            first=next(i for i,x in enumerate(dates) if str(x)==str(start))
            last=next(i for i,x in enumerate(dates) if str(x)==str(end))
        except StopIteration:
            continue
        if last<first:
            continue
        result.append((first,last,str(entry.get("label","Highlighted period"))[:45]))
    return result


def svg(plot: dict) -> str:
    """Safe static vector chart, suitable for embedding into an HTML report."""
    if plot.get("kind") == "scatter2d":
        return _svg_scatter(plot)
    if plot.get("kind") == "heatmap2d":
        return _svg_heatmap(plot)
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
    for first,last,label in _saved_regions(plot,xs):
        x1,x2=xx(first),xx(last)
        items.append(f'<rect x="{x1:.2f}" y="{top}" width="{max(1.,x2-x1):.2f}" '
                     f'height="{h}" fill="#9dd5f6" opacity=".26"/>')
        items.append(f'<text x="{min(right-120,x1+3):.2f}" y="{top+11}" '
                     f'fill="#21455c" font-size="9">{html.escape(label)}</text>')
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
    if plot.get("kind") == "scatter2d":
        return _pdf_scatter(plot)
    if plot.get("kind") == "heatmap2d":
        return _pdf_heatmap(plot)
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
    for first,last,label in _saved_regions(plot,xs):
        x1,x2=xx(first),xx(last)
        drawing.add(Rect(x1,bottom,max(1.,x2-x1),h,strokeColor=None,
                         fillColor=HexColor("#e5f1ff")))
        drawing.add(String(min(right-95,x1+3),top-11,
                           label.encode("latin-1","replace").decode("latin-1")[:25],
                           fontSize=7,fillColor=HexColor("#24506a")))
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


def _scatter_data(plot: dict):
    xs, ys = plot.get("x"), plot.get("y")
    if (not isinstance(xs, list) or not isinstance(ys,list)
            or not 2<=len(xs)<=600 or len(xs)!=len(ys)
            or any(not _finite(v) for v in xs+ys)):
        return None
    lowx, highx, lowy, highy = min(xs), max(xs), min(ys), max(ys)
    if highx==lowx: highx=lowx+1
    if highy==lowy: highy=lowy+1
    return xs,ys,lowx,highx,lowy,highy


def _heatmap_data(plot: dict):
    labels=plot.get("labels")
    values=plot.get("values")
    row_labels=plot.get("row_labels",labels)
    if (not isinstance(labels,list) or not isinstance(row_labels,list)
            or not 1<=len(labels)<=25 or not 1<=len(row_labels)<=25
            or not isinstance(values,list) or len(values)!=len(row_labels)
            or any(not isinstance(row,list) or len(row)!=len(labels) or
                   any(not _finite(v) for v in row) for row in values)):
        return None
    flat=[float(v) for row in values for v in row]
    low,high=min(flat),max(flat)
    return labels,row_labels,values,low,high


def _color_for(value, low, high, sequential):
    import colorsys
    z=max(0.,min(1.,((value-low)/max(1e-12,high-low)) if sequential
                    else (value+1)/2))
    r,g,b=colorsys.hls_to_rgb(.56-.13*z,.49,.47)
    return "#%02x%02x%02x"%(int(r*255),int(g*255),int(b*255))


def _svg_scatter(plot):
    data=_scatter_data(plot)
    if data is None:
        return "<p>Saved scatter points are unavailable or invalid.</p>"
    xs,ys,lowx,highx,lowy,highy=data
    parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 325" role="img" '
           'aria-label="'+html.escape(str(plot.get("title","Saved scatter"))[:140],quote=True)+'">',
           '<rect width="840" height="325" fill="#f8fbfc"/>']
    for x,y in zip(xs,ys):
        px=65+730*(x-lowx)/(highx-lowx)
        py=270-230*(y-lowy)/(highy-lowy)
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="2.6" fill="#139e80" fill-opacity=".6">'
                     f'<title>{float(x):.5g}, {float(y):.5g}</title></circle>')
    parts+=['<line x1="65" y1="270" x2="796" y2="270" stroke="#44656b"/>',
            '<line x1="65" y1="40" x2="65" y2="270" stroke="#44656b"/>',
            '<text x="430" y="304" text-anchor="middle" font-size="12">'+
            html.escape(str(plot.get("x_label","X"))[:60])+'</text>',
            '<text x="25" y="150" text-anchor="middle" transform="rotate(-90,25,150)" font-size="12">'+
            html.escape(str(plot.get("y_label","Y"))[:60])+'</text>','</svg>']
    return "".join(parts)


def _svg_heatmap(plot):
    data=_heatmap_data(plot)
    if data is None:
        return "<p>Saved heatmap matrix is unavailable or invalid.</p>"
    labels, row_labels, values, low, high=data
    columns=len(labels); rows=len(row_labels)
    cell=min(42,max(13,int(650/max(columns,rows))))
    width=145+cell*columns
    height=85+cell*rows
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" '
           'aria-label="'+html.escape(str(plot.get("title","Saved heatmap"))[:140],quote=True)+'">',
           f'<rect width="{width}" height="{height}" fill="#f8fbfc"/>']
    sequential=plot.get("scale")=="sequential"
    for i,label in enumerate(labels):
        parts.append(f'<text x="{122+i*cell+cell/2}" y="43" text-anchor="start" font-size="9" '
                     f'transform="rotate(-37,{122+i*cell+cell/2},43)">'+
                     html.escape(str(label)[:13])+'</text>')
    for row_index,row in enumerate(values):
        parts.append(f'<text x="115" y="{59+row_index*cell+cell/2}" '
                     'text-anchor="end" font-size="9">'+
                     html.escape(str(row_labels[row_index])[:15])+'</text>')
        for j,value in enumerate(row):
            color=_color_for(value,low,high,sequential)
            parts.append(f'<rect x="{122+j*cell}" y="{54+row_index*cell}" '
                         f'width="{cell-2}" height="{cell-2}" rx="2" fill="{color}">'
                         f'<title>{float(value):.6g}</title></rect>')
    parts.append('</svg>')
    return "".join(parts)


def _pdf_scatter(plot):
    data=_scatter_data(plot)
    if data is None:return None
    from reportlab.graphics.shapes import Drawing, Circle, Rect, Line, String
    from reportlab.lib.colors import HexColor
    xs,ys,lowx,highx,lowy,highy=data
    canvas=Drawing(480,252)
    canvas.add(Rect(0,0,480,252,fillColor=HexColor("#f8fbfc"),strokeColor=None))
    canvas.add(Line(39,24,454,24,strokeColor=HexColor("#44656b")))
    canvas.add(Line(39,24,39,222,strokeColor=HexColor("#44656b")))
    for x,y in zip(xs,ys):
        canvas.add(Circle(39+415*(x-lowx)/(highx-lowx),
                          24+198*(y-lowy)/(highy-lowy),1.8,
                          strokeColor=None,fillColor=HexColor("#139e80")))
    canvas.add(String(240,7,str(plot.get("x_label","X"))[:52],
                      fontSize=9,textAnchor="middle"))
    canvas.add(String(42,234,str(plot.get("y_label","Y"))[:52],fontSize=9))
    return canvas


def _pdf_heatmap(plot):
    data=_heatmap_data(plot)
    if data is None:return None
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.lib.colors import HexColor
    labels,row_labels,values,low,high=data
    count=max(len(labels),len(row_labels))
    cell=max(9,min(20,200/count))
    canvas=Drawing(480,252)
    canvas.add(Rect(0,0,480,252,strokeColor=None,fillColor=HexColor("#f8fbfc")))
    sequential=plot.get("scale")=="sequential"
    for j,label in enumerate(labels):
        canvas.add(String(55+j*cell,230,str(label)[:7],fontSize=7))
    for i,row in enumerate(values):
        y=208-(i+1)*cell
        canvas.add(String(5,y+4,str(row_labels[i])[:8],fontSize=7))
        for j,value in enumerate(row):
            canvas.add(Rect(55+j*cell,y,cell-1,cell-1,strokeColor=None,
                            fillColor=HexColor(_color_for(value,low,high,sequential))))
    return canvas
