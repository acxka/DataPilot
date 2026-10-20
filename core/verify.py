# -*- coding: utf-8 -*-
"""数字溯源校验：最终结论里的数字都应能在 SQL 结果中找到出处（防幻觉护栏）。"""
import re

NUM_RE = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")
UNIT_MUL = {"万": 1e4, "亿": 1e8}
IGNORE_IF = re.compile(r"^(19|20)\d{2}$")


def _to_float(tok, text_after=""):
    try:
        v = float(tok.replace(",", ""))
    except Exception:
        return None
    for unit, mul in UNIT_MUL.items():
        if text_after.startswith(unit):
            v *= mul
            break
    return v


def _row_numbers(row):
    out = []
    for cell in row:
        if isinstance(cell, bool) or cell is None:
            continue
        if isinstance(cell, (int, float)):
            out.append(float(cell))
        elif isinstance(cell, str):
            try:
                out.append(float(cell.replace(",", "")))
            except Exception:
                continue
    return out


def collect_evidence_numbers(evidence):
    """收集 SQL 结果中的原始数值，以及同一行内可推导出的差值/合计/占比/同比率等派生数值。"""
    raw, derived = [], []
    for ev in evidence:
        for row in (ev.get("rows") or []):
            nums = _row_numbers(row)
            raw.extend(nums)
            for i in range(len(nums)):
                for j in range(i + 1, len(nums)):
                    a, b = nums[i], nums[j]
                    derived.extend([a - b, b - a, a + b, a * b])
                    if b:
                        derived.extend([a / b * 100, (a / b - 1) * 100, (a - b) / b * 100])
                    if a:
                        derived.extend([b / a * 100, (b / a - 1) * 100, (b - a) / a * 100])
    pool = raw + derived
    if len(pool) > 60000:
        pool = pool[:60000]
    return pool


def _matches(v, pool):
    for e in pool:
        for scale in (1.0, 100.0, 0.01, 0.1, 10.0):
            if abs(v * scale - e) <= max(abs(e) * 0.012, 0.011):
                return True
    return False


def check_answer(answer, evidence):
    """返回无法在证据中找到出处的数字列表。"""
    if not answer:
        return []
    pool = collect_evidence_numbers(evidence)
    unsupported = []
    # 屏蔽日期/时间样式，避免把 2025-10-01 拆出 10、01 之类误报
    masked = re.sub(r"\d{4}-\d{1,2}(?:-\d{1,2})?", lambda m: " " * len(m.group(0)), answer)
    for m in NUM_RE.finditer(masked):
        tok = m.group(0)
        if IGNORE_IF.match(tok):
            continue
        after = answer[m.end():m.end() + 1]
        v = _to_float(tok, after)
        if v is None:
            continue
        if _matches(v, pool):
            continue
        ctx = masked[max(0, m.start() - 24):m.end() + 6].replace("\n", " ")
        unsupported.append({"value": v, "context": ctx})
    return unsupported[:15]