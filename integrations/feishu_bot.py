# -*- coding: utf-8 -*-
"""DataPilot 飞书机器人：用飞书「事件订阅-长连接」把 Agent 接到真实 IM 场景。

架构：
  飞书服务器 --(WebSocket 长连接)--> FeishuBot（本文件）
    ├─ 收到 im.message.receive_v1 事件 → 立即 ACK（3 秒内）→ 入队
    ├─ 工作线程：先回「正在分析」，再调用 DataPilot Agent 分析，最后回结论
    └─ 分析轨迹写入 runs/feishu/<时间戳>/

零第三方依赖：WebSocket 与 Protobuf 均为标准库手写实现。
运行：python integrations/feishu_bot.py
"""
import json
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from core import config                      # noqa: E402
from core.agent import DataPilotAgent        # noqa: E402
from core.llm import LLMClient               # noqa: E402
from core.multiagent import TeamOrchestrator  # noqa: E402
from core.tools import ToolBox               # noqa: E402
from core.trace import Trace                 # noqa: E402
from integrations.feishu_api import FeishuAPI, FeishuAPIError  # noqa: E402
from integrations.feishu_proto import decode_frame, encode_frame  # noqa: E402
from integrations.feishu_ws import WebSocket, WebSocketError  # noqa: E402

