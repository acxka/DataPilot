# -*- coding: utf-8 -*-
"""反向验证：让机器人主动按邮箱给用户发一条消息（验证应用租户/权限/可用范围）。"""
import json, sys, urllib.request

def load_env(path='datapilot/.env'):
    env = {}
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); env[k.strip()] = v.strip()
    return env

env = load_env()
body = json.dumps({'app_id': env['FEISHU_APP_ID'], 'app_secret': env['FEISHU_APP_SECRET']}).encode()
req = urllib.request.Request('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                             data=body, headers={'Content-Type': 'application/json'}, method='POST')
token = json.loads(urllib.request.urlopen(req, timeout=20).read().decode())['tenant_access_token']
print('token ok')

email = sys.argv[1]
text = sys.argv[2] if len(sys.argv) > 2 else 'DataPilot 已上线：这是一条连通性测试消息，收到后请直接回复我一个问题。'
payload = {'receive_id': email, 'msg_type': 'text',
           'content': json.dumps({'text': text}, ensure_ascii=False)}
req = urllib.request.Request('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=email',
                             data=json.dumps(payload).encode(),
                             headers={'Content-Type': 'application/json',
                                      'Authorization': 'Bearer ' + token}, method='POST')
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        print('发送结果:', r.read().decode()[:600])
except urllib.error.HTTPError as e:
    print('发送失败 HTTP', e.code, e.read().decode('utf-8', 'ignore')[:600])