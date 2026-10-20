# -*- coding: utf-8 -*-
"""报告配图生成（Pillow，零外部素材）：架构图、对比柱状图、Trace 时间线。
运行：python report/make_assets.py
"""
import json
import os
import sqlite3

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "report", "assets")
os.makedirs(ASSETS, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/msyh.ttc"
FONT_BOLD = "C:/Windows/Fonts/msyhbd.ttc"
if not os.path.exists(FONT_BOLD):
    FONT_BOLD = FONT_PATH

C_NAVY = (30, 58, 95)
C_BLUE = (37, 99, 235)
C_GREEN = (22, 163, 74)
C_ORANGE = (234, 88, 12)
C_PURPLE = (124, 58, 237)
C_GRAY = (100, 116, 139)
C_LIGHT = (241, 245, 249)
C_BORDER = (203, 213, 225)
C_WHITE = (255, 255, 255)


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, size)


def text(d, xy, s, size=22, bold=False, fill=C_NAVY, anchor="la"):
    d.text(xy, s, font=font(size, bold), fill=fill, anchor=anchor)


def rrect(d, box, radius=14, fill=C_WHITE, outline=C_BORDER, width=2):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def center(d, box, s, size=22, bold=False, fill=C_NAVY):
    x0, y0, x1, y1 = box
    text(d, ((x0 + x1) // 2, (y0 + y1) // 2), s, size, bold, fill, anchor="mm")


def arrow(d, p0, p1, color=C_GRAY, width=3, label="", label_size=16):
    d.line([p0, p1], fill=color, width=width)
    import math
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    L, W = 16, 8
    left = (p1[0] - L * math.cos(ang) + W * math.sin(ang), p1[1] - L * math.sin(ang) - W * math.cos(ang))
    right = (p1[0] - L * math.cos(ang) - W * math.sin(ang), p1[1] - L * math.sin(ang) + W * math.cos(ang))
    d.polygon([p1, left, right], fill=color)
    if label:
        mx, my = (p0[0] + p1[0]) // 2, (p0[1] + p1[1]) // 2
        tw = d.textlength(label, font=font(label_size))
        d.rectangle([mx - tw / 2 - 6, my - 13, mx + tw / 2 + 6, my + 13], fill=(255, 255, 255))
        text(d, (mx, my), label, label_size, False, C_GRAY, anchor="mm")


def architecture():
    W, H = 1480, 980
    img = Image.new("RGB", (W, H), C_LIGHT)
    d = ImageDraw.Draw(img)
    text(d, (46, 26), "DataPilot 系统架构", 46, True, C_NAVY)
    text(d, (48, 84), "规划 — 执行 — 复核 三 Agent 协同 · 只读数据沙箱 · 全链路可审计", 22, False, C_GRAY)

    # 用户层 / 接入层
    rrect(d, (46, 130, 390, 236), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (46, 130, 390, 180), "业务用户", 26, True, C_BLUE)
    center(d, (46, 180, 390, 236), "区域经理 / 运营 / 店长", 19, False, C_GRAY)
    rrect(d, (460, 130, 820, 236), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (460, 130, 820, 180), "接入层 CLI / 飞书机器人", 26, True, C_BLUE)
    center(d, (460, 180, 820, 236), "自然语言提问 · 多轮对话 · IM 长连接", 18, False, C_GRAY)
    arrow(d, (390, 183), (460, 183), C_BLUE, 4, "提问")

    # Planner
    rrect(d, (920, 120, 1434, 246), fill=(245, 243, 255), outline=(196, 181, 253))
    center(d, (920, 120, 1434, 170), "Planner 规划 Agent", 28, True, C_PURPLE)
    center(d, (920, 170, 1434, 246), "拆解子问题 · 指定指标与维度 · 识别信息缺口", 19, False, C_GRAY)
    arrow(d, (820, 183), (920, 183), C_PURPLE, 4, "问题")
    arrow(d, (1177, 246), (1177, 300), C_PURPLE, 4, "分析计划")

    # 信任边界 + Executor + 数据层
    text(d, (840, 292), "信任边界：Agent 只读访问，写操作在进入数据库前被拦截", 17, True, (220, 38, 38))
    d.rectangle([(826, 318), (1444, 566)], outline=(220, 38, 38), width=4)
    rrect(d, (850, 336, 1190, 548), fill=(240, 253, 244), outline=(134, 239, 172))
    center(d, (850, 336, 1190, 386), "Executor 执行 Agent（ReAct）", 21, True, C_GREEN)
    center(d, (850, 392, 1190, 430), "Thought → Tool → Observation 循环", 18, False, C_GRAY)
    rrect(d, (868, 440, 1172, 532), fill=C_WHITE, outline=(134, 239, 172))
    center(d, (868, 440, 1172, 486), "7 个工具：表结构 / 只读SQL / 字段画像", 17, False, C_NAVY)
    center(d, (868, 486, 1172, 532), "SVG 图表 / 口径检索 / 用户澄清", 17, False, C_NAVY)
    rrect(d, (1210, 336, 1420, 548), fill=(254, 249, 195), outline=(253, 224, 71))
    center(d, (1210, 336, 1420, 386), "数据层", 24, True, (161, 98, 7))
    center(d, (1210, 390, 1420, 440), "SQLite 只读库", 18, False, C_GRAY)
    center(d, (1210, 440, 1420, 490), "9 张表 / 44k 订单", 18, False, C_GRAY)
    center(d, (1210, 490, 1420, 540), "指标口径库", 18, False, C_GRAY)
    arrow(d, (1190, 430), (1210, 430), (161, 98, 7), 3)

    # 草稿 → Reviewer
    arrow(d, (1177, 566), (1177, 640), C_GREEN, 4, "草稿 + 证据链")
    rrect(d, (880, 640, 1434, 790), fill=(255, 247, 237), outline=(253, 186, 116))
    center(d, (880, 640, 1434, 692), "Reviewer 复核 Agent", 28, True, C_ORANGE)
    text(d, (902, 708), "① 数字溯源：结论数字必须来自 SQL 结果或可推导", 20, False, C_GRAY)
    text(d, (902, 748), "② 口径 / 因果 / 完整性审查，不通过则回退补查（最多 2 轮）", 19, False, C_GRAY)

    # 回退补查
    d.line([(880, 720), (846, 720)], fill=C_ORANGE, width=4)
    d.line([(846, 720), (846, 420)], fill=C_ORANGE, width=4)
    arrow(d, (846, 420), (880, 430), C_ORANGE, 4)
    text(d, (596, 664), "复核不通过 → 回退补查", 19, False, C_ORANGE)

    # 输出
    arrow(d, (1177, 790), (1177, 862), C_NAVY, 4, "复核通过")
    rrect(d, (840, 862, 1434, 956), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (840, 862, 1434, 908), "结构化结论与交付物", 26, True, C_BLUE)
    center(d, (840, 908, 1434, 956), "结论 / 数据（注明来源） / 归因 / 建议 / 图表 / Trace", 18, False, C_GRAY)

    # Trace
    rrect(d, (46, 336, 390, 566), fill=(248, 250, 252), outline=C_BORDER)
    center(d, (46, 336, 390, 390), "Trace 全链路留痕", 26, True, C_NAVY)
    center(d, (46, 400, 390, 444), "trace.jsonl 逐步结构化日志", 19, False, C_GRAY)
    center(d, (46, 444, 390, 486), "trace.html 可视化回放", 19, False, C_GRAY)
    center(d, (46, 486, 390, 528), "护栏事件 / token / 耗时统计", 19, False, C_GRAY)
    text(d, (62, 534), "每一步模型决策与工具返回都可回放", 17, False, C_GRAY)

    # 模型路由
    rrect(d, (46, 862, 800, 956), fill=(248, 250, 252), outline=C_BORDER)
    center(d, (46, 862, 800, 908), "模型路由与降级", 26, True, C_NAVY)
    center(d, (46, 908, 800, 956), "主：DeepSeek v4-pro（执行）/ flash（规划·复核） · 备：中转站自动降级", 17, False, C_GRAY)

    path = os.path.join(ASSETS, "architecture.png")
    img.save(path)
    return path

def grouped_bar(path, title, labels, series, ylabel="", width=1000, height=540, fmt=None):
    img = Image.new("RGB", (width, height), C_WHITE)
    d = ImageDraw.Draw(img)
    text(d, (46, 24), title, 32, True, C_NAVY)
    if ylabel:
        text(d, (48, 68), ylabel, 19, False, C_GRAY)
    ml, mr, mt, mb = 96, 30, 108, 96
    pw, ph = width - ml - mr, height - mt - mb
    vals = [v for s in series for v in s["values"]]
    vmax = max(vals) * 1.15 if max(vals) > 0 else 1
    colors = [C_BLUE, C_GRAY, C_GREEN]
    for t in range(6):
        y = mt + ph - ph * t / 5
        d.line([(ml, y), (ml + pw, y)], fill=(226, 232, 240), width=1)
        text(d, (ml - 10, y), fmt(t * vmax / 5) if fmt else "%g" % (t * vmax / 5), 17, False, C_GRAY, anchor="rm")
    n, k = len(labels), len(series)
    group_w = pw / n * 0.7
    bar_w = group_w / k
    for i, lab in enumerate(labels):
        for j, s in enumerate(series):
            v = s["values"][i]
            x = ml + pw / n * i + (pw / n - group_w) / 2 + j * bar_w
            y = mt + ph - ph * max(v, 0) / vmax
            d.rounded_rectangle([x, y, x + bar_w - 6, mt + ph], radius=4, fill=colors[j % len(colors)])
            text(d, (x + (bar_w - 6) / 2, y - 8), fmt(v) if fmt else "%g" % v, 16, False, C_NAVY, anchor="mb")
        text(d, (ml + pw / n * (i + 0.5), mt + ph + 20), lab, 19, False, C_GRAY, anchor="ma")
    lx = ml
    for j, s in enumerate(series):
        d.rectangle([lx, height - 52, lx + 16, height - 36], fill=colors[j % len(colors)])
        text(d, (lx + 26, height - 58), s["name"], 18, False, C_NAVY)
        lx += 44 + d.textlength(s["name"], font=font(18))
    img.save(path)
    return path


def chart_from_db(path, title, sql, fmt=None):
    conn = sqlite3.connect("file:%s?mode=ro" % os.path.join(ROOT, "data", "retail.db").replace("\\", "/"), uri=True)
    rows = conn.execute(sql).fetchall()
    conn.close()
    labels = [r[0] for r in rows]
    s1 = {"name": "2024-10", "values": [r[1] for r in rows]}
    s2 = {"name": "2025-10", "values": [r[2] for r in rows]}
    return grouped_bar(path, title, labels, [s1, s2], "销售额（元）", fmt=fmt)


def trace_timeline(path, trace_jsonl, width=1050, max_steps=26):
    recs = []
    with open(trace_jsonl, encoding="utf-8") as f:
        for line in f:
            recs.append(json.loads(line))
    recs = recs[:max_steps]
    row_h = 54
    height = 120 + row_h * len(recs) + 40
    img = Image.new("RGB", (width, height), C_WHITE)
    d = ImageDraw.Draw(img)
    text(d, (40, 22), "运行轨迹 Trace（真实执行日志时间线）", 32, True, C_NAVY)
    text(d, (42, 66), "每一行对应 trace.jsonl 中的一条记录：模型决策 / 工具调用 / 护栏事件", 18, False, C_GRAY)
    colors = {"user": C_BLUE, "llm": C_PURPLE, "tool": C_GREEN, "guard": (220, 38, 38),
              "system": (8, 145, 178), "final": C_NAVY}
    labels = {"user": "用户", "llm": "模型", "tool": "工具", "guard": "护栏",
              "system": "规划/复核", "final": "回答"}
    y = 110
    for i, r in enumerate(recs):
        kind = r.get("kind", "")
        color = colors.get(kind, C_GRAY)
        d.line([(130, y), (130, y + row_h)], fill=(226, 232, 240), width=3)
        d.ellipse([(120, y + 14), (140, y + 34)], fill=color)
        text(d, (40, y + 14), "步骤%02d" % r.get("step", i + 1), 17, False, C_GRAY)
        tag = labels.get(kind, kind)
        tw = d.textlength(tag, font=font(17))
        d.rounded_rectangle([168, y + 8, 168 + tw + 26, y + 40], radius=12, fill=color)
        text(d, (168 + 13, y + 24), tag, 17, True, C_WHITE, anchor="lm")
        desc = ""
        if kind == "tool":
            desc = "%s(%s)" % (r.get("name"), _short(r.get("args"), 70))
        elif kind == "llm":
            tc = r.get("tool_calls") or []
            desc = "生成 %d 个工具调用 · %.1fs · %s tokens" % (len(tc), r.get("latency") or 0, r.get("tokens") or 0)
        elif kind == "guard":
            desc = "拦截：%s" % (r.get("reason") or r.get("action") or "")
        elif kind == "final":
            desc = "输出最终结论（%d 字）" % len(r.get("text") or "")
        elif kind == "user":
            desc = r.get("text") or ""
        else:
            desc = (r.get("text") or "")[:80].replace("\n", " ")
        text(d, (356, y + 18), _short(desc, 62), 19, False, (51, 65, 85))
        y += row_h
    img.save(path)
    return path


def _short(obj, n=80):
    s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


if __name__ == "__main__":
    print(architecture())
    print(grouped_bar(os.path.join(ASSETS, "eval_by_category.png"), "40 题评测集分类型通过率",
                      ["基础聚合", "多表关联", "同比环比", "归因分析", "模糊缺参", "越权注入"],
                      [{"name": "通过率(%)", "values": [0, 0, 0, 0, 0, 0]}], "百分比", fmt=lambda v: "%.0f" % v))
    print("done")