ENDPOINT = "https://open.feishu.cn/callback/ws/endpoint"
LOG_DIR = os.path.join(ROOT, "runs", "feishu")
MAX_REPLY_CHARS = 6000


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "bot.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def get_ws_endpoint(app_id, app_secret):
    body = json.dumps({"AppID": app_id, "AppSecret": app_secret}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "locale": "zh"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    if data.get("code") != 0:
        raise RuntimeError("获取长连接地址失败：code=%s msg=%s" % (data.get("code"), data.get("msg")))
    d = data.get("data") or {}
    return d.get("URL"), (d.get("ClientConfig") or {})


def clean_text(text):
    """去掉飞书 @ 占位符与多余空白，并把 Markdown 粗体转成纯文本。"""
    text = re.sub(r"@_user_\d+", " ", text or "")
    text = text.replace("**", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class FeishuBot(object):
    def __init__(self):
        config.load_env()
        self.app_id = os.environ.get("FEISHU_APP_ID", "").strip()
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "").strip()
        if not self.app_id or not self.app_secret:
            raise SystemExit("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET，请写入 .env")
        self.api = FeishuAPI(self.app_id, self.app_secret)
        self.mode = os.environ.get("FEISHU_BOT_MODE", "single").strip()
        self.ws = None
        self.service_id = 0
        self.ping_interval = 90
        self.reconnect_interval = 90
        self.reconnect_nonce = 25
        self.queue = queue.Queue()
        self.seen = set()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    # ---------------- 连接管理 ----------------
    def run_forever(self):
        log("DataPilot 飞书机器人启动 | app=%s | 分析模式=%s" % (self.app_id, self.mode))
        while True:
            try:
                url, cfg = get_ws_endpoint(self.app_id, self.app_secret)
                self.ping_interval = int(cfg.get("PingInterval") or 90)
                self.reconnect_interval = int(cfg.get("ReconnectInterval") or 90)
                self.reconnect_nonce = int(cfg.get("ReconnectNonce") or 25)
                log("长连接地址已获取，开始连接…")
                self._connect_and_serve(url)
            except KeyboardInterrupt:
                log("收到退出信号")
                return
            except Exception as e:
                log("连接异常：%s，%.0f 秒后重连" % (e, self.reconnect_interval))
                time.sleep(self.reconnect_interval)

    def _connect_and_serve(self, url):
        self.ws = WebSocket(url, timeout=30)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.service_id = int((q.get("service_id") or ["0"])[0])
        log("已连接飞书长连接（service_id=%s，心跳 %ss）" % (self.service_id, self.ping_interval))
        # 关键：连接建立后立刻发送第一个 ping，服务端据此把连接注册到应用（官方 SDK 也是立即发送）
        try:
            self.ws.send(encode_frame(service=self.service_id, method=0, headers=[("type", "ping")]))
            log("已发送首个心跳 ping（注册连接）")
        except Exception as e:
            log("首个心跳发送失败：%s" % e)
        stop = threading.Event()

        def ping_loop():
            while not stop.wait(self.ping_interval):
                try:
                    self.ws.send(encode_frame(service=self.service_id, method=0,
                                              headers=[("type", "ping")]))
                    log("已发送心跳 ping")
                except Exception as e:
                    log("心跳发送失败：%s" % e)
                    return
        threading.Thread(target=ping_loop, daemon=True).start()
        try:
            while True:
                data = self.ws.recv()
                log("收到长连接下行帧：%d bytes" % len(data))
                self._handle_frame(data)
        finally:
            stop.set()
            try:
                self.ws.close()
            except Exception:
                pass

    # ---------------- 帧处理 ----------------
    def _handle_frame(self, raw):
        frame = decode_frame(raw)
        headers = frame.get("headers") or {}
        kind = headers.get("type") or ""
        method = frame.get("method")
        log("收到帧：method=%s type=%s headers=%s payload_len=%d" % (
            method, kind, ",".join(sorted(headers.keys())), len(frame.get("payload") or b"")))
        if method == 0:  # control
            if kind == "pong":
                pl = frame.get("payload") or b""
                if pl:
                    try:
                        cfg = json.loads(pl.decode("utf-8"))
                        self.ping_interval = int(cfg.get("PingInterval") or self.ping_interval)
                    except Exception:
                        pass
            return
        # data 帧：立即 ACK（飞书要求 3 秒内响应），再异步处理
        if kind == "event":
            self._ack(frame)
            payload = frame.get("payload") or b""
            try:
                event = json.loads(payload.decode("utf-8"))
            except Exception as e:
                log("事件解析失败：%s" % e)
                return
            self._enqueue(event)
        elif kind == "card":
            self._ack(frame)

    def _ack(self, frame):
        headers = dict(frame.get("headers") or {})
        headers["biz_rt"] = "1"
        ack = {"code": 200}
        try:
            self.ws.send(encode_frame(seq_id=frame.get("seq", 0), log_id=frame.get("log_id", 0),
                                      service=frame.get("service", 0), method=frame.get("method", 1),
                                      headers=list(headers.items()),
                                      payload=json.dumps(ack).encode()))
        except Exception as e:
            log("ACK 发送失败：%s" % e)

    # ---------------- 事件排队 ----------------
    def _enqueue(self, event):
        header = event.get("header") or {}
        body = event.get("event") or {}
        sender = body.get("sender") or {}
        message = body.get("message") or {}
        log("事件：type=%s sender_type=%s msg_type=%s" % (
            header.get("event_type"), sender.get("sender_type"), message.get("message_type")))
        if header.get("event_type") != "im.message.receive_v1":
            return
        if sender.get("sender_type") != "user":
            return
        msg_id = message.get("message_id")
        if not msg_id or msg_id in self.seen:
            return
        self.seen.add(msg_id)
        if len(self.seen) > 500:
            self.seen = set(list(self.seen)[-200:])
        if message.get("message_type") != "text":
            self.api_reply(msg_id, "目前只支持文本提问，请直接输入你的业务问题～")
            return
        try:
            content = json.loads(message.get("content") or "{}")
        except Exception:
            content = {}
        text = clean_text(content.get("text") or "")
        if not text:
            return
        chat_id = message.get("chat_id") or ""
        log("收到问题（chat=%s）：%s" % (chat_id, text))
        self.queue.put({"message_id": msg_id, "chat_id": chat_id, "text": text})

    def api_reply(self, message_id, text):
        try:
            self.api.reply_text(message_id, text[:MAX_REPLY_CHARS])
        except FeishuAPIError as e:
            log("回复失败：%s" % e)

    def api_send(self, chat_id, text):
        try:
            self.api.send_text(chat_id, text[:MAX_REPLY_CHARS])
        except FeishuAPIError as e:
            log("发送失败：%s" % e)

    # ---------------- 工作线程 ----------------
    def _worker_loop(self):
        while True:
            item = self.queue.get()
            try:
                self._process(item)
            except Exception as e:
                log("处理异常：%s\n%s" % (e, traceback.format_exc()[-800:]))
                self.api_reply(item["message_id"], "分析过程出错：%s\n请换个问法或稍后重试。" % e)
            finally:
                self.queue.task_done()

    def _process(self, item):
        text = item["text"]
        self.api_reply(item["message_id"], "收到，正在分析：「%s」\n预计 1-2 分钟，请稍候～" % text[:60])
        t0 = time.time()
        try:
            result = self.analyze(text)
        except Exception as e:
            self.api_reply(item["message_id"], "分析失败：%s" % e)
            return
        answer = clean_text(result.get("answer") or "").strip()
        usage = result.get("usage") or {}
        footer = "\n\n—— DataPilot | %d 步 · %d 条 SQL · %.0f 秒 · %s tokens" % (
            result.get("steps", 0), result.get("sql_count", 0), time.time() - t0,
            usage.get("total_tokens", 0))
        body = answer or "（未生成结论）"
        if len(body) + len(footer) > MAX_REPLY_CHARS:
            body = body[:MAX_REPLY_CHARS - len(footer) - 20] + "\n…（内容已截断）"
        self.api_reply(item["message_id"], body + footer)
        log("已回复（%.0fs，%d tokens）：%s" % (time.time() - t0, usage.get("total_tokens", 0), text))

    def analyze(self, question):
        slug = re.sub(r"[^\w\u4e00-\u9fa5]+", "-", question)[:24].strip("-") or "q"
        run_dir = os.path.join(LOG_DIR, time.strftime("%Y%m%d-%H%M%S") + "-" + slug)
        os.makedirs(run_dir, exist_ok=True)
        trace = Trace(run_dir, question=question, quiet=True)
        llm = LLMClient(config.providers(), timeout=180, max_retries=2)
        toolbox = ToolBox(config.db_path(), run_dir, trace=trace)
        try:
            if self.mode == "team":
                fast = LLMClient(config.fast_providers(), timeout=120, max_retries=2)
                orch = TeamOrchestrator(llm, toolbox, trace, max_steps=config.MAX_STEPS,
                                        max_repair=1, fast_llm=fast)
                result = orch.run(question)
            else:
                agent = DataPilotAgent(llm, toolbox, trace, max_steps=config.MAX_STEPS)
                result = agent.run(question)
        finally:
            toolbox.close()
        log("分析完成：%s" % os.path.relpath(run_dir, ROOT))
        return result


def main():
    bot = FeishuBot()
    bot.run_forever()


if __name__ == "__main__":
    main()