# -*- coding: utf-8 -*-
"""Agent 工具集：数据库探查、只读 SQL、字段画像、SVG 图表、指标口径检索、用户澄清。"""
import json
import os
import re
import sqlite3
import time

from . import chart_svg, guard

TABLE_DESC = {
    "regions": "区域表：5 个大区及负责人",
    "stores": "门店表：12 家门店，含所属区域、城市、开业日期、面积",
    "products": "商品表：60 个 SKU，含品类/子品类/售价/成本/上市日期",
    "customers": "会员表：3000 名会员，含等级与注册区域",
    "promotions": "促销活动表：满减/专场/清仓活动，含起止日期、折扣力度、适用范围",
    "orders": "订单表：订单日期、门店、渠道（线下/线上）、状态、促销活动、订单总额",
    "order_items": "订单明细表：每个订单的商品、数量、单价、折扣、金额",
    "inventory_daily": "库存快照表：每周一快照（2025-09~11 为日快照），含库存量、缺货标记、补货量",
    "returns": "退货表：退货日期、数量、原因、退款金额",
}

TOOL_SPECS = [
    {"type": "function", "function": {
        "name": "list_tables",
        "description": "列出数据库中所有表名、中文说明和行数。分析开始前若不确定表结构，先调用它。",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "describe_table",
        "description": "查看某张表的字段定义（字段名、类型、是否可空）以及 3 行样例数据。写 SQL 前用它确认字段名，避免猜错列名。",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string", "description": "表名，如 orders"}}, "required": ["table"]}}},
    {"type": "function", "function": {
        "name": "run_sql",
        "description": "在只读数据分析库上执行一条 SELECT 查询并返回结果（最多 500 行）。所有金额、数量、比例等结论性数字都必须来自本工具的真实返回，禁止凭猜测给出数字。系统会自动拦截 INSERT/UPDATE/DELETE/DROP 等写操作和多语句。",
        "parameters": {"type": "object", "properties": {
            "sql": {"type": "string", "description": "标准 SQLite SELECT 语句"},
            "purpose": {"type": "string", "description": "一句话说明这条 SQL 要验证什么，便于审计"}},
            "required": ["sql"]}}},
    {"type": "function", "function": {
        "name": "profile_column",
        "description": "统计某个字段的数据质量画像：空值率、去重值数量、数值型的最小/最大/平均值、Top5 取值。用于判断数据可用性、识别异常值或分类字段取值。",
        "parameters": {"type": "object", "properties": {
            "table": {"type": "string"}, "column": {"type": "string"}},
            "required": ["table", "column"]}}},
    {"type": "function", "function": {
        "name": "make_chart",
        "description": "把已经查到的数据画成图表 SVG 并保存，返回文件路径。只用于展示 run_sql 已返回的真实数据，图表系列长度必须与 x_labels 一致。一般在分析完成、准备输出结论时调用 1-2 次。",
        "parameters": {"type": "object", "properties": {
            "chart_type": {"type": "string", "enum": ["bar", "line", "grouped_bar"]},
            "title": {"type": "string", "description": "图表标题"},
            "x_labels": {"type": "array", "items": {"type": "string"}},
            "series": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "values": {"type": "array", "items": {"type": "number"}}}}},
            "y_label": {"type": "string"}},
            "required": ["chart_type", "title", "x_labels", "series"]}}},
    {"type": "function", "function": {
        "name": "search_metrics",
        "description": "检索业务指标口径库（销售额/退货率/缺货率/库存周转天数/同比/环比 等 12 个指标的官方定义与计算公式）。计算关键指标前先检索，避免口径错误。",
        "parameters": {"type": "object", "properties": {
            "keyword": {"type": "string", "description": "指标名或业务关键词，如 销售额、退货率、缺货"}},
            "required": ["keyword"]}}},
    {"type": "function", "function": {
        "name": "ask_user",
        "description": "当用户问题缺少关键信息（如没给时间范围、没说明是哪个指标或区域）且无法合理假设时，向用户提问澄清。不要编造缺失条件。",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}}},
            "required": ["question"]}}},
]


