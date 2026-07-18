"""
P0 11 项验收脚本 - 跑全
需要 server 已启动 + CAPTCHA_DEV_PEEK=true + SMS_DEV_PEEK=true
"""
import json
import re
import statistics
import sys
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
results = []  # (id, name, ok, detail)


def http(method, path, body=None, headers=None):
    url = BASE + path
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json", **(headers or {})})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read().decode("utf-8", errors="replace")
            return r.status, b, time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", errors="replace")
        return e.code, b, time.perf_counter() - t0


def get_captcha_code():
    """拿一组图验 (id, code) - 仅 dev 模式可用"""
    code, body, _ = http("GET", "/api/captcha")
    if code != 200:
        raise RuntimeError(f"captcha gen fail: {code} {body}")
    cap = json.loads(body)
    code2, body2, _ = http("POST", "/api/captcha/dev-peek", {"code_id": cap["code_id"], "code": ""})
    if code2 != 200:
        raise RuntimeError(f"dev-peek fail: {code2} {body2}")
    peek = json.loads(body2)
    if not peek.get("code"):
        raise RuntimeError(f"no code peek: {peek}")
    return cap["code_id"], peek["code"]


def send_sms(mobile, purpose):
    """发短信 + 拿 sms_token (verify-code 后)"""
    cid, ccode = get_captcha_code()
    code, body, _ = http("POST", "/api/sms/send-code", {
        "mobile": mobile, "purpose": purpose,
        "captcha_id": cid, "captcha_code": ccode,
    })
    if code != 200:
        return None, f"send-code fail: {code} {body[:200]}"
    # dev peek sms
    code2, body2, _ = http("POST", "/api/sms/dev-peek", {"mobile": mobile, "purpose": purpose})
    if code2 != 200:
        return None, f"sms dev-peek fail: {code2} {body2}"
    peek = json.loads(body2)
    sms_code = peek.get("code")
    if not sms_code:
        return None, f"no sms code: {peek}"
    # verify-code
    code3, body3, _ = http("POST", "/api/sms/verify-code", {
        "mobile": mobile, "code": sms_code, "purpose": purpose,
    })
    if code3 != 200:
        return None, f"verify fail: {code3} {body3[:200]}"
    v = json.loads(body3)
    return v.get("sms_token"), None


def reg(mobile, password, sms_token, policy_agreed=True):
    return http("POST", "/api/register", {
        "mobile": mobile, "password": password,
        "sms_token": sms_token, "policy_agreed": policy_agreed,
    })


def login(mobile, password=None):
    body = {"mobile": mobile}
    if password is not None:
        body["password"] = password
    return http("POST", "/api/login", body)


def forgot_reset(mobile, new_password, sms_token):
    return http("POST", "/api/forgot/reset", {
        "mobile": mobile, "new_password": new_password, "sms_token": sms_token,
    })


def record(idx, name, ok, detail=""):
    results.append((idx, name, ok, detail))
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} #{idx} {name}: {detail}", flush=True)


def header(title):
    print(flush=True)
    print("=" * 70, flush=True)
    print(title, flush=True)
    print("=" * 70, flush=True)


# 唯一 mobile 生成器 (避免重跑冲突) - 11 位
_BASE = int(time.time()) % 100000
def M(suffix):
    n = (_BASE * 31 + suffix) % 100000000  # 8 digits
    return f"139{n:08d}"


# ============================================================
# 验收 11: 盲点 3 - /metrics
# ============================================================
header("验收 11: 盲点 3 - /metrics 暴露")
code, body, _ = http("GET", "/metrics")
if code == 200 and "register_total" in body and "bcrypt_duration_seconds" in body and "quote_total" in body:
    record(11, "盲点 3 指标", True, f"/metrics 200, 包含 register_total/bcrypt/quote_total")
else:
    record(11, "盲点 3 指标", False, f"code={code} body={body[:200]}")


# ============================================================
# 验收 1: P0-1 服务端图验
# ============================================================
header("验收 1: P0-1 服务端图验")
# 1.1 GET /api/captcha 返回不应含 code
code, body, _ = http("GET", "/api/captcha")
j = json.loads(body)
if "code" in j or "code_value" in j or "code_text" in j:
    record(1, "P0-1 F12 拿不到码", False, f"响应含 code 字段: {j}")
