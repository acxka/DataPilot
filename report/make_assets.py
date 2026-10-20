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
    W, H = 1680, 1080
    img = Image.new("RGB", (W, H), C_LIGHT)
    d = ImageDraw.Draw(img)
    text(d, (60, 40), "DataPilot 系统架构", 40, True, C_NAVY)
    text(d, (62, 96), "规划 — 执行 — 复核 三 Agent 协同 · 只读数据沙箱 · 全链路可审计", 20, False, C_GRAY)

    # 用户层 / 接入层
    rrect(d, (60, 170, 400, 270), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (60, 170, 400, 220), "业务用户", 22, True, C_BLUE)
    center(d, (60, 220, 400, 270), "区域经理 / 运营 / 店长", 17, False, C_GRAY)
    rrect(d, (470, 170, 810, 270), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (470, 170, 810, 220), "接入层 CLI / Web", 22, True, C_BLUE)
    center(d, (470, 220, 810, 270), "自然语言提问 · 多轮对话 · 澄清", 17, False, C_GRAY)
    arrow(d, (400, 220), (470, 220), C_BLUE, 3, "提问")

    # Planner
    rrect(d, (930, 150, 1440, 270), fill=(245, 243, 255), outline=(196, 181, 253))
    center(d, (930, 150, 1440, 195), "Planner 规划 Agent", 23, True, C_PURPLE)
    center(d, (930, 195, 1440, 270), "拆解子问题 · 指定指标与维度 · 识别信息缺口", 17, False, C_GRAY)
    arrow(d, (810, 220), (930, 220), C_PURPLE, 3, "问题")
    arrow(d, (1185, 270), (1185, 325), C_PURPLE, 3, "分析计划")

    # 信任边界 + Executor
    text(d, (868, 318), "信任边界：Agent 只读访问，写操作在进入数据库前被拦截", 15, True, (220, 38, 38))
    d.rectangle([(855, 345), (1660, 565)], outline=(220, 38, 38), width=3)
    rrect(d, (930, 365, 1440, 535), fill=(240, 253, 244), outline=(134, 239, 172))
    center(d, (930, 365, 1440, 411), "Executor 执行 Agent（ReAct）", 23, True, C_GREEN)
    text(d, (955, 423), "Thought → Tool Call → Observation 循环", 17, False, C_GRAY)
    rrect(d, (955, 452, 1415, 520), fill=C_WHITE, outline=(134, 239, 172))
    center(d, (955, 452, 1415, 486), "7 个工具：表结构 / 只读SQL / 字段画像", 16, False, C_NAVY)
    center(d, (955, 486, 1415, 520), "SVG 图表 / 指标口径检索 / 用户澄清", 16, False, C_NAVY)

    # 数据层
    rrect(d, (1470, 365, 1640, 535), fill=(254, 249, 195), outline=(253, 224, 71))
    center(d, (1470, 365, 1640, 411), "数据层", 21, True, (161, 98, 7))
    center(d, (1470, 415, 1640, 455), "SQLite 只读库", 16, False, C_GRAY)
    center(d, (1470, 455, 1640, 493), "9 张表 / 44k 订单", 16, False, C_GRAY)
    center(d, (1470, 493, 1640, 533), "指标口径库", 16, False, C_GRAY)
    arrow(d, (1440, 450), (1470, 450), (161, 98, 7), 3)

    # 草稿 → Reviewer
    arrow(d, (1185, 535), (1185, 640), C_GREEN, 3, "草稿结论 + 证据链")

    # Reviewer
    rrect(d, (930, 640, 1440, 800), fill=(255, 247, 237), outline=(253, 186, 116))
    center(d, (930, 640, 1440, 688), "Reviewer 复核 Agent", 23, True, C_ORANGE)
    text(d, (955, 705), "① 数字溯源校验：结论数字必须来自 SQL 结果或可推导", 17, False, C_GRAY)
    text(d, (955, 740), "② 口径 / 因果 / 完整性审查 · 不通过则带意见回退补查", 17, False, C_GRAY)

    # 回退补查
    d.line([(930, 720), (890, 720)], fill=C_ORANGE, width=3)
    d.line([(890, 720), (890, 450)], fill=C_ORANGE, width=3)
    arrow(d, (890, 450), (930, 460), C_ORANGE, 3)
    text(d, (640, 600), "复核不通过 → 回退补查（最多 2 轮）", 17, False, C_ORANGE)

    # 输出
    arrow(d, (1185, 800), (1185, 875), C_NAVY, 3, "复核通过")
    rrect(d, (860, 875, 1510, 1005), fill=(239, 246, 255), outline=(147, 197, 253))
    center(d, (860, 875, 1510, 930), "结构化结论与交付物", 23, True, C_BLUE)
    center(d, (860, 930, 1510, 968), "一句话结论 / 关键数据（注明来源） / 归因分析 / 行动建议", 17, False, C_GRAY)
    center(d, (860, 968, 1510, 1005), "图表 SVG / Trace 轨迹 / 评测报告", 16, False, C_GRAY)

    # Trace
    rrect(d, (60, 365, 400, 575), fill=(248, 250, 252), outline=C_BORDER)
    center(d, (60, 365, 400, 415), "Trace 全链路留痕", 21, True, C_NAVY)
    center(d, (60, 420, 400, 465), "trace.jsonl 逐步结构化日志", 16, False, C_GRAY)
    center(d, (60, 465, 400, 505), "trace.html 可视化回放", 16, False, C_GRAY)
    center(d, (60, 505, 400, 545), "护栏事件 / token / 耗时统计", 16, False, C_GRAY)
    text(d, (70, 548), "每一步模型决策与工具返回都可回放", 14, False, C_GRAY)

    # 模型路由
    rrect(d, (60, 875, 780, 1005), fill=(248, 250, 252), outline=C_BORDER)
    center(d, (60, 875, 780, 925), "模型路由与降级", 21, True, C_NAVY)
    center(d, (60, 930, 780, 965), "主：DeepSeek v4-pro（执行）/ flash（规划·复核）", 15, False, C_GRAY)
    center(d, (60, 965, 780, 1000), "备：OpenAI 兼容中转站，主接口故障自动切换", 15, False, C_GRAY)

    path = os.path.join(ASSETS, "architecture.png")
    img.save(path)
    return path


