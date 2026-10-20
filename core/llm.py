# -*- coding: utf-8 -*-
"""OpenAI 兼容协议的 LLM 客户端：超时/重试/主备降级/token 统计。"""
import json
import socket
import time
import urllib.error
import urllib.request


class LLMError(Exception):
    pass


class LLMClient(object):
    def __init__(self, providers, timeout=120, max_retries=2, log=None):
        if not providers:
            raise LLMError("no provider configured")
        self.providers = providers
        self.timeout = timeout
        self.max_retries = max_retries
        self.log = log or (lambda *a, **k: None)
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "calls": 0}
        self.failover_events = []

    def _post(self, provider, payload):
        url = provider["base_url"].rstrip("/") + "/v1/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Authorization": "Bearer " + provider["api_key"],
            "Content-Type": "application/json",
        })
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw), time.time() - t0

    def chat(self, messages, tools=None, temperature=0.2, max_tokens=None):
        """按主备顺序调用；网络错误/5xx/429 触发重试与降级。"""
        last_err = None
        for p_index, provider in enumerate(self.providers):
            payload = {"model": provider["model"], "messages": messages,
                       "temperature": temperature, "stream": False}
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            if max_tokens:
                payload["max_tokens"] = max_tokens
            for attempt in range(self.max_retries + 1):
                try:
                    data, latency = self._post(provider, payload)
                    break
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", "ignore")[:300]
                    last_err = "%s HTTP %s: %s" % (provider["name"], e.code, detail)
                    if e.code in (400, 401, 403, 404):
                        break  # 不可重试，直接换 provider
                    self.log("[llm] 重试 %d/%d (%s)" % (attempt + 1, self.max_retries, last_err))
                    time.sleep(1.5 * (attempt + 1))
                except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
                    last_err = "%s 网络异常: %s" % (provider["name"], e)
                    self.log("[llm] 重试 %d/%d (%s)" % (attempt + 1, self.max_retries, last_err))
                    time.sleep(1.5 * (attempt + 1))
                except Exception as e:  # JSON 解析失败等
                    last_err = "%s 异常: %s" % (provider["name"], e)
                    self.log("[llm] 重试 %d/%d (%s)" % (attempt + 1, self.max_retries, last_err))
                    time.sleep(1.0)
            else:
                continue
            # 成功
            usage = data.get("usage") or {}
            self.usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.usage["total_tokens"] += usage.get("total_tokens", 0)
            self.usage["calls"] += 1
            if p_index > 0:
                self.failover_events.append({"from": self.providers[0]["name"],
                                             "to": provider["name"], "reason": last_err})
                self.log("[llm] 已降级到备用模型 %s（原因：%s）" % (provider["name"], last_err))
            msg = data["choices"][0]["message"]
            return {
                "content": msg.get("content") or "",
                "tool_calls": msg.get("tool_calls") or [],
                "usage": usage,
                "latency": round(latency, 2),
                "model": data.get("model", provider["model"]),
                "provider": provider["name"],
                "finish_reason": data["choices"][0].get("finish_reason"),
            }
        raise LLMError("所有模型均调用失败: %s" % last_err)