else:
    record(1, "P0-1 F12 拿不到码", True, "GET /api/captcha 响应无 code/code_value/code_text")
# 1.2 改 code 后端 400 (用真实 captcha_id 但错 code)
cap = json.loads(body)
code3, body3, _ = http("POST", "/api/sms/send-code", {
    "mobile": "13800000002", "purpose": "register",
    "captcha_id": cap["code_id"], "captcha_code": "ZZZZ",
})
if code3 == 400 and "invalid_captcha" in body3:
    record(1, "P0-1 错码拦截", True, f"错码 → 400 invalid_captcha")
else:
    record(1, "P0-1 错码拦截", False, f"code={code3} body={body3[:200]}")


# ============================================================
# Setup: 注册一个测试用户
# ============================================================
header("Setup: 注册一个真实用户 for 后续测试")
test_mobile = M(1)
test_pwd = "Test1234Pass"
sms_token, err = send_sms(test_mobile, "register")
if not sms_token:
    record(0, "Setup", False, f"send_sms err: {err}")
    sys.exit(1)
code, body, _ = reg(test_mobile, test_pwd, sms_token)
if code != 200:
    record(0, "Setup", False, f"register fail: {code} {body[:200]}")
    sys.exit(1)
print(f"  Setup OK: user registered", flush=True)


# ============================================================
# 验收 2: P0-2 枚举封堵 (5 个随机号全 200, 响应无 "未注册" 字样)
# ============================================================
header("验收 2: P0-2 枚举封堵")
import random
random.seed(42)
sample_mobiles = [f"139{random.randint(10000000, 99999999):08d}" for _ in range(5)]

results_2 = []
for m in sample_mobiles:
    # 拿 sms_token (注册路径) - 不管是否注册都尝试
    sms_token, err = send_sms(m, "reset")
    if sms_token:
        code, body, _ = forgot_reset(m, "NewPass1234", sms_token)
    else:
        code, body, _ = forgot_reset(m, "NewPass1234", "INVALID_TOKEN")
    results_2.append((code, body))
    time.sleep(0.3)

# 关注: 凡是 sms_token 拿到的(对未注册用户也是 200,这是 mock 实际会发码)
# 关键是响应都是 200 (或 429 - 也算无信息泄漏)
all_ok = all(r[0] in (200, 429) for r in results_2)
no_leak = all("未注册" not in r[1] and "user_not_found" not in r[1] for r in results_2)
detail = f"{len(sample_mobiles)} 个随机号: codes={[r[0] for r in results_2]}"
if all_ok and no_leak:
    record(2, "P0-2 枚举封堵", True, detail)
else:
    record(2, "P0-2 枚举封堵", False, f"{detail}, no_leak={no_leak}")


# ============================================================
# 验收 3: P0-3 时序对齐
# ============================================================
header("验收 3: P0-3 时序对齐")
# 已注册 vs 未注册 各跑 5 次(用不同 mobile,避开 login IP 限流)
registered_times = []
for m in [M(101), M(102), M(103), M(104), M(105)]:
    sms_token, _ = send_sms(m, "register")
    reg(m, "Test1234Pass", sms_token)
    time.sleep(0.2)
    code, _, t = login(m, password="wrong_password_xx")
    registered_times.append(t)

not_registered_times = []
for m in ["13900000091", "13900000092", "13900000093", "13900000094", "13900000095"]:
    code, _, t = login(m, password="any_password_xx")
    not_registered_times.append(t)
    time.sleep(0.2)

avg_reg = statistics.mean(registered_times) * 1000
avg_not = statistics.mean(not_registered_times) * 1000
diff = abs(avg_reg - avg_not)
print(f"  已注册 avg={avg_reg:.1f}ms, 未注册 avg={avg_not:.1f}ms, 差={diff:.1f}ms", flush=True)
record(3, "P0-3 时序对齐", diff < 50, f"差 {diff:.1f}ms (要求 < 50ms, 旧版 80ms vs 2ms)")


