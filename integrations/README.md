# 真实 IM 前端对接（integration）

把 DataPilot Agent 接入真实 IM，作为「真实生产对接」创新加分项。**已完成飞书机器人端到端联调**
（群聊 @机器人 → 即时反馈 → 完整分析结论，见报告 3.4 与 report/assets/feishu_demo.png）。

## 飞书（自建应用 + 事件订阅长连接）

| 模块 | 说明 |
|---|---|
| `feishu_bot.py` | Bot 主程序：长连接收事件 → 3 秒内 ACK → 工作线程调用 Agent → OpenAPI 回复 |
| `feishu_ws.py` | RFC 6455 WebSocket 客户端（标准库手写）：握手、掩码帧、ping/pong、重连 |
| `feishu_proto.py` | pbbp2.Frame Protobuf 编解码（标准库手写，兼容 proto2 零值显式编码） |
| `feishu_api.py` | 飞书 OpenAPI 封装：tenant_access_token、回复/发送消息 |
| `feishu_send_email.py` | 按邮箱主动发消息（连通性排查用） |

### 运行

```bash
# .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BOT_MODE=single
python integrations/feishu_bot.py
```

飞书侧配置：创建企业自建应用 → 添加「机器人」能力 → 事件与回调选「使用长连接接收事件」并订阅
`im.message.receive_v1` → 开通 `im:message`、`im:message:send_as_bot`、`im:resource` → 发布版本。

### 联调中踩的两个坑（报告 5.1 问题 7）

1. **proto2 零值编码**：pbbp2.Frame 是 proto2 语义，`SeqID/LogID/method` 即使为 0 也必须显式编码；
   按 proto3 省略零值会导致服务端解析失败——表现为「WebSocket 能连上，但不回 pong、不推任何事件」。
   修复后与官方 SDK 序列化逐字节一致。
2. **租户平台策略**：个人「豆包账号」租户被飞书收回自建应用 OpenAPI 权限
   （`21001 Access denied due to platform policy`），换企业租户后 `tenant_access_token` 正常。

## Slack（备选，Socket Mode）

slack.com 可访问、协议为 WebSocket + JSON 信封，思路与飞书长连接一致，可在拿到 Bot / App-Level Token 后接入。
