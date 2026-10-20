# DataPilot · 企业运营数据分析智能体

> 《基于 AI Agent 的业务落地实操》课程大作业
> 作者：曹舟彦（202330304911，电气工程及其自动化七班）
> 提交日期：2026-10-23

DataPilot 是一个面向**区域连锁零售企业（示例：云启电器）**的运营数据分析 Agent。业务人员用自然语言提问，
Agent 会自主拆解问题、检索指标口径、编写并执行只读 SQL、交叉验证数据、生成图表，最后输出带证据链的结论与建议。

## 1. 业务背景

连锁零售企业的运营分析长期依赖“业务提需求 → 数据组写 SQL → 一周后出报表”的排队模式：

- 区域经理看完月度数据想追问一句“为什么下滑”，又要重新排队；
- 指标口径分散在多个 Excel 里，销售额是否含取消单、退货率按金额还是按件数，常常对不上；
- 临时取数占用了数据工程师 60% 以上的时间，却只产生很少的沉淀。

DataPilot 把这条链路压缩到一次对话：**提问 → 自主取数 → 交叉验证 → 归因 → 建议**，全过程留痕可审计。

## 2. 快速开始（零第三方依赖）

环境要求：Python 3.9+（仅使用标准库，无需 pip install）。

```bash
# 1. 生成示例数据库（44k 订单 / 9 张表，随机种子固定，可复现）
python data/build_db.py

# 2. 配置模型密钥
cp .env.example .env        # 填入 DEEPSEEK_API_KEY（或直接用环境变量）

# 3. 自检
python main.py --check

# 4. 开始分析
python main.py "2025年10月华东区销售额比去年同期下滑了多少？主要原因是什么？"

# 5. 接入真实 IM（飞书机器人，需配置 FEISHU_APP_ID/SECRET）
python integrations/feishu_bot.py

# 多智能体模式（默认）/ 单 Agent 对照模式
python main.py --mode team   "问题"
python main.py --mode single "问题"
python main.py --max-steps 8 "问题"
```

每次运行会在 `runs/<时间戳-问题>/` 下生成：

- `trace.jsonl`：逐步结构化轨迹（模型决策、工具调用、参数、返回、护栏事件）
- `trace.html`：可视化回放页面
- `answer.md` / `result.json` / `charts/*.svg`

## 3. 系统架构

```text
                    ┌──────────────────────────────────────────────┐
   用户自然语言问题 → │  Planner（规划 Agent）                        │
                    │  拆解子问题 / 指定指标与维度 / 识别信息缺口      │
                    └───────────────┬──────────────────────────────┘
                                    ↓ 分析计划
                    ┌──────────────────────────────────────────────┐
                    │  Executor（执行 Agent，ReAct 循环）            │
                    │  Thought → Tool Call → Observation → ...      │
                    │  工具：表结构/只读SQL/字段画像/绘图/口径检索/澄清  │
                    └───────────────┬──────────────────────────────┘
                                    ↓ 草稿结论 + 证据链
                    ┌──────────────────────────────────────────────┐
                    │  Reviewer（复核 Agent）+ 程序化数字溯源校验     │
                    │  数字是否有出处 / 口径是否正确 / 因果是否成立     │
                    └───────────────┬──────────────────────────────┘
                          fail → 带意见回退补查（最多 2 轮）
                                    ↓ pass
                             结构化结论与建议
```

## 4. 核心工具（7 个）

| 工具 | 作用 | 关键设计 |
|---|---|---|
| list_tables | 列出表与行数 | 让模型先了解数据规模，避免盲目查询 |
| describe_table | 字段定义 + 样例数据 | 防止猜错列名导致无效 SQL |
| run_sql | 执行只读 SELECT | 白名单校验、单语句、自动 LIMIT 500、8s 超时中止 |
| profile_column | 字段画像（空值率/分布） | 识别异常值与数据质量问题 |
| make_chart | 生成 SVG 图表 | 零依赖，可直接嵌入文档 |
| search_metrics | 检索指标口径库 | 12 个指标统一定义，防止口径漂移 |
| ask_user | 向用户澄清 | 缺参数时不编造条件 |

## 5. 评测

```bash
# 40 题评测集（基础聚合/多表关联/同比环比/归因分析/模糊缺参/越权注入）
python eval/run_eval.py --mode single --workers 4 --max-steps 9

# 异常与护栏测试（9 组 SQL 护栏 + 用户注入 + 数据注入 + 接口降级 + 步数保护 + 澄清 + 报错自愈）
python eval/run_exception.py
```

评测输出：`eval/summary.md`、`eval/summary.json`、`eval/exception_report.md`。

## 6. 目录结构

```text
datapilot/
├── main.py                 # CLI 入口
├── core/
│   ├── agent.py            # ReAct 执行 Agent（含上下文压缩、循环检测、注入检测）
│   ├── multiagent.py       # Planner / Reviewer / TeamOrchestrator
│   ├── tools.py            # 7 个工具的实现与 JSON Schema
│   ├── guard.py            # SQL 只读护栏
│   ├── verify.py           # 数字溯源校验（含派生数值）
│   ├── prompts.py          # System Prompt / Planner Prompt / Reviewer Prompt
│   ├── llm.py              # OpenAI 兼容客户端：重试、主备降级、token 统计
│   ├── trace.py            # JSONL + HTML 轨迹
│   ├── chart_svg.py        # 零依赖 SVG 图表
│   └── config.py           # 配置与模型路由
├── data/
│   ├── build_db.py         # 示例数据集生成器（可复现）
│   └── metric_dict.json    # 指标口径库
├── integrations/           # 真实 IM 对接：飞书机器人（长连接 + Protobuf 标准库实现）
├── eval/
│   ├── benchmark.jsonl     # 40 题评测集（含标准 SQL / 期望行为）
│   ├── run_eval.py         # 自动评测
│   └── run_exception.py    # 异常与护栏测试
└── runs/                   # 运行轨迹（不提交）
```

## 7. 设计取舍与已知局限

- **零依赖**：沙箱环境无法安装第三方包，因此全部用标准库实现；代价是图表能力较基础（手写 SVG）。
- **上下文压缩**：多轮工具调用会重复发送历史，Agent 会将较早的工具结果摘要化，控制 token 增长。
- **成本**：一次复杂分析约 8~17 万 tokens；规划/复核使用快模型（deepseek-flash）分担成本。
- **局限**：只读单库分析，不含跨库联邦查询；图表类型有限；对“举办过但未挂单”类业务事实无法从数据推断。
- **真实前端**：已接入飞书自建应用（事件订阅长连接），群聊 @机器人 即可提问并收到完整分析；长连接客户端为纯标准库实现。

## 8. 许可

课程作业用途，示例数据由脚本随机生成，不含任何真实企业或个人数据。