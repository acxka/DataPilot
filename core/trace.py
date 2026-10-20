# -*- coding: utf-8 -*-
"""运行轨迹记录：JSONL 落盘 + 终端打印 + 单文件 HTML 回放（报告截图用）。"""
import html
import json
import os
import time

BADGE = {
    "user": ("用户", "#2563eb"), "llm": ("模型", "#7c3aed"), "tool": ("工具", "#059669"),
    "guard": ("护栏", "#dc2626"), "error": ("异常", "#ea580c"), "final": ("回答", "#0f172a"),
    "system": ("规划", "#0891b2"),
}

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f1f5f9;font-family:"Microsoft YaHei","PingFang SC",sans-serif;color:#0f172a}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:20px;margin:0 0 6px}
.sub{color:#64748b;font-size:13px;margin-bottom:16px}
.q{background:#fff;border:1px solid #e2e8f0;border-left:4px solid #2563eb;padding:14px 18px;
border-radius:10px;font-size:15px;line-height:1.6}
.stats{display:flex;gap:12px;margin:16px 0 26px;flex-wrap:wrap}
.stat{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:10px 16px;min-width:110px}
.stat b{display:block;font-size:20px;color:#1d4ed8}
.stat span{font-size:12px;color:#64748b}
.step{display:flex;gap:14px}
.gutter{width:34px;display:flex;flex-direction:column;align-items:center}
.idx{width:30px;height:30px;border-radius:50%;background:#cbd5e1;color:#0f172a;font-size:12px;
display:flex;align-items:center;justify-content:center;font-weight:700}
.line{flex:1;width:2px;background:#e2e8f0;min-height:14px}
.card{flex:1;background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:12px 16px;margin-bottom:14px}
.head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.badge{color:#fff;font-size:12px;padding:2px 10px;border-radius:999px}
.meta{font-size:12px;color:#64748b}
pre{margin:6px 0;padding:10px 12px;background:#f8fafc;border:1px solid #eef2f7;border-radius:8px;
font-size:12.5px;line-height:1.55;white-space:pre-wrap;word-break:break-all;font-family:Consolas,monospace}
pre.answer{background:#f0f9ff;border-color:#bae6fd;font-size:13.5px;font-family:inherit}
pre.thought{background:#faf5ff;border-color:#e9d5ff;font-family:inherit}
.kv b{font-size:12px;color:#64748b}
footer{margin-top:28px;font-size:12px;color:#94a3b8;text-align:center}
"""


class Trace(object):
    def __init__(self, run_dir, question=None, title="DataPilot Run", quiet=False):
        self.run_dir = run_dir
        self.title = title
        self.quiet = quiet
        self.started = time.time()
        self.records = []
        self.meta = {"question": question, "started_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        os.makedirs(run_dir, exist_ok=True)
        self.jsonl_path = os.path.join(run_dir, "trace.jsonl")
        self.html_path = os.path.join(run_dir, "trace.html")
        if question:
            self.add("user", text=question)

    def add(self, kind, **payload):
        rec = {"step": len(self.records) + 1, "kind": kind,
               "ts": round(time.time() - self.started, 3)}
        rec.update(payload)
        self.records.append(rec)
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if not self.quiet:
            self._print(rec)
        return rec

    def _print(self, rec):
        label = BADGE.get(rec["kind"], (rec["kind"], "#333"))[0]
        if rec["kind"] == "tool":
            print("  [%s] %s(%s) -> %s" % (label, rec.get("name"), _short(rec.get("args")),
                                           _short(rec.get("result"))))
        elif rec["kind"] == "llm":
            tc = rec.get("tool_calls") or []
            print("  [%s] 第%d步 %d 个工具调用, %.1fs, %s tokens" % (
                label, rec.get("step_index", 0), len(tc), rec.get("latency") or 0,
                rec.get("tokens") or 0))
        elif rec["kind"] == "final":
            print("  [%s] 完成，共 %.1fs" % (label, rec.get("elapsed") or 0))
        else:
            print("  [%s] %s" % (label, _short(rec.get("text") or rec.get("reason") or "")))

    def finish(self, answer, usage, elapsed):
        self.add("final", text=answer, usage=usage, elapsed=round(elapsed, 2))
        self.meta.update({"finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                          "elapsed": round(elapsed, 2), "usage": usage})
        with open(os.path.join(self.run_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)
        with open(os.path.join(self.run_dir, "answer.md"), "w", encoding="utf-8") as f:
            f.write(answer or "")
        try:
            self.write_html()
        except Exception as e:  # HTML 生成失败不影响主流程
            print("  [warn] trace HTML 生成失败：%s" % e)
        return self.html_path

    def write_html(self):
        rows = []
        for r in self.records:
            label, color = BADGE.get(r["kind"], (r["kind"], "#475569"))
            if r["kind"] == "tool":
                body = ("<div class='kv'><b>参数</b><pre>" + html.escape(
                    json.dumps(r.get("args"), ensure_ascii=False, indent=1)) + "</pre></div>"
                        "<div class='kv'><b>返回</b><pre>" + html.escape(_pretty(r.get("result"))) + "</pre></div>")
            elif r["kind"] == "llm":
                body = "<div class='kv'><pre class='thought'>" + html.escape(
                    r.get("content") or "(仅工具调用，无文本输出)") + "</pre></div>"
                if r.get("tool_calls"):
                    body += "<div class='kv'><b>工具调用</b><pre>" + html.escape(
                        json.dumps(r["tool_calls"], ensure_ascii=False, indent=1)) + "</pre></div>"
            elif r["kind"] == "final":
                body = "<pre class='answer'>" + html.escape(r.get("text") or "") + "</pre>"
            else:
                body = "<pre>" + html.escape(r.get("text") or r.get("reason") or "") + "</pre>"
            meta = []
            if r.get("latency"):
                meta.append("%.2fs" % r["latency"])
            if r.get("tokens"):
                meta.append("%s tokens" % r["tokens"])
            if r.get("name"):
                meta.append(r["name"])
            rows.append(
                "<div class='step'><div class='gutter'><span class='idx'>" + str(r["step"]) +
                "</span><span class='line'></span></div><div class='card'><div class='head'>" +
                "<span class='badge' style='background:" + color + "'>" + label + "</span>" +
                "<span class='meta'>" + " · ".join(meta) + "</span></div>" + body + "</div></div>")

        usage = self.meta.get("usage") or {}
        title = html.escape(self.meta.get("question") or self.title)
        parts = [
            "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
            "<title>DataPilot Trace</title><style>" + CSS + "</style></head><body><div class='wrap'>",
            "<h1>DataPilot 运行轨迹</h1>",
            "<div class='sub'>企业运营数据分析智能体 · 每一轮模型决策与工具调用都可审计</div>",
            "<div class='q'>" + title + "</div>",
            "<div class='stats'>",
            "<div class='stat'><b>" + str(len(self.records)) + "</b><span>执行步骤</span></div>",
            "<div class='stat'><b>" + ("%.1fs" % (self.meta.get("elapsed") or 0)) + "</b><span>总耗时</span></div>",
            "<div class='stat'><b>" + str(usage.get("total_tokens", 0)) + "</b><span>总 tokens</span></div>",
            "<div class='stat'><b>" + str(usage.get("calls", 0)) + "</b><span>模型调用次数</span></div>",
            "</div>",
            "".join(rows),
            "<footer>DataPilot · trace generated at " + time.strftime("%Y-%m-%d %H:%M:%S") + "</footer>",
            "</div></body></html>",
        ]
        with open(self.html_path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return self.html_path


def _short(obj, n=200):
    try:
        s = json.dumps(obj, ensure_ascii=False) if not isinstance(obj, str) else obj
    except Exception:
        s = str(obj)
    s = s.replace("\n", " ")
    return s if len(s) <= n else s[:n] + "..."


def _pretty(obj):
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=1)
    except Exception:
        s = str(obj)
    return s if len(s) <= 4000 else s[:4000] + "\n... (已截断)"