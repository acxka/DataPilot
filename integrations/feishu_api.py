# -*- coding: utf-8 -*-
"""飞书开放平台 HTTP API 封装：tenant_access_token、回复消息、发送消息。"""
import json
import time
import urllib.error
import urllib.request

DOMAIN = "https://open.feishu.cn"


class FeishuAPIError(Exception):
    pass


class FeishuAPI(object):
    def __init__(self, app_id, app_secret, domain=DOMAIN):
        self.app_id = app_id
        self.app_secret = app_secret
        self.domain = domain.rstrip("/")
        self._token = None
        self._token_expire = 0

    def _post(self, path, payload, with_token=True):
        url = self.domain + path
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if with_token:
            headers["Authorization"] = "Bearer " + self.tenant_token()
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise FeishuAPIError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:300]))
        except Exception as e:
            raise FeishuAPIError("%s: %s" % (type(e).__name__, e))
        if data.get("code") not in (0, None):
            raise FeishuAPIError("code=%s msg=%s" % (data.get("code"), data.get("msg")))
        return data

    def tenant_token(self):
        if self._token and time.time() < self._token_expire - 60:
            return self._token
        data = self._post("/open-apis/auth/v3/tenant_access_token/internal",
                          {"app_id": self.app_id, "app_secret": self.app_secret}, with_token=False)
        self._token = data["tenant_access_token"]
        self._token_expire = time.time() + int(data.get("expire", 7200))
        return self._token

    def reply_text(self, message_id, text):
        return self._post("/open-apis/im/v1/messages/%s/reply" % message_id,
                          {"content": json.dumps({"text": text}, ensure_ascii=False),
                           "msg_type": "text"})

    def send_text(self, chat_id, text):
        return self._post("/open-apis/im/v1/messages?receive_id_type=chat_id",
                          {"receive_id": chat_id, "msg_type": "text",
                           "content": json.dumps({"text": text}, ensure_ascii=False)})