def grouped_bar(path, title, labels, series, ylabel="", width=1200, height=620, fmt=None):
    img = Image.new("RGB", (width, height), C_WHITE)
    d = ImageDraw.Draw(img)
    text(d, (60, 34), title, 26, True, C_NAVY)
    if ylabel:
        text(d, (60, 76), ylabel, 15, False, C_GRAY)
    ml, mr, mt, mb = 110, 40, 120, 110
    pw, ph = width - ml - mr, height - mt - mb
    vals = [v for s in series for v in s["values"]]
    vmax = max(vals) * 1.15 if max(vals) > 0 else 1
    colors = [C_BLUE, C_GRAY, C_GREEN]
    for t in range(6):
        y = mt + ph - ph * t / 5
        d.line([(ml, y), (ml + pw, y)], fill=(226, 232, 240), width=1)
        text(d, (ml - 12, y), fmt(t * vmax / 5) if fmt else "%g" % (t * vmax / 5), 14, False, C_GRAY, anchor="rm")
    n, k = len(labels), len(series)
    group_w = pw / n * 0.7
    bar_w = group_w / k
    for i, lab in enumerate(labels):
        for j, s in enumerate(series):
            v = s["values"][i]
            x = ml + pw / n * i + (pw / n - group_w) / 2 + j * bar_w
            y = mt + ph - ph * max(v, 0) / vmax
            d.rounded_rectangle([x, y, x + bar_w - 6, mt + ph], radius=4, fill=colors[j % len(colors)])
            text(d, (x + (bar_w - 6) / 2, y - 8), fmt(v) if fmt else "%g" % v, 13, False, C_NAVY, anchor="mb")
        text(d, (ml + pw / n * (i + 0.5), mt + ph + 18), lab, 15, False, C_GRAY, anchor="ma")
    lx = ml
    for j, s in enumerate(series):
        d.rectangle([lx, height - 52, lx + 16, height - 36], fill=colors[j % len(colors)])
        text(d, (lx + 24, height - 56), s["name"], 15, False, C_NAVY)
        lx += 40 + d.textlength(s["name"], font=font(15))
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


def trace_timeline(path, trace_jsonl, width=1200, max_steps=26):
    recs = []
    with open(trace_jsonl, encoding="utf-8") as f:
        for line in f:
            recs.append(json.loads(line))
    recs = recs[:max_steps]
    row_h = 46
    height = 120 + row_h * len(recs) + 40
    img = Image.new("RGB", (width, height), C_WHITE)
    d = ImageDraw.Draw(img)
    text(d, (60, 30), "运行轨迹 Trace（真实执行日志时间线）", 26, True, C_NAVY)
    text(d, (60, 72), "每一行对应 trace.jsonl 中的一条记录：模型决策 / 工具调用 / 护栏事件", 15, False, C_GRAY)
    colors = {"user": C_BLUE, "llm": C_PURPLE, "tool": C_GREEN, "guard": (220, 38, 38),
              "system": (8, 145, 178), "final": C_NAVY}
    labels = {"user": "用户", "llm": "模型", "tool": "工具", "guard": "护栏",
              "system": "规划/复核", "final": "回答"}
    y = 110
    for i, r in enumerate(recs):
        kind = r.get("kind", "")
        color = colors.get(kind, C_GRAY)
        d.line([(150, y), (150, y + row_h)], fill=(226, 232, 240), width=2)
        d.ellipse([(142, y + 12), (158, y + 28)], fill=color)
        text(d, (60, y + 12), "步骤%02d" % r.get("step", i + 1), 14, False, C_GRAY)
        tag = labels.get(kind, kind)
        tw = d.textlength(tag, font=font(14))
        d.rounded_rectangle([178, y + 8, 178 + tw + 22, y + 32], radius=10, fill=color)
        text(d, (178 + 11, y + 20), tag, 14, True, C_WHITE, anchor="lm")
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
        text(d, (320, y + 16), _short(desc, 78), 15, False, (51, 65, 85))
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