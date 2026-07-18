# -*- coding: utf-8 -*-
"""W2 前端联调验收测试 - ASCII only"""
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
        print(status_str + " " + name + ": HTTP " + str(r.status_code) + " -> " + resp)
        if ok:
            passed += 1
        else:
            failed += 1
            print("   期望: " + str(expect_code) + ", 实际: " + str(r.status_code))
    except Exception as e:
        failed += 1
        print("[FAIL] " + name + ": " + str(e))

print("=" * 60)
print("AI 报价网 W2 前端联调验收测试")
print("=" * 60)

# 1. /health
test("1. GET /health", BASE + "/health", expect_code=200)

# 2. POST /api/login
test("2. POST /api/login", BASE + "/api/login", method="POST", 
     data={"mobile": "13800138000", "code": "123456"}, expect_code=200)

# 3. POST /api/quote (force_fallback=true)
test("3. POST /api/quote (fallback)", BASE + "/api/quote", method="POST",
     data={"area": 89, "layout": "3室2厅", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138000", "user_id": 1},
     params={"force_fallback": "true"}, expect_code=200)

# 4. POST /api/lead
test("4. POST /api/lead", BASE + "/api/lead", method="POST",
     data={"user_id": 1, "name": "张三", "phone": "13800138000", "district": "蜀山区", "remark": "咨询半包"},
     expect_code=200)

# 5. GET /api/admin/stats
test("5. GET /api/admin/stats", BASE + "/api/admin/stats",
     headers={"Authorization": "Bearer wj-quote-admin-20260709"}, expect_code=200)

# 6. 检查前端文件
print("\n--- 前端文件检查 ---")
import os
files = ["login.html", "survey.html", "result.html"]
for fname in files:
    path = os.path.join(r"C:\Users\Administrator\Desktop\AI报价网_V1", fname)
    if os.path.exists(path):
        size = os.path.getsize(path)
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))
        print("[OK] " + fname + ": " + str(size) + " bytes, modified " + mtime)
        passed += 1
        
        # 检查是否包含 API 调用
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        if fname == "login.html":
            if "fetch('/api/login'" in content or 'fetch("/api/login"' in content:
                print("   [OK] 包含 fetch('/api/login')")
                passed += 1
            else:
                print("   [FAIL] 不包含 fetch('/api/login')")
                failed += 1
        elif fname == "survey.html":
            if "fetch('/api/quote" in content or 'fetch("/api/quote' in content:
                print("   [OK] 包含 fetch('/api/quote")
                passed += 1
            else:
                print("   [FAIL] 不包含 fetch('/api/quote")
                failed += 1
        elif fname == "result.html":
            if "fetch('/api/lead" in content or 'fetch("/api/lead' in content:
                print("   [OK] 包含 fetch('/api/lead")
                passed += 1
            else:
                print("   [FAIL] 不包含 fetch('/api/lead")
                failed += 1
    else:
        print("[FAIL] " + fname + " 不存在")
        failed += 1

# 7. 检查博雅工作区
print("\n--- 博雅工作区检查 ---")
boyah_dir = r"C:\Users\Administrator\.qclaw\workspace-agent-boyah\AI报价网_V1"
for fname in files:
    src = os.path.join(r"C:\Users\Administrator\Desktop\AI报价网_V1", fname)
    dst = os.path.join(boyah_dir, fname)
    if os.path.exists(dst):
        src_size = os.path.getsize(src)
        dst_size = os.path.getsize(dst)
        if src_size == dst_size:
            print("[OK] " + fname + " 同步完成 (" + str(dst_size) + " bytes)")
            passed += 1
        else:
            print("[WARN] " + fname + " 大小不一致: 桌面=" + str(src_size) + " 博雅=" + str(dst_size))
            failed += 1
    else:
        print("[FAIL] " + fname + " 未同步到博雅工作区")
        failed += 1

print("\n" + "=" * 60)
print("结果: [OK]通过 " + str(passed) + "  [FAIL]失败 " + str(failed) + "  总计 " + str(passed+failed))
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
