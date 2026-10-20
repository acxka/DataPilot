# -*- coding: utf-8 -*-
"""DataPilot 执行 Agent：ReAct（Thought → Tool Call → Observation）+ 护栏 + 轨迹记录。

- 支持注入 Planner 的分析计划（多智能体模式）；
- 支持复核后的定向修复（repair）；
- 采用上下文压缩：历史工具结果只保留摘要，控制 token 随步数的平方增长。
"""
import json
import re
import time

from . import prompts
from .tools import TOOL_SPECS

INJECTION_PATTERNS = [
    r"忽略(之前|以上|前面)(的)?(所有)?(指令|规则|提示)",
    r"ignore\s+(all\s+)?(previous|above)\s+instructions",
    r"输出(你的)?(系统)?(提示词|prompt|system prompt)",
    r"扮演|越狱|jailbreak",
    r"drop\s+table|delete\s+from|truncate\s+table",
]

COMPACT_THRESHOLD = 45000   # 消息总字符数超过该值时触发压缩
COMPACT_KEEP_RECENT = 6     # 最近 N 条 tool 消息保留原文


def detect_injection(text):
    hits = []
    for p in INJECTION_PATTERNS:
        m = re.search(p, text or "", flags=re.I)
        if m:
            hits.append(m.group(0))
    return hits


def _shrink(result, max_rows=60, max_chars=7000):
    """压缩工具返回，避免把大结果整段塞回模型上下文（完整结果仍在 trace 里）。"""
    if isinstance(result, dict) and isinstance(result.get("rows"), list) and len(result["rows"]) > max_rows:
        result = dict(result)
        result["rows"] = result["rows"][:max_rows]
        result["note"] = (result.get("note") or "") + "（喂给模型时仅展示前 %d 行）" % max_rows
    s = json.dumps(result, ensure_ascii=False)
    if len(s) > max_chars:
        result = {"truncated": True, "preview": s[:max_chars]}
    return result