# ============================================================
# 验收 4: P0-4 三层限流
# ============================================================
header("验收 4: P0-4 三层限流")
# 用 register 接口, register_ip_limit=10/min, sleep 1.1s 慢攻击
# 15 个不同 mobile 发起 register
ok_count = 0
rate_limited_count = 0
attack_results = []
attack_mobile_base = 13900999000
for i in range(15):
    m = f"{attack_mobile_base + i:011d}"
    sms_token, err = send_sms(m, "register")
    if not sms_token:
        attack_results.append(("sms_fail", err))
        rate_limited_count += 1
        continue
    code, body, _ = reg(m, "Test1234Pass", sms_token)
    if code == 429:
        rate_limited_count += 1
        attack_results.append(("429", body[:80]))
    elif code == 200:
        ok_count += 1
        attack_results.append(("200", "ok"))
    else:
        attack_results.append((str(code), body[:80]))
    time.sleep(1.1)  # 慢攻击绕过 1QPS

print(f"  ok={ok_count}, rate_limited={rate_limited_count}, total=15", flush=True)
print(f"  samples: {attack_results[:3]} ... {attack_results[-2:]}", flush=True)
record(4, "P0-4 三层限流", rate_limited_count >= 1, f"15 次中 {rate_limited_count} 次被限流, {ok_count} 次成功")


# ============================================================
# 验收 5: P0-5 JWT 改密失效
# ============================================================
header("验收 5: P0-5 JWT 改密失效")
new_mobile = M(2)
# 等限流清 (P0-4 用了 15 次)
print("  sleeping 65s to clear rate limits...", flush=True)
time.sleep(65)
sms_token, err = send_sms(new_mobile, "register")
if not sms_token:
    record(5, "P0-5 JWT 改密失效", False, f"send_sms err: {err}")
else:
    code, body, _ = reg(new_mobile, "Test1234Pass", sms_token)
    if code != 200:
        record(5, "P0-5 JWT 改密失效", False, f"register fail: {code} {body[:200]}")
        sys.exit(0)
    auth = json.loads(body)
    old_token = auth["token"]
old_user_id = auth["user_id"]

# 测旧 token 调 quote
quote_body = {
    "area": 100, "layout": 3, "grade": "standard", "pack": "full",
    "style": "modern", "special": [], "district": "yuhui",
    "rooms": 3, "floor": 6, "has_elevator": True,
    "demolition_wall_area": 0, "demolition_build_area": 0,
    "user_id": old_user_id,
}
code, body, _ = http("POST", "/api/quote", quote_body, headers={"Authorization": f"Bearer {old_token}"})
quote_ok_before = (code == 200)

# 改密
sms_token2, _ = send_sms(new_mobile, "reset")
code, body, _ = forgot_reset(new_mobile, "NewPass5678", sms_token2)
reset_ok = (code == 200)

# 用旧 token 再调 quote
code2, body2, _ = http("POST", "/api/quote", quote_body, headers={"Authorization": f"Bearer {old_token}"})
if code2 == 401 and quote_ok_before and reset_ok:
    record(5, "P0-5 JWT 改密失效", True, f"改密前 200, 改密后 401")
else:
    record(5, "P0-5 JWT 改密失效", False, f"改密前 quote={code}, 改密后={code2} reset={reset_ok} body2={body2[:200]}")


# ============================================================
# 验收 6: P0-6 HTTPS 文档
# ============================================================
header("验收 6: P0-6 HTTPS 文档")
import os
doc_path = r"C:\Users\Administrator\Desktop\AI报价网_V3_HTTPS部署指南_2026-07-11.md"
doc_exists = os.path.exists(doc_path)
if doc_exists:
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()
    has_nginx = "nginx" in content.lower()
    has_ssl = "ssl" in content.lower() or "HTTPS" in content or "Let's Encrypt" in content or "certbot" in content.lower()
    has_hsts = "HSTS" in content or "Strict-Transport-Security" in content
    if has_nginx and has_ssl and has_hsts:
        record(6, "P0-6 HTTPS 文档", True, f"文档存在, 含 nginx/ssl/hsts ({len(content)} bytes)")
    else:
        record(6, "P0-6 HTTPS 文档", False, f"缺字段: nginx={has_nginx} ssl={has_ssl} hsts={has_hsts}")
