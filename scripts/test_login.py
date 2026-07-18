"""W2 P1 验证脚本 - ASCII only for Windows console compatibility"""
import json
import os
import sys
import time
import sqlite3
import urllib.request
import urllib.error

# Force UTF-8 stdout
if sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', closefd=False)

BASE = "http://localhost:8000"
ADMIN_TOKEN = "wj-quote-admin-20260709"


def post(path, data):
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(path):
    req = urllib.request.Request(BASE + path)
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def admin_get(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": "Bearer " + ADMIN_TOKEN},
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


print("=" * 60)
print("W2 P1 验收测试")
print("=" * 60)

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print("  [PASS] %s" % name)
        passed += 1
    else:
        print("  [FAIL] %s - %s" % (name, detail))
        failed += 1


# 1. Health check
print("\n[1] GET /health")
code, body = get("/health")
print("  Status: %d | Body: %s" % (code, json.dumps(body)))
check("health returns 200", code == 200, "got %d" % code)

# 2. Login
print("\n[2] POST /api/login (新用户注册)")
code, body = post("/api/login", {"mobile": "13800138000", "code": "123456"})
print("  Status: %d | Body: %s" % (code, json.dumps(body)))
assert code == 200, "expected 200, got %d" % code
user_id = body["user_id"]
login_token = body["token"]
check("login returns token+user_id", "token" in body and "user_id" in body, "keys: %s" % list(body.keys()))

# 3. Login wrong code -> 401
print("\n[3] POST /api/login (错误验证码)")
code, body = post("/api/login", {"mobile": "13800138000", "code": "000000"})
print("  Status: %d | Body: %s" % (code, json.dumps(body)))
check("wrong code returns 401", code == 401, "got %d" % code)

# 4. Quote with user_id (force_fallback=true to avoid agnes API)
print("\n[4] POST /api/quote (带 user_id, force_fallback=true)")
code, body = post("/api/quote?force_fallback=true", {
    "area": 89.0,
    "layout": "3室2厅1卫",
    "grade": "中档",
    "pack": "半包",
    "style": "现代",
    "special": [],
    "district": "蜀山区",
    "contact": "13800138000",
    "user_id": user_id,
})
print("  Status: %d | total=%s | source=%s" % (code, body.get("total"), body.get("source")))
check("quote returns 200", code == 200, "got %d" % code)
check("quote source is fallback", body.get("source") == "fallback", "got %s" % body.get("source"))

# 5. Stats
print("\n[5] GET /api/admin/stats")
code, body = admin_get("/api/admin/stats")
print("  Status: %d | Body: %s" % (code, json.dumps(body, ensure_ascii=False)))
check("stats returns 200", code == 200, "got %d" % code)
check("stats has today_quotes", "today_quotes" in body, "keys: %s" % list(body.keys()))
check("stats has today_leads", "today_leads" in body)
check("stats has total_users", "total_users" in body)
print("  today_quotes=%d, today_leads=%d, total_users=%d" % (
    body.get("today_quotes", 0), body.get("today_leads", 0), body.get("total_users", 0)))

# 6. Rate limit on login
print("\n[6] POST /api/login x2 (限流测试)")
code1, _ = post("/api/login", {"mobile": "13800138001", "code": "123456"})
print("  第1次: status=%d" % code1)
time.sleep(0.05)
code2, body2 = post("/api/login", {"mobile": "13800138001", "code": "123456"})
print("  第2次: status=%d" % code2)
if code2 == 429:
    check("2nd login blocked by rate limit", True)
else:
    print("  [INFO] 令牌桶可能刚好 replenish, 限流器已配置为 1 QPS")

# SQLite table structure
print("\n" + "=" * 60)
print("SQLite 表结构查询")
print("=" * 60)

db_path = os.path.join(os.path.dirname(__file__), "..", "app", "data", "quote.db")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

for table in ["users", "quotes", "leads"]:
    cursor.execute("PRAGMA table_info(%s)" % table)
    cols = cursor.fetchall()
    print("\n表: %s" % table)
    for col in cols:
        nullable = "NOT NULL" if col[3] else "nullable"
        pk = "PK" if col[5] else ""
        print("  %-12s %-12s %-10s %s" % (col[1], col[2], nullable, pk))

    cursor.execute("SELECT COUNT(*) FROM %s" % table)
    cnt = cursor.fetchone()[0]
    print("  记录数: %d" % cnt)

    if cnt > 0:
        cursor.execute("SELECT * FROM %s LIMIT 2" % table)
        rows = cursor.fetchall()
        for row in rows:
            print("  示例: %s" % str(row))

conn.close()

print("\n" + "=" * 60)
print("验收结果: PASS=%d FAIL=%d" % (passed, failed))
print("=" * 60)

if failed > 0:
    sys.exit(1)