class DataPilotAgent(object):
    def __init__(self, llm, toolbox, trace, max_steps=12, log=None):
        self.llm = llm
        self.toolbox = toolbox
        self.trace = trace
        self.max_steps = max_steps
        self.log = log or (lambda *a, **k: None)
        self.messages = []
        self.answer = ""
        self.evidence = []
        self.injection_hits = []
        self.compacted_chars = 0
        self.step = 0
        self.seen = {}

    # ---------- 初始化 ----------
    def _bootstrap(self, question, plan=None):
        hits = detect_injection(question)
        if hits:
            self.injection_hits = hits
            self.trace.add("guard", action="prompt_injection_suspected", matches=hits,
                           reason="用户输入中含指令覆盖类文本，已按数据处理并继续原任务")
        system = prompts.build_system_prompt(self.toolbox.schema_text, self.max_steps)
        if plan:
            system += "\n\n# 分析计划（Planner 已制定，请按顺序执行）\n" + json.dumps(plan, ensure_ascii=False, indent=2)
        user = question
        if hits:
            user = prompts.INJECTION_HINT + "\n\n用户原始输入：\n" + question
        self.messages = [{"role": "system", "content": system},
                         {"role": "user", "content": user}]

    # ---------- 主循环 ----------
    def _loop(self, max_steps):
        final = ""
        for _ in range(max_steps):
            self.step += 1
            resp = self.llm.chat(self.messages, tools=TOOL_SPECS, temperature=0.1)
            tool_calls = resp.get("tool_calls") or []
            self.trace.add("llm", step_index=self.step, content=resp.get("content") or "",
                           tool_calls=[{"name": tc["function"]["name"],
                                        "arguments": tc["function"]["arguments"]} for tc in tool_calls],
                           latency=resp.get("latency"),
                           tokens=(resp.get("usage") or {}).get("total_tokens", 0),
                           provider=resp.get("provider"), model=resp.get("model"))
            if not tool_calls:
                final = (resp.get("content") or "").strip()
                if final:
                    break
                self.messages.append({"role": "user", "content": "请给出最终结论。"})
                continue
            self.messages.append({"role": "assistant", "content": resp.get("content") or "",
                                  "tool_calls": tool_calls})
            for tc in tool_calls:
                self._run_one_tool(tc)
            self._compact()
        return final

    def _run_one_tool(self, tc):
        name = tc["function"]["name"]
        raw_args = tc["function"].get("arguments") or "{}"
        t_tool = time.time()
        try:
            args = json.loads(raw_args)
            if not isinstance(args, dict):
                raise ValueError("参数必须是 JSON 对象")
        except Exception as e:
            args = {}
            result = {"error": "工具参数不是合法 JSON：%s。请重新生成，参数必须是 JSON 对象。" % e}
        else:
            sig = name + "::" + json.dumps(args, ensure_ascii=False, sort_keys=True)
            self.seen[sig] = self.seen.get(sig, 0) + 1
            if self.seen[sig] >= 2:
                result = {"error": "检测到重复调用（同一工具与参数已执行过），请改用不同的 SQL 或直接输出结论。"}
                self.trace.add("guard", action="loop_guard", tool=name, repeat=self.seen[sig])
            else:
                result = self.toolbox.call(name, args)
        latency = round(time.time() - t_tool, 3)
        if isinstance(result, dict) and result.get("columns") is not None and result.get("rows") is not None:
            self.evidence.append({"sql": args.get("sql", ""), "columns": result.get("columns"),
                                  "rows": result.get("rows")[:100],
                                  "row_count": result.get("row_count")})
            if len(self.evidence) > 40:
                self.evidence = self.evidence[-40:]
        self.trace.add("tool", name=name, args=args, result=result, latency=latency, step_index=self.step)
        self.messages.append({"role": "tool", "tool_call_id": tc["id"],
                              "content": json.dumps(_shrink(result), ensure_ascii=False)})

    def _compact(self):
        """上下文压缩：把较早的工具结果替换为摘要，抑制 token 随步数线性膨胀。"""
        size = sum(len(m.get("content") or "") for m in self.messages)
        if size <= COMPACT_THRESHOLD:
            return
        tool_idx = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
        targets = tool_idx[:-COMPACT_KEEP_RECENT]
        saved = 0
        for i in targets:
            content = self.messages[i].get("content") or ""
            if len(content) <= 260:
                continue
            saved += len(content) - 240
            self.messages[i]["content"] = json.dumps({
                "compacted": True,
                "summary": content[:200],
                "note": "历史查询结果已压缩，如需明细请重新查询",
            }, ensure_ascii=False)
        if saved:
            self.compacted_chars += saved
            self.trace.add("system", role="ContextCompactor",
                           text="上下文压缩：%d 条历史工具结果已摘要化，节省约 %d 字符" % (len(targets), saved))

    # ---------- 对外接口 ----------
    def _result(self, final, elapsed, mode):
        usage = dict(self.llm.usage)
        usage["failover_events"] = self.llm.failover_events
        return {"answer": final, "steps": self.step, "elapsed": round(elapsed, 2), "usage": usage,
                "run_dir": self.trace.run_dir, "charts": self.toolbox.charts,
                "sql_count": self.toolbox.sql_count, "tool_calls": self.toolbox.calls,
                "injection_hits": self.injection_hits, "compacted_chars": self.compacted_chars,
                "evidence_count": len(self.evidence), "mode": mode}

    def run(self, question, plan=None, finalize=True):
        self._bootstrap(question, plan)
        t0 = time.time()
        final = self._loop(self.max_steps)
        if not final:
            final = self._force_summary()
        self.answer = final
        elapsed = time.time() - t0
        result = self._result(final, elapsed, "team" if plan else "single")
        if finalize:
            result["html"] = self.trace.finish(final, result["usage"], elapsed)
        return result

    def repair(self, feedback, finalize=True):
        """复核未通过时，带着具体意见继续对话补查，然后重写结论。"""
        t0 = time.time()
        self.messages.append({"role": "user", "content": feedback})
        final = self._loop(max(4, self.max_steps - self.step))
        if not final:
            final = self._force_summary()
        self.answer = final
        elapsed = time.time() - t0
        result = self._result(final, elapsed, "team-repair")
        if finalize:
            result["html"] = self.trace.finish(final, result["usage"], elapsed)
        return result

    def _force_summary(self):
        self.trace.add("guard", action="max_steps", reason="达到最大步数 %d，强制生成总结" % self.max_steps)
        self.messages.append({"role": "user", "content": prompts.FORCE_SUMMARY_PROMPT})
        resp = self.llm.chat(self.messages, tools=None, temperature=0.1)
        answer = (resp.get("content") or "").strip()
        self.trace.add("llm", content=answer, provider=resp.get("provider"),
                       tokens=(resp.get("usage") or {}).get("total_tokens", 0), step_index=self.step)
        return answer