# -*- coding: utf-8 -*-
"""DataPilot CLI 入口。

用法：
  python main.py "2025年10月华东区销售额同比下滑多少？主要原因是什么？"
  python main.py --check                      # 检查模型与数据库连通性
  python main.py --mode single "问题"         # 单 Agent 模式（用于对比实验）
  python main.py                              # 多轮交互模式
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core import config
from core.agent import DataPilotAgent
from core.llm import LLMClient, LLMError
from core.multiagent import TeamOrchestrator
from core.trace import Trace
from core.tools import ToolBox


def make_run_dir(question):
    slug = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", question)[:30].strip("-") or "run"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    d = os.path.join(config.RUNS_DIR, "%s-%s" % (stamp, slug))
    os.makedirs(d, exist_ok=True)
    return d


def check():
    print("[1/2] 检查数据库 ...")
    if not os.path.exists(config.db_path()):
        print("  x 数据库不存在，请先运行 python data/build_db.py")
        return 1
    import sqlite3
    conn = sqlite3.connect(config.db_path())
    n = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()
    print("  ok retail.db 可用，orders 表 %d 行" % n)
    print("[2/2] 检查模型接口 ...")
    provs = config.providers()
    print("  可用 provider: %s" % ", ".join("%s(%s)" % (p["name"], p["model"]) for p in provs))
    llm = LLMClient(provs, max_retries=1)
    resp = llm.chat([{"role": "user", "content": "只回复两个字：正常"}], temperature=0)
    print("  ok %s 调用成功：%r（%.2fs, %s tokens）" % (resp["provider"], resp["content"][:20],
                                                   resp["latency"], resp["usage"].get("total_tokens")))
    return 0


def ask(question, max_steps=None, quiet=False, mode="team"):
    run_dir = make_run_dir(question)
    trace = Trace(run_dir, question=question)
    llm = LLMClient(config.providers(), timeout=180, max_retries=2,
                    log=(lambda m: None) if quiet else print)
    max_steps = max_steps or config.MAX_STEPS
    toolbox = ToolBox(config.db_path(), run_dir, trace=trace)
    try:
        if mode == "single":
            agent = DataPilotAgent(llm, toolbox, trace, max_steps=max_steps)
            result = agent.run(question)
        else:
            fast_llm = LLMClient(config.fast_providers(), timeout=120, max_retries=2,
                                 log=(lambda m: None) if quiet else print)
            orch = TeamOrchestrator(llm, toolbox, trace, max_steps=max_steps, fast_llm=fast_llm)
            result = orch.run(question)
    finally:
        toolbox.close()
    print("\n" + "=" * 78)
    print(result["answer"])
    print("=" * 78)
    print("\n运行摘要：%d 步 · %d 次工具调用（%d 条 SQL）· 耗时 %.1fs · %d tokens · 轨迹 %s"
          % (result["steps"], result["tool_calls"], result["sql_count"], result["elapsed"],
             result["usage"].get("total_tokens", 0), os.path.relpath(result.get("html", ""), config.ROOT)))
    if result.get("charts"):
        print("图表：%s" % ", ".join(os.path.relpath(c, config.ROOT) for c in result["charts"]))
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)
    return result


def repl(max_steps=None, mode="team"):
    print("DataPilot 交互模式（输入 exit 退出）。示例：2025年10月华东区销售额同比下滑多少？")
    while True:
        try:
            q = input("\n你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if q.lower() in ("exit", "quit", "q"):
            break
        if not q:
            continue
        ask(q, max_steps, mode=mode)


def main():
    parser = argparse.ArgumentParser(description="DataPilot 企业运营数据分析智能体")
    parser.add_argument("question", nargs="?", help="要分析的业务问题")
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--mode", choices=["team", "single"], default="team",
                        help="team=规划/执行/复核多智能体；single=单 Agent 对照")
    parser.add_argument("--check", action="store_true", help="检查环境与接口连通性")
    parser.add_argument("--quiet", action="store_true", help="不打印中间步骤")
    args = parser.parse_args()
    if args.check:
        sys.exit(check())
    if args.question:
        ask(args.question, args.max_steps, args.quiet, args.mode)
    else:
        repl(args.max_steps, args.mode)


if __name__ == "__main__":
    try:
        main()
    except LLMError as e:
        print("模型调用失败：%s" % e)
        sys.exit(2)