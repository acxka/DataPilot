# -*- coding: utf-8 -*-
"""合并初测与复测结果，重算评测汇总，并保存调优前后对比。"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVAL = os.path.join(ROOT, "eval")


def load_lines(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def summarize(results, mode="single", model="deepseek-v4-pro"):
    cats = {}
    for r in results:
        c = cats.setdefault(r["category"], {"n": 0, "pass": 0, "score": 0.0})
        c["n"] += 1
        c["pass"] += 1 if r.get("pass") else 0
        c["score"] += r.get("score", 0.0)
    n = len(results) or 1
    tool_calls = sum(r.get("tool_calls", 0) for r in results)
    tool_errs = sum(r.get("tool_errors", 0) for r in results)
    return {
        "mode": mode, "model": model, "questions": len(results),
        "accuracy": round(sum(1 for r in results if r.get("pass")) / n, 4),
        "avg_score": round(sum(r.get("score", 0) for r in results) / n, 4),
        "avg_steps": round(sum(r.get("steps", 0) for r in results) / n, 2),
        "avg_sql": round(sum(r.get("sql_count", 0) for r in results) / n, 2),
        "avg_tokens": int(sum(r.get("tokens", 0) for r in results) / n),
        "total_tokens": sum(r.get("tokens", 0) for r in results),
        "avg_elapsed": round(sum(r.get("elapsed", 0) for r in results) / n, 1),
        "tool_success_rate": round(1 - tool_errs / max(tool_calls, 1), 4),
        "by_category": {k: {"n": v["n"], "pass": v["pass"],
                            "accuracy": round(v["pass"] / v["n"], 4),
                            "avg_score": round(v["score"] / v["n"], 4)} for k, v in cats.items()},
        "details": results,
    }


def md(summary, title="DataPilot 评测报告"):
    lines = ["# " + title, "",
             "- 模式：%s | 模型：%s | 题量：%d" % (summary["mode"], summary["model"], summary["questions"]),
             "- 总体通过率：**%.1f%%**" % (summary["accuracy"] * 100),
             "- 平均步数：%.2f | 平均 SQL：%.2f | 平均 tokens：%d | 平均耗时：%.1fs" % (
                 summary["avg_steps"], summary["avg_sql"], summary["avg_tokens"], summary["avg_elapsed"]),
             "- 工具调用成功率：%.2f%% | 总 tokens：%d" % (summary["tool_success_rate"] * 100,
                                                        summary["total_tokens"]),
             "", "| 类别 | 题量 | 通过 | 通过率 | 平均得分 |", "|---|---|---|---|---|"]
    for k, v in summary["by_category"].items():
        lines.append("| %s | %d | %d | %.1f%% | %.2f |" % (k, v["n"], v["pass"], v["accuracy"] * 100, v["avg_score"]))
    lines += ["", "| 题号 | 类别 | 得分 | 结果 | 步数 | SQL | tokens | 耗时(s) |", "|---|---|---|---|---|---|---|---|"]
    for r in summary["details"]:
        lines.append("| %s | %s | %.2f | %s | %d | %d | %d | %.0f |" % (
            r["id"], r["category"], r.get("score", 0), "PASS" if r.get("pass") else "FAIL",
            r.get("steps", 0), r.get("sql_count", 0), r.get("tokens", 0), r.get("elapsed", 0)))
    return "\n".join(lines)


def main():
    base = load_lines(os.path.join(EVAL, "results.jsonl"))
    retest = load_lines(os.path.join(EVAL, "retest", "results.jsonl"))
    before = summarize(base)
    with open(os.path.join(EVAL, "summary_before.json"), "w", encoding="utf-8") as f:
        json.dump(before, f, ensure_ascii=False, indent=2)
    by_id = {r["id"]: r for r in base}
    for r in retest:
        by_id[r["id"]] = r
    final = [by_id[k] for k in sorted(by_id)]
    after = summarize(final)
    with open(os.path.join(EVAL, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(after, f, ensure_ascii=False, indent=2)
    with open(os.path.join(EVAL, "summary.md"), "w", encoding="utf-8") as f:
        f.write(md(after))
    with open(os.path.join(EVAL, "summary_before.md"), "w", encoding="utf-8") as f:
        f.write(md(before, "DataPilot 评测报告（调优前初测）"))
    print("初测：%d/%d = %.1f%%" % (sum(1 for r in base if r["pass"]), len(base), before["accuracy"] * 100))
    print("复测后：%d/%d = %.1f%%" % (sum(1 for r in final if r["pass"]), len(final), after["accuracy"] * 100))
    for k, v in after["by_category"].items():
        b = before["by_category"].get(k, {})
        print("  %-8s 初测 %.1f%% -> 复测 %.1f%%" % (k, b.get("accuracy", 0) * 100, v["accuracy"] * 100))
    print("平均 tokens/题：%d（初测 %d）" % (after["avg_tokens"], before["avg_tokens"]))


if __name__ == "__main__":
    main()
