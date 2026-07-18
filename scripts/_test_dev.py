"""调试"""
import json
import sys
import urllib.request
import urllib.error


def http(m, p, b=None):
    d = json.dumps(b).encode() if b else None
    req = urllib.request.Request("http://127.0.0.1:8000" + p, data=d, method=m, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


c1, b1 = http("GET", "/api/captcha")
print("captcha:", c1, b1[:200], flush=True)
cap = json.loads(b1)
cid = cap["code_id"]
c2, b2 = http("POST", "/api/captcha/dev-peek", {"code_id": cid, "code": ""})
print("peek:", c2, b2, flush=True)
c3, b3 = http("POST", "/api/sms/send-code", {"mobile": "13800001111", "purpose": "register", "captcha_id": cid, "captcha_code": json.loads(b2)["code"]})
print("send:", c3, b3, flush=True)
c4, b4 = http("POST", "/api/sms/dev-peek", {"mobile": "13800001111", "purpose": "register"})
print("sms peek:", c4, b4, flush=True)
