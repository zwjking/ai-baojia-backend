"""检查 fallback.py 4 项调整是否已生效"""
checks = [
    ('import math', '调整 0: import math'),
    ('_FURNITURE_RATE = 0.20', '调整 1: 家具家电 0.20'),
    ('max(2, math.ceil(area / 25))', '调整 2: 室内门按户型'),
    ('grade in ("高档", "豪华")', '调整 3: 高档/豪华 30%分位'),
    ('lo + (hi - lo) * 0.30', '调整 3: 30% 分位算法'),
    ('raw_mgmt_rate', '调整 4: mgmt_rate 封顶'),
    ('min(raw_mgmt_rate, 0.10)', '调整 4: 封顶 0.10'),
]
with open(r'C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\services\fallback.py', 'r', encoding='utf-8') as f:
    content = f.read()
all_ok = True
for needle, label in checks:
    found = needle in content
    print(f"  {'OK' if found else 'FAIL'} {label}: 关键字 '{needle}' -> {found}")
    if not found:
        all_ok = False
print()
print("ALL CHANGES APPLIED" if all_ok else "SOME CHANGES MISSING")
