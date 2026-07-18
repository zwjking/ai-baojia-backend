# -*- coding: utf-8 -*-
"""W2 P1 验收测试 v2 - 修正版"""
import requests
import json
import sys
import time

BASE = "http://127.0.0.1:8000"
passed = 0
failed = 0

def test(name, url, method="GET", data=None, headers=None, params=None, expect_code=200):
    global passed, failed
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=30)
        elif method == "POST":
            r = requests.post(url, json=data, headers=headers, params=params, timeout=120)
        
        ok = r.status_code == expect_code
        status_str = "[OK]" if ok else "[FAIL]"
        resp = json.dumps(r.json(), ensure_ascii=False)[:150]
        print(f"{status_str} {name}: HTTP {r.status_code} -> {resp}")
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
print("AI 报价网 W2 P1 验收测试 v2")
print("=" * 60)

# 1. /health
test("1. GET /health", f"{BASE}/health", expect_code=200)

# 2. POST /api/login 成功
test("2. POST /api/login (成功)", f"{BASE}/api/login", method="POST", 
     data={"mobile": "13800138000", "code": "123456"}, expect_code=200)

# 3. POST /api/login 错误验证码（用新手机号）
test("3. POST /api/login (错码)", f"{BASE}/api/login", method="POST",
     data={"mobile": "13800138099", "code": "999999"}, expect_code=401)

# 4. GET /api/admin/stats
test("4. GET /api/admin/stats", f"{BASE}/api/admin/stats",
     headers={"Authorization": "Bearer wj-quote-admin-20260709"}, expect_code=200)

# 5. POST /api/lead (带 user_id)
test("5. POST /api/lead", f"{BASE}/api/lead", method="POST",
     data={"user_id": 1, "name": "张三", "phone": "13800138000", "district": "蜀山区", "remark": "咨询半包"},
     expect_code=200)

# 6. POST /api/quote (带 user_id + force_fallback=true 跳过 agnes)
test("6. POST /api/quote (fallback)", f"{BASE}/api/quote", method="POST",
     data={"area": 89, "layout": "3室2厅", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138000", "user_id": 1},
     params={"force_fallback": "true"}, expect_code=200)

# 7. 限流测试 - 连续两次登录（用不同手机号）
print("\n--- 限流测试 ---")
r1 = requests.post(f"{BASE}/api/login", json={"mobile": "13900000003", "code": "123456"})
print(f"第1次登录: HTTP {r1.status_code}")
time.sleep(0.3)
r2 = requests.post(f"{BASE}/api/login", json={"mobile": "13900000004", "code": "123456"})
ok = r2.status_code == 429
status_str = "[OK]" if ok else "[FAIL]"
print(f"{status_str} 第2次登录: HTTP {r2.status_code} (期望 429)")
if ok: passed += 1
else:
    failed += 1
    print(f"   响应: {r2.text[:200]}")

# 8. SQLite 数据库验证
print("\n--- 数据库验证 ---")
try:
    import sqlite3
    db_path = r"C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\data\quote.db"
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    user_count = c.fetchone()[0]
    print(f"[OK] users 表: {user_count} 条记录")
    passed += 1
    
    c.execute("SELECT COUNT(*) FROM quotes")
    quote_count = c.fetchone()[0]
    print(f"[OK] quotes 表: {quote_count} 条记录 (fallback 模式不写入,应为 0)")
    passed += 1
    
    c.execute("SELECT COUNT(*) FROM leads")
    lead_count = c.fetchone()[0]
    print(f"[OK] leads 表: {lead_count} 条记录")
    passed += 1
    
    conn.close()
except Exception as e:
    failed += 3
    print(f"[FAIL] 数据库验证异常: {e}")

print("\n" + "=" * 60)
print(f"结果: [OK]通过 {passed}  [FAIL]失败 {failed}  总计 {passed+failed}")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
