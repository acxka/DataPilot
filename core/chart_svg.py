# -*- coding: utf-8 -*-
"""零依赖 SVG 图表生成（柱状图/折线图/分组柱状图），供 Agent 可视化与报告截图使用。"""
import os
import re

PALETTE = ["#2563eb", "#16a34a", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2"]
FONT = "'Microsoft YaHei','PingFang SC',SimHei,sans-serif"


def _nice_max(v):
    if v <= 0:
        return 1.0
    exp = 0
    while v >= 10:
        v /= 10.0
        exp += 1
    while v < 1:
        v *= 10
        exp -= 1
    steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
    for s in steps:
        if v <= s:
            v = s
            break
    return v * (10 ** exp)


def fmt_num(v):
    try:
        v = float(v)
    except Exception:
        return str(v)
    for unit, div in (("亿", 1e8), ("万", 1e4)):
        if abs(v) >= div:
            return ("%.2f" % (v / div)).rstrip("0").rstrip(".") + unit
    if abs(v) >= 100:
        return "{:,.0f}".format(v)
    if abs(v) >= 1:
        return ("%.2f" % v).rstrip("0").rstrip(".")
    return ("%.4f" % v).rstrip("0").rstrip(".")


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def make_svg(chart_type, title, x_labels, series, y_label="", width=820, height=440):
    x_labels = [str(x) for x in (x_labels or [])]
    series = [s for s in (series or []) if s.get("values")]
    if not x_labels or not series:
        raise ValueError("缺少 x_labels 或 series 数据")
    if len(x_labels) > 24:
        x_labels = x_labels[:24]
        series = [{"name": s["name"], "values": s["values"][:24]} for s in series]
    n = len(x_labels)
    k = len(series)
    ml, mr, mt, mb = 78, 26, 54, 74
    pw, ph = width - ml - mr, height - mt - mb
    if chart_type not in ("bar", "line", "grouped_bar", "hbar"):
        chart_type = "bar"
    if chart_type == "line":
        all_vals = [float(v) for s in series for v in s["values"]]
    else:
        all_vals = [float(v) for s in series for v in s["values"]]
    vmax = _nice_max(max(all_vals + [0]))
    vmin = 0.0
    if chart_type == "line" and min(all_vals) < 0:
        vmin = -_nice_max(abs(min(all_vals)))
    def y_px(v):
        return mt + ph - (float(v) - vmin) / (vmax - vmin) * ph
    def x_center(i):
        return ml + pw / n * (i + 0.5)

    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (width, height, width, height),
           '<rect width="100%%" height="100%%" fill="#ffffff"/>',
           '<text x="%d" y="30" font-family="%s" font-size="18" font-weight="700" fill="#0f172a">%s</text>' % (ml, FONT, _esc(title))]
    if y_label:
        out.append('<text x="%d" y="%d" font-family="%s" font-size="12" fill="#64748b">%s</text>' % (18, mt - 8, FONT, _esc(y_label)))
    # 网格与 y 轴刻度
    for t in range(6):
        v = vmin + (vmax - vmin) * t / 5.0
        y = y_px(v)
        out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#e2e8f0" stroke-width="1"/>' % (ml, y, ml + pw, y))
        out.append('<text x="%d" y="%.1f" font-family="%s" font-size="11" fill="#94a3b8" text-anchor="end">%s</text>'
                   % (ml - 8, y + 4, FONT, fmt_num(v)))
    # x 轴
    out.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#94a3b8" stroke-width="1.2"/>' % (ml, y_px(0 if vmin <= 0 <= vmax else vmin), ml + pw, y_px(0 if vmin <= 0 <= vmax else vmin)))
    # 柱/线
    if chart_type in ("bar", "grouped_bar"):
        group_w = pw / n * 0.72
        bar_w = group_w / k
        for i in range(n):
            for j, s in enumerate(series):
                v = float(s["values"][i])
                x = ml + pw / n * i + (pw / n - group_w) / 2 + j * bar_w
                y0, y1 = y_px(max(v, 0)), y_px(min(v, 0))
                color = PALETTE[j % len(PALETTE)]
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="3" fill="%s"/>'
                           % (x, y1, max(bar_w - 3, 2), max(abs(y0 - y1), 0.5), color))
                if n <= 12:
                    out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="10.5" fill="#334155" text-anchor="middle">%s</text>'
                               % (x + bar_w / 2, y1 - 5, FONT, fmt_num(v)))
        for i in range(n):
            out.append('<text x="%.1f" y="%d" font-family="%s" font-size="11" fill="#475569" text-anchor="middle">%s</text>'
                       % (x_center(i), mt + ph + 20, FONT, _esc(x_labels[i])))
    elif chart_type == "line":
        for j, s in enumerate(series):
            pts = " ".join("%.1f,%.1f" % (x_center(i), y_px(s["values"][i])) for i in range(n))
            color = PALETTE[j % len(PALETTE)]
            out.append('<polyline points="%s" fill="none" stroke="%s" stroke-width="2.6" stroke-linejoin="round"/>' % (pts, color))
            for i in range(n):
                out.append('<circle cx="%.1f" cy="%.1f" r="3.4" fill="#fff" stroke="%s" stroke-width="2"/>'
                           % (x_center(i), y_px(s["values"][i]), color))
        for i in range(n):
            out.append('<text x="%.1f" y="%d" font-family="%s" font-size="11" fill="#475569" text-anchor="middle">%s</text>'
                       % (x_center(i), mt + ph + 20, FONT, _esc(x_labels[i])))
    # 图例
    lx = ml
    for j, s in enumerate(series):
        out.append('<rect x="%d" y="%d" width="12" height="12" rx="2" fill="%s"/>' % (lx, height - 34, PALETTE[j % len(PALETTE)]))
        out.append('<text x="%d" y="%d" font-family="%s" font-size="12" fill="#334155">%s</text>' % (lx + 18, height - 24, FONT, _esc(s.get("name", ""))))
        lx += 26 + 13 * len(str(s.get("name", "")))
    out.append("</svg>")
    return "\n".join(out)


def save_svg(directory, chart_type, title, x_labels, series, y_label=""):
    os.makedirs(directory, exist_ok=True)
    slug = re.sub(r"[^\w\u4e00-\u9fa5]+", "_", title)[:40] or "chart"
    path = os.path.join(directory, slug + ".svg")
    i = 1
    while os.path.exists(path):
        i += 1
        path = os.path.join(directory, "%s_%d.svg" % (slug, i))
    with open(path, "w", encoding="utf-8") as f:
        f.write(make_svg(chart_type, title, x_labels, series, y_label))
    return path