else:
    record(6, "P0-6 HTTPS 文档", False, f"文件不存在: {doc_path}")


# ============================================================
# 验收 7: P0-7 三步注册
# ============================================================
header("验收 7: P0-7 三步注册")
user_a = M(3)
user_b = M(4)
sms_token_a, _ = send_sms(user_a, "register")
code, body, _ = reg(user_a, "Test1234Pass", sms_token_a)
sms_token_reset, _ = send_sms(user_a, "reset")
code, body, _ = forgot_reset(user_b, "HackPass1234", sms_token_reset)
if code == 403 and "mobile_mismatch" in body:
    record(7, "P0-7 三步注册", True, f"用 A 的 token reset B → 403 mobile_mismatch")
else:
    record(7, "P0-7 三步注册", False, f"code={code} body={body[:200]}")


# ============================================================
# 验收 8: P0-8 弱密码挡
# ============================================================
header("验收 8: P0-8 弱密码挡")
weak_mobile = M(5)
sms_token, _ = send_sms(weak_mobile, "register")
code, body, _ = reg(weak_mobile, "123456", sms_token)
if code == 422 and "weak_password" in body:
    record(8, "P0-8 弱密码 123456", True, f"密码 123456 → 422 weak_password")
else:
    record(8, "P0-8 弱密码 123456", False, f"code={code} body={body[:200]}")
weak_mobile2 = M(6)
sms_token, _ = send_sms(weak_mobile2, "register")
code, body, _ = reg(weak_mobile2, "12345678", sms_token)
if code == 422 and "weak_password" in body:
    record(8, "P0-8 黑名单弱密码 12345678", True, f"12345678 → 422 weak_password (黑名单)")
else:
    record(8, "P0-8 黑名单弱密码 12345678", False, f"code={code} body={body[:200]}")


# ============================================================
# 验收 9: 盲点 1 短信防炸
# ============================================================
header("验收 9: 盲点 1 短信防炸")
code, body, _ = http("POST", "/api/sms/send-code", {
    "mobile": M(7), "purpose": "register",
    "captcha_id": "FAKE_ID", "captcha_code": "ZZZZ",
})
if code == 400 and "invalid_captcha" in body:
    record(9, "盲点 1 短信防炸", True, f"无图验 → 400 invalid_captcha")
else:
    record(9, "盲点 1 短信防炸", False, f"code={code} body={body[:200]}")


# ============================================================
# 验收 10: 盲点 2 个保法
# ============================================================
header("验收 10: 盲点 2 个保法")
no_consent_mobile = M(8)
sms_token, _ = send_sms(no_consent_mobile, "register")
code, body, _ = http("POST", "/api/register", {
    "mobile": no_consent_mobile, "password": "Test1234Pass",
    "sms_token": sms_token, "policy_agreed": False,
})
if code == 400 and "consent" in body:
    record(10, "盲点 2 协议未勾", True, f"policy_agreed=false → 400 consent_required")
else:
    record(10, "盲点 2 协议未勾", False, f"code={code} body={body[:200]}")

import sqlite3
db_path = r"C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\data\quote.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()
try:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_consent_log'")
    if not cur.fetchone():
        record(10, "盲点 2 consent_log 表", False, "表 user_consent_log 不存在")
    else:
        cur.execute("SELECT user_id, mobile, policy_version FROM user_consent_log ORDER BY id DESC LIMIT 3")
        rows = cur.fetchall()
        if rows:
            record(10, "盲点 2 consent_log 写入", True, f"最近 3 条: {rows}")
        else:
            record(10, "盲点 2 consent_log 写入", False, "表存在但无记录")
except Exception as e:
    record(10, "盲点 2 consent_log", False, f"DB err: {e}")
finally:
    conn.close()


# ============================================================
# Summary
# ============================================================
header("Summary")
total = len(results)
passed = sum(1 for r in results if r[2])
failed = total - passed
print(f"Passed: {passed}/{total}", flush=True)
for idx, name, ok, detail in results:
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} #{idx} {name}: {detail}", flush=True)

if failed > 0:
    print(f"\nFAILED {failed} - 需要修", flush=True)
    sys.exit(1)
else:
    print(f"\n[OK] 11 项全过", flush=True)
    sys.exit(0)
