# -*- coding: utf-8 -*-
"""演示：模糊问题下的多轮澄清（模拟用户回答），并保存轨迹。

运行：python eval/demo_clarify.py
输出：eval/clarify_demo.json + runs/<时间戳>/trace.html
"""
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("MAX_STEPS", "6")

from core import config                      # noqa: E402
from core.agent import DataPilotAgent        # noqa: E402
from core.llm import LLMClient               # noqa: E402
from core.multiagent import TeamOrchestrator  # noqa: E402
from core.tools import ToolBox               # noqa: E402
from core.trace import Trace                 # noqa: E402

QUESTION = "最近生意怎么样？"
CANNED = "按 2025 年 10 月、全公司范围来看。"


def main():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(ROOT, "runs", stamp + "-clarify-demo")
    os.makedirs(run_dir, exist_ok=True)
    trace = Trace(run_dir, question=QUESTION)
    llm = LLMClient(config.providers(), timeout=180, max_retries=2)
    toolbox = ToolBox(config.db_path(), run_dir, trace=trace,
                      asker=lambda q, opts: CANNED)
    turns = []

    def asker(q, opts):
        turns.append({"agent_question": q, "options": opts, "user_answer": CANNED})
        trace.add("user", text="【模拟用户回答】" + CANNED)
        return CANNED
    toolbox.asker = asker
    try:
        agent = DataPilotAgent(llm, toolbox, trace, max_steps=int(os.environ["MAX_STEPS"]))
        result = agent.run(QUESTION)
    finally:
        toolbox.close()
    out = {
        "question": QUESTION,
        "clarify_turns": turns,
        "answer": result["answer"],
        "steps": result["steps"], "sql_count": result["sql_count"],
        "tokens": result["usage"].get("total_tokens", 0),
        "elapsed": result["elapsed"],
        "trace_html": os.path.join(run_dir, "trace.html"),
    }
    with open(os.path.join(ROOT, "eval", "clarify_demo.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("澄清轮次：", len(turns))
    for t in turns:
        print("  Agent 问：", t["agent_question"])
        print("  用户答：", t["user_answer"])
    print("步数：%d | SQL：%d | tokens：%d | 耗时：%.1fs" % (
        out["steps"], out["sql_count"], out["tokens"], out["elapsed"]))
    print("答案节选：", out["answer"][:300].replace("\n", " "))


if __name__ == "__main__":
    main()
