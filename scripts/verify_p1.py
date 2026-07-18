# -*- coding: utf-8 -*-
"""W2 P1 验收测试 - 纯 ASCII 输出"""
import requests
import json
import sys
import time

BASE = "http://127.0.0.1:8000"
passed = 0
failed = 0

def test(name, url, method="GET", data=None, headers=None, expect_code=200):
    global passed, failed
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            r = requests.post(url, json=data, headers=headers, timeout=60)
        
        ok = r.status_code == expect_code
        status = "[OK]" if ok else "[FAIL]"
        resp = json.dumps(r.json(), ensure_ascii=False)[:150]
        print(f"{status} {name}: HTTP {r.status_code} -> {resp}")
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"   期望: {expect_code}, 实际: {r.status_code}")
            print(f"   响应: {r.text[:200]}")
    except Exception as e:
        failed += 1
        print(f"[FAIL] {name}: 异常 - {e}")

print("=" * 60)
print("AI 报价网 W2 P1 验收测试")
print("=" * 60)

# 1. /health
test("1. GET /health", f"{BASE}/health", expect_code=200)

# 2. POST /api/login 成功
test("2. POST /api/login (成功)", f"{BASE}/api/login", method="POST", 
     data={"mobile": "13800138000", "code": "123456"}, expect_code=200)

# 3. POST /api/login 错误验证码
test("3. POST /api/login (错码)", f"{BASE}/api/login", method="POST",
     data={"mobile": "13800138001", "code": "999999"}, expect_code=401)

# 4. GET /api/admin/stats
test("4. GET /api/admin/stats", f"{BASE}/api/admin/stats",
     headers={"Authorization": "Bearer wj-quote-admin-20260709"}, expect_code=200)

# 5. POST /api/lead (带 user_id)
test("5. POST /api/lead", f"{BASE}/api/lead", method="POST",
     data={"user_id": 1, "name": "张三", "phone": "13800138000", "district": "蜀山区", "remark": "咨询半包"},
     expect_code=200)

# 6. POST /api/quote (带 user_id, L2 fallback)
test("6. POST /api/quote", f"{BASE}/api/quote", method="POST",
     data={"area": 89, "layout": "3室2厅", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138000", "user_id": 1},
     expect_code=200)

# 7. 限流测试 - 连续两次登录
print("\n--- 限流测试 ---")
r1 = requests.post(f"{BASE}/api/login", json={"mobile": "13900000001", "code": "123456"})
print(f"第1次登录: HTTP {r1.status_code}")
time.sleep(0.3)
r2 = requests.post(f"{BASE}/api/login", json={"mobile": "13900000002", "code": "123456"})
ok = r2.status_code == 429
status = "[OK]" if ok else "[FAIL]"
print(f"{status} 第2次登录: HTTP {r2.status_code} (期望 429)")
if ok: passed += 1
else:
    failed += 1
    print(f"   响应: {r2.text[:200]}")

print("\n" + "=" * 60)
print(f"结果: [OK]通过 {passed}  [FAIL]失败 {failed}  总计 {passed+failed}")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
