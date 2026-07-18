import time
import json
import urllib.request


def http(m, p, b=None):
    d = json.dumps(b).encode() if b else None
    req = urllib.request.Request("http://127.0.0.1:8000" + p, data=d, method=m, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, str(e)


# 测试未注册 vs 已注册
print("== 未注册用户(应该走 dummy bcrypt) ==", flush=True)
for i in range(5):
    t0 = time.perf_counter()
    code, body = http("POST", "/api/login", {"mobile": "13900000999", "password": "x" * 10})
    t = (time.perf_counter() - t0) * 1000
    print(f"  {i+1}: code={code} {t:.1f}ms", flush=True)

# 注册一个测试用户
print("\n== 注册 test_p0_3_user ==", flush=True)
import sys
sys.path.insert(0, "scripts")
# 调 send_sms 流程
import urllib.request, json
def get_captcha():
    code, body = http("GET", "/api/captcha")
    cap = json.loads(body)
    c, b = http("POST", "/api/captcha/dev-peek", {"code_id": cap["code_id"], "code": ""})
    return json.loads(b)["code"], cap["code_id"]
ccode, cid = get_captcha()
c, b = http("POST", "/api/sms/send-code", {"mobile": "13900008888", "purpose": "register", "captcha_id": cid, "captcha_code": ccode})
print(f"  send: {c} {b}", flush=True)
c, b = http("POST", "/api/sms/dev-peek", {"mobile": "13900008888", "purpose": "register"})
sp = json.loads(b)
c, b = http("POST", "/api/sms/verify-code", {"mobile": "13900008888", "code": sp["code"], "purpose": "register"})
stk = json.loads(b)["sms_token"]
c, b = http("POST", "/api/register", {"mobile": "13900008888", "password": "Test1234Pass", "sms_token": stk, "policy_agreed": True})
print(f"  register: {c} {b}", flush=True)

print("\n== 已注册用户(应该走真 bcrypt) ==", flush=True)
for i in range(5):
    t0 = time.perf_counter()
    code, body = http("POST", "/api/login", {"mobile": "13900008888", "password": "wrongpassxxx"})
    t = (time.perf_counter() - t0) * 1000
    print(f"  {i+1}: code={code} {t:.1f}ms", flush=True)
