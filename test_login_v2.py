"""登录 V2 E2E 测试 (陈浩 2026-07-11)
注册 → 登录 → 重置密码 → 老用户补设密码
"""
import requests
import json
import time

BASE = "http://localhost:8000"

def show(label, resp):
    body = ""
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:200]
    print(f"[{label}] HTTP {resp.status_code}: {json.dumps(body, ensure_ascii=False)[:300]}")

# 测试数据 - 每次唯一手机号
import random
mobile1 = f"139{random.randint(10000000, 99999999)}"
mobile2 = f"138{random.randint(10000000, 99999999)}"  # 老用户(走验证码注册的,无密码)
mobile3 = f"137{random.randint(10000000, 99999999)}"  # 已注册,补设密码
print(f"=== 测试手机号 ===\n  新用户: {mobile1}\n  老用户(无密码): {mobile2}\n  老用户(补设): {mobile3}\n")

# 1) 注册新用户
print("=== 1) /api/register 新用户注册 ===")
r = requests.post(f"{BASE}/api/register", json={
    "mobile": mobile1,
    "password": "abc123456",
    "code": "123456"
}, timeout=10)
show("register-new", r)
assert r.status_code == 200, f"register 失败: {r.text}"
reg_data = r.json()
new_uid = reg_data["user_id"]
print(f"  ✓ 新用户 user_id={new_uid}, token={reg_data['token'][:8]}...")

# 2) 重复注册 (应 409)
print("\n=== 2) /api/register 重复注册 (期望 409 user_exists) ===")
r = requests.post(f"{BASE}/api/register", json={
    "mobile": mobile1,
    "password": "abc123456",
    "code": "123456"
}, timeout=10)
show("register-dup", r)
assert r.status_code == 409, f"应 409 实际 {r.status_code}"

# 3) 密码登录
print("\n=== 3) /api/login-password 密码登录 ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile1,
    "password": "abc123456"
}, timeout=10)
show("login-pwd", r)
assert r.status_code == 200, f"login 失败: {r.text}"
login_data = r.json()
print(f"  ✓ 登录 user_id={login_data['user_id']} == {new_uid}")

# 4) 错密码
print("\n=== 4) /api/login-password 错密码 (期望 401 wrong_password) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile1,
    "password": "wrong999"
}, timeout=10)
show("login-wrong", r)
assert r.status_code == 401, f"应 401 实际 {r.status_code}"

# 5) 老用户(无密码)登录密码
print("\n=== 5) 先用 /api/login 验证码注册老用户 ===")
r = requests.post(f"{BASE}/api/login", json={
    "mobile": mobile2,
    "code": "123456"
}, timeout=10)
show("login-legacy", r)
assert r.status_code == 200
old_uid = r.json()["user_id"]

print("\n=== 6) /api/login-password 老用户无密码 (期望 401 use_legacy_login) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile2,
    "password": "abc123456"
}, timeout=10)
show("login-legacy-try-pwd", r)
assert r.status_code == 401
assert r.json()["detail"]["error"] == "use_legacy_login", f"应 use_legacy_login 实际 {r.json()}"

# 7) 老用户用 /api/register 补设密码
print("\n=== 7) /api/register 老用户补设密码 (期望 200) ===")
r = requests.post(f"{BASE}/api/register", json={
    "mobile": mobile2,
    "password": "newpass888",
    "code": "123456"
}, timeout=10)
show("register-supplement", r)
assert r.status_code == 200, f"应 200 实际 {r.status_code}"

# 8) 老用户用新密码登录
print("\n=== 8) /api/login-password 老用户新密码登录 (期望 200) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile2,
    "password": "newpass888"
}, timeout=10)
show("login-old-new-pwd", r)
assert r.status_code == 200

