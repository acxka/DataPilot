# -*- coding: utf-8 -*-
"""多智能体协同：Planner（规划）→ Executor（执行，复用 DataPilotAgent）→ Reviewer（复核）→ 修复循环。

设计要点：
- Planner 只做任务拆解与口径选择，不接触数据，避免“边查边乱”；
- Executor 负责多步工具调用，产出草稿结论与证据链；
- Reviewer 只审“结论是否有数据支撑”，并配合程序化数字溯源校验；
- 复核不通过则带着具体问题让 Executor 补查（最多 2 轮），形成 Reflection 闭环。
"""
import json
import re
import time

from . import prompts, verify
from .agent import DataPilotAgent


class PlannerAgent(object):
    def __init__(self, llm):
        self.llm = llm

    def plan(self, question, schema):
        sys = prompts.PLANNER_PROMPT.replace("{schema}", schema)
        resp = self.llm.chat([{"role": "system", "content": sys},
                              {"role": "user", "content": question}], temperature=0.1)
        raw = resp.get("content") or ""
        plan = _parse_json(raw)
        if not plan:
            plan = {"goal": question, "sub_questions": [question], "metrics": [], "dimensions": [],
                    "ambiguity": "", "raw": raw[:600]}
        return plan, resp


class ReviewerAgent(object):
    def __init__(self, llm):
        self.llm = llm

    def review(self, question, plan, draft_answer, evidence):
        pack = _evidence_pack(evidence)
        unsupported = verify.check_answer(draft_answer, evidence)
        user = ("【原始问题】\n%s\n\n【分析计划】\n%s\n\n【执行证据（SQL 与结果）】\n%s\n\n"
                "【草稿结论】\n%s\n\n【程序化数字溯源校验结果】\n%s") % (
            question, json.dumps(plan, ensure_ascii=False)[:800], pack, draft_answer[:5000],
            json.dumps(unsupported, ensure_ascii=False)[:2000] if unsupported else "所有数字均可溯源")
        resp = self.llm.chat([{"role": "system", "content": prompts.REVIEWER_PROMPT},
                              {"role": "user", "content": user}], temperature=0.0)
        raw = resp.get("content") or ""
        verdict = _parse_json(raw) or {"verdict": "pass", "issues": [], "raw": raw[:400]}
        verdict["unsupported_numbers"] = unsupported
        verdict["_resp"] = resp
        return verdict


class TeamOrchestrator(object):
    """规划 → 执行 → 复核 → 修复 的协同流程。"""

    def __init__(self, llm, toolbox, trace, max_steps=12, max_repair=2, fast_llm=None):
        self.llm = llm
        self.fast_llm = fast_llm
        self.toolbox = toolbox
        self.trace = trace
        self.max_steps = max_steps
        self.max_repair = max_repair
        self.evidence = []
        self.result = None

    def run(self, question):
        t0 = time.time()
        planner = PlannerAgent(self.fast_llm or self.llm)
        plan, presp = planner.plan(question, self.toolbox.schema_text)
        self.trace.add("system", role="Planner",
                       text="分析计划：\n" + json.dumps(plan, ensure_ascii=False, indent=2),
                       latency=presp.get("latency"),
                       tokens=(presp.get("usage") or {}).get("total_tokens", 0))
        if plan.get("ambiguity"):
            self.trace.add("system", role="Planner", text="识别到信息缺口：%s" % plan["ambiguity"])

        executor = DataPilotAgent(self.llm, self.toolbox, self.trace, max_steps=self.max_steps)
        result = executor.run(question, plan=plan, finalize=False)
        self.evidence = executor.evidence

        reviewer = ReviewerAgent(self.fast_llm or self.llm)
        reviews = []
        for rnd in range(self.max_repair):
            verdict = reviewer.review(question, plan, result["answer"], executor.evidence)
            reviews.append(verdict)
            self.trace.add("system", role="Reviewer",
                           text="复核结论：%s\n问题：%s" % (verdict.get("verdict"),
                                                      json.dumps(verdict.get("issues"), ensure_ascii=False)),
                           latency=verdict["_resp"].get("latency"),
                           tokens=(verdict["_resp"].get("usage") or {}).get("total_tokens", 0))
            if str(verdict.get("verdict", "")).lower() == "pass" and not verdict.get("unsupported_numbers"):
                break
            issues = verdict.get("issues") or []
            hint = verdict.get("fix_hint") or ""
            feedback = ("【复核意见】你的结论存在以下问题，请针对性补充查证后重写结论（不要编造，查不到就说明）：\n- "
                        + "\n- ".join([str(i) for i in issues[:6]]) + "\n" + hint)
            result = executor.repair(feedback, finalize=False)
            self.evidence = executor.evidence
        else:
            self.trace.add("system", role="Reviewer",
                           text="已用完 %d 轮修复机会，保留当前结论并标注局限" % self.max_repair)

        elapsed = time.time() - t0
        usage = dict(self.llm.usage)
        usage["failover_events"] = self.llm.failover_events
        unsupported = verify.check_answer(result["answer"], executor.evidence)
        if unsupported:
            note = ("\n\n> 注：以下数字未能在本次查询结果中找到直接出处，请谨慎使用：%s"
                    % "、".join(str(x.get("value")) for x in unsupported[:8]))
            result["answer"] = result["answer"] + note
        html_path = self.trace.finish(result["answer"], usage, elapsed)
        result.update({"html": html_path, "elapsed": round(elapsed, 2), "usage": usage,
                       "plan": plan,
                       "reviews": [{k: v for k, v in r.items() if not k.startswith("_")} for r in reviews],
                       "unsupported_numbers": unsupported, "run_dir": self.trace.run_dir,
                       "charts": self.toolbox.charts, "sql_count": self.toolbox.sql_count,
                       "tool_calls": self.toolbox.calls, "steps": result.get("steps", 0),
                       "mode": "team"})
        return result


def _parse_json(text):
    if not text:
        return None
    text = text.strip()
    m = re.search(r"\x60{3}(?:json)?\s*(.*?)\x60{3}", text, flags=re.S)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        s, e = text.find("{"), text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                return None
    return None


def _evidence_pack(evidence, max_items=40, max_rows=3):
    out = []
    for i, ev in enumerate(evidence[-max_items:], start=1):
        rows = ev.get("rows") or []
        out.append("证据%d SQL: %s\n列: %s\n代表行(%d/%s): %s" % (
            i, ev.get("sql", "")[:320], ev.get("columns"), min(len(rows), max_rows),
            ev.get("row_count"), json.dumps(rows[:max_rows], ensure_ascii=False)[:700]))
    return "\n\n".join(out) if out else "（无查询证据）"