def _schema_text(conn):
    lines = []
    for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        name = row[0]
        cols = conn.execute("PRAGMA table_info(%s)" % name).fetchall()
        col_txt = ", ".join("%s %s" % (c[1], c[2]) for c in cols)
        lines.append("- %s（%s）: %s" % (name, TABLE_DESC.get(name, ""), col_txt))
    return "\n".join(lines)


class ToolBox(object):
    def __init__(self, db_path, run_dir, trace=None, interactive=False, asker=None):
        self.db_path = db_path
        self.run_dir = run_dir
        self.charts_dir = os.path.join(run_dir, "charts")
        self.trace = trace
        self.interactive = interactive
        self.asker = asker
        self.calls = 0
        self.sql_count = 0
        self.charts = []
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self.schema_text = _schema_text(self._conn)

    # ---------- 工具实现 ----------
    def list_tables(self, args):
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        out = []
        for r in rows:
            n = r["name"]
            cnt = self._conn.execute("SELECT COUNT(*) FROM %s" % n).fetchone()[0]
            out.append({"table": n, "desc": TABLE_DESC.get(n, ""), "rows": cnt})
        return {"tables": out}

    def describe_table(self, args):
        table = (args.get("table") or "").strip()
        if not self._table_exists(table):
            return {"error": "表 %s 不存在，可用表：%s" % (table, self._table_names())}
        cols = self._conn.execute("PRAGMA table_info(%s)" % table).fetchall()
        sample = self._conn.execute("SELECT * FROM %s LIMIT 3" % table).fetchall()
        return {"table": table, "desc": TABLE_DESC.get(table, ""),
                "columns": [{"name": c["name"], "type": c["type"], "notnull": bool(c["notnull"])} for c in cols],
                "sample": [dict(s) for s in sample]}

    def run_sql(self, args):
        sql = args.get("sql") or ""
        ok, clean, reason = guard.validate_sql(sql)
        if not ok:
            if self.trace:
                self.trace.add("guard", reason=reason, sql=sql[:400], action="reject")
            return {"error": "SQL 被安全护栏拦截：%s。请改写为单条只读 SELECT 查询。" % reason}
        t0 = time.time()
        uri = "file:%s?mode=ro" % self.db_path.replace("\\", "/")
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        deadline = time.time() + 8.0

        def handler():
            return 1 if time.time() > deadline else 0  # 非0 = 中止
        conn.set_progress_handler(handler, 5000)
        try:
            cur = conn.execute(clean)
            rows = cur.fetchmany(guard.MAX_ROWS + 1)
            columns = [d[0] for d in cur.description] if cur.description else []
        except sqlite3.OperationalError as e:
            conn.close()
            return {"error": "SQL 执行失败：%s。请检查字段名/表名/语法后重试。" % e}
        except Exception as e:
            conn.close()
            return {"error": "SQL 执行异常：%s" % e}
        conn.close()
        truncated = len(rows) > guard.MAX_ROWS
        rows = rows[:guard.MAX_ROWS]
        elapsed = round(time.time() - t0, 3)
        self.sql_count += 1
        display_rows = [[_clean_val(v) for v in tuple(r)] for r in rows]
        return {"columns": columns, "row_count": len(display_rows), "truncated": truncated,
                "elapsed_ms": int(elapsed * 1000), "rows": display_rows[:200],
                "note": "结果已被截断为前 %d 行" % guard.MAX_ROWS if truncated else ""}

    def profile_column(self, args):
        table = (args.get("table") or "").strip()
        column = (args.get("column") or "").strip()
        if not self._table_exists(table):
            return {"error": "表 %s 不存在" % table}
        cols = [c[1] for c in self._conn.execute("PRAGMA table_info(%s)" % table).fetchall()]
        if column not in cols:
            return {"error": "字段 %s.%s 不存在，可用字段：%s" % (table, column, ", ".join(cols))}
        q = 'SELECT COUNT(*) n, COUNT("%s") nn, COUNT(DISTINCT "%s") d FROM %s' % (column, column, table)
        r = self._conn.execute(q).fetchone()
        total, nonnull, distinct = r["n"], r["nn"], r["d"]
        out = {"table": table, "column": column, "total": total,
               "null_rate": round(1 - (nonnull / total if total else 0), 4),
               "distinct": distinct}
        try:
            r2 = self._conn.execute('SELECT MIN("%s") mn, MAX("%s") mx, AVG("%s") av FROM %s'
                                    % (column, column, column, table)).fetchone()
            if r2["mn"] is not None and not isinstance(r2["mn"], str):
                out["min"], out["max"] = _clean_val(r2["mn"]), _clean_val(r2["mx"])
                out["avg"] = round(r2["av"], 2) if isinstance(r2["av"], (int, float)) else r2["av"]
        except Exception:
            pass
        top = self._conn.execute('SELECT "%s" v, COUNT(*) c FROM %s GROUP BY 1 ORDER BY 2 DESC LIMIT 5'
                                 % (column, table)).fetchall()
        out["top5"] = [[_clean_val(t["v"]), t["c"]] for t in top]
        return out

    def make_chart(self, args):
        try:
            path = chart_svg.save_svg(self.charts_dir, args.get("chart_type", "bar"),
                                      args.get("title", "chart"), args.get("x_labels") or [],
                                      args.get("series") or [], args.get("y_label", ""))
        except Exception as e:
            return {"error": "图表生成失败：%s" % e}
        rel = os.path.relpath(path, os.path.dirname(self.run_dir))
        self.charts.append(path)
        return {"ok": True, "path": rel, "abs_path": path,
                "note": "图表已保存，可在最终回答中引用该文件路径"}

    def search_metrics(self, args):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "metric_dict.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        kw = (args.get("keyword") or "").strip()
        scored = []
        for m in data["metrics"]:
            hay = (m["name"] + " " + " ".join(m.get("aliases", [])) + " " + m["definition"]).lower()
            score = sum(1 for ch in kw if ch in hay)
            if kw and (kw in hay or any(a in kw or kw in a for a in m.get("aliases", []))
                       or m["name"] in kw or kw in m["name"]):
                score += 100
            scored.append((score, m))
        scored.sort(key=lambda x: -x[0])
        hits = [m for s, m in scored if s > 0][:3] or [scored[0][1]]
        return {"keyword": kw, "matched": hits, "note": data.get("notes", "")}

    def ask_user(self, args):
        q = args.get("question") or "请补充必要信息"
        if self.asker:
            ans = self.asker(q, args.get("options") or [])
            return {"question": q, "user_answer": ans}
        return {"question": q, "options": args.get("options") or [],
                "note": "当前为非交互运行，无法获得用户回答。请基于已有信息做最合理假设，并在结论中明确说明假设。"}

    # ---------- 调度 ----------
    def call(self, name, args):
        func = getattr(self, name, None)
        if not callable(func) or name.startswith("_"):
            return {"error": "未知工具 %s" % name}
        self.calls += 1
        try:
            result = func(args or {})
        except Exception as e:
            return {"error": "工具 %s 执行异常：%s" % (name, e)}
        # 数据侧提示注入防御：净化工具返回中的指令性文本
        clean, hits = guard.sanitize_value(result)
        if hits and self.trace:
            self.trace.add("guard", action="data_injection_filtered", tool=name, hits=hits,
                           reason="工具返回内容中检测到疑似注入指令，已过滤后再交给模型")
        return clean

    def _table_exists(self, table):
        r = self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        return r is not None

    def _table_names(self):
        return [r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def _clean_val(v):
    if isinstance(v, float):
        return round(v, 2)
    if isinstance(v, bytes):
        return v.decode("utf-8", "ignore")
    return v