# 9) 重置密码
print("\n=== 9) /api/reset-password 重置密码 (期望 200) ===")
r = requests.post(f"{BASE}/api/reset-password", json={
    "mobile": mobile1,
    "code": "123456",
    "new_password": "reset999"
}, timeout=10)
show("reset", r)
assert r.status_code == 200

# 10) 用新密码登录
print("\n=== 10) /api/login-password 重置后用新密码登录 (期望 200) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile1,
    "password": "reset999"
}, timeout=10)
show("login-after-reset", r)
assert r.status_code == 200

# 11) 旧密码失败
print("\n=== 11) /api/login-password 重置后用旧密码 (期望 401) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile1,
    "password": "abc123456"
}, timeout=10)
show("login-old-after-reset", r)
assert r.status_code == 401

# 12) 校验密码 bcrypt 加密
print("\n=== 12) 校验 bcrypt 加密 ===")
import sqlite3
import os
db_path = os.path.join(os.path.dirname(__file__), "app", "data", "quote.db")
conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT mobile, password_hash FROM users WHERE mobile IN (?, ?)", (mobile1, mobile2))
rows = cur.fetchall()
conn.close()
for m, ph in rows:
    if ph:
        is_bcrypt = ph.startswith("$2b$") or ph.startswith("$2a$")
        print(f"  {m}: hash={ph[:30]}... (bcrypt={is_bcrypt})")
        assert is_bcrypt, f"密码未用 bcrypt: {ph[:20]}"
        # 验证明文
        import bcrypt
        ok = bcrypt.checkpw(b"reset999", ph.encode()) if m == mobile1 else bcrypt.checkpw(b"newpass888", ph.encode())
        assert ok, f"bcrypt 校验失败: {m}"
        print(f"    ✓ bcrypt 验证明文通过")
    else:
        print(f"  {m}: 无 password_hash (老用户)")

# 13) 校验 - mobile 太短(Pydantic 422 或业务 400 都可)
print("\n=== 13) 错误手机号 (期望 400/422) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": "12345",
    "password": "abc123456"
}, timeout=10)
show("login-bad-mobile", r)
assert r.status_code in [400, 422], f"应 400/422 实际 {r.status_code}"

# 14) 校验 - 密码太短
print("\n=== 14) 密码太短 (期望 400/422) ===")
r = requests.post(f"{BASE}/api/login-password", json={
    "mobile": "13800138000",
    "password": "123"
}, timeout=10)
show("login-short-pwd", r)
assert r.status_code in [400, 422], f"应 400/422 实际 {r.status_code}"

# 15) 重置不存在用户
print("\n=== 15) /api/reset-password 不存在用户 (期望 404) ===")
r = requests.post(f"{BASE}/api/reset-password", json={
    "mobile": "19900000000",
    "code": "123456",
    "new_password": "abc123456"
}, timeout=10)
show("reset-no-user", r)
assert r.status_code == 404

# 16) 登录后 /api/quote 跑通(模拟跳转 survey)
print("\n=== 16) 登录后 /api/quote 跑通 (验证 survey 跳转) ===")
login_token = requests.post(f"{BASE}/api/login-password", json={
    "mobile": mobile1,
    "password": "reset999"
}, timeout=10).json()["token"]
print(f"  token={login_token[:8]}...")
quote_payload = {
    "area": 89,
    "layout": "3室2厅1卫",
    "grade": "中档",
    "pack": "半包",
    "style": "现代",
    "special": [],
    "district": "蜀山区",
    "contact": "13900000000"
}
r = requests.post(f"{BASE}/api/quote", json=quote_payload, timeout=15)
show("quote", r)
assert r.status_code == 200, f"quote 失败: {r.text[:300]}"
q = r.json()
print(f"  ✓ quote total={q.get('total')}, items={len(q.get('items', []))}, source={q.get('source')}")

print("\n" + "="*60)
print("✅ 全部 16 个测试通过")
print("="*60)
print(f"新用户: {mobile1}")
print(f"老用户(补设): {mobile2}")
