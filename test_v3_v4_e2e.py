"""V4 端到端验证 - force_fallback=true 走 L2 路径
- V3 baseline 4 case (验证 V3 兼容)
- V4 扩展 4 case (验证 V4 字段全链路)
"""
import json
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:8000"

CASES = [
    # V3 baseline
    {"name": "F1 V3 60m²简装全包瑶海", "expect_wan": (7, 9),
     "body": {"area": 60, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包", "style": "简约", "special": [], "district": "瑶海区", "contact": "13800138001"}},
    {"name": "F2 V3 89m²中档半包蜀山", "expect_wan": (7, 8),
     "body": {"area": 89, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138002"}},
    {"name": "F3 V3 128m²高档全包滨湖", "expect_wan": (30, 50),
     "body": {"area": 128, "layout": "4室2厅2卫", "grade": "高档", "pack": "全包", "style": "轻奢", "special": ["地暖"], "district": "滨湖新区", "contact": "13800138003"}},
    {"name": "F4 V3 200m²豪华整装蜀山", "expect_wan": (130, 180),
     "body": {"area": 200, "layout": "5室2厅3卫", "grade": "豪华", "pack": "整装", "style": "新中式", "special": ["中央空调","地暖","新风"], "district": "蜀山区", "contact": "13800138004"}},
    # V4 新场景
    {"name": "V4-1 200m²+拆改+品牌高端", "expect_wan": (130, 200),
     "body": {"area": 200, "layout": "5室2厅3卫", "grade": "豪华", "pack": "整装", "style": "新中式", "special": ["中央空调","地暖","新风"], "district": "蜀山区", "contact": "13800138011",
              "rooms": "5-2-3", "floor": 18, "has_elevator": True, "demolition_wall_area": 8.5, "demolition_build_area": 5.0,
              "brand_tier_tile": "高端", "brand_tier_floor": "高端", "brand_tier_cabinet": "高端", "brand_tier_bathroom": "高端"}},
    {"name": "V4-2 60m² V4字段None", "expect_wan": (7, 9),
     "body": {"area": 60, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包", "style": "简约", "special": [], "district": "瑶海区", "contact": "13800138012"}},
    {"name": "V4-3 89m² 7层无电梯搬运费", "expect_wan": (7, 12),
     "body": {"area": 89, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138013",
              "rooms": "3-2-1", "floor": 7, "has_elevator": False}},
    {"name": "V4-4 89m² 半包+品牌经济降档", "expect_wan": (5, 10),
     "body": {"area": 89, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138014",
              "brand_tier_tile": "经济", "brand_tier_floor": "经济", "brand_tier_cabinet": "经济", "brand_tier_bathroom": "经济"}},
]

print('='*88)
print(f'{"Case":<38} {"total(万)":>10} {"items":>5} {"v4_items":>8} {"break_v4":>9} {"区间":<10} {"status"}')
print('='*88)
pass_n = 0
fail_n = 0
for c in CASES:
    body = json.dumps(c['body'], ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        f"{BASE}/api/quote?force_fallback=true",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=30) as r:
            t_used = (time.time() - t0) * 1000
            resp = json.loads(r.read().decode('utf-8'))
        total_wan = resp['total'] / 10000
        in_range = c['expect_wan'][0] <= total_wan <= c['expect_wan'][1]
        v4_items = sum(len(b.get('items', [])) for b in [
            resp.get('breakdown_v4', {}).get('main_material', {}),
            resp.get('breakdown_v4', {}).get('auxiliary', {}),
            resp.get('breakdown_v4', {}).get('labor', {}),
            resp.get('breakdown_v4', {}).get('management', {}),
            resp.get('breakdown_v4', {}).get('tax', {}),
        ]) if resp.get('breakdown_v4') else 0
        has_v4 = '✅' if resp.get('breakdown_v4') else '❌'
        status = '✅' if in_range else '❌'
        if in_range: pass_n += 1
        else: fail_n += 1
        print(f'{c["name"]:<38} {total_wan:>10.2f} {len(resp["items"]):>5} {v4_items:>8} {has_v4:>9} {str(c["expect_wan"]):<10} {status} {t_used:.0f}ms', flush=True)
        # 关键 V4 字段展示
        if 'V4' in c['name']:
            extras = []
            for k in ['rooms', 'floor', 'has_elevator', 'demolition_cost']:
                if k in resp and resp[k] is not None:
                    extras.append(f'{k}={resp[k]}')
            if extras:
                print(f'    ↳ {", ".join(extras)}', flush=True)
            if resp.get('material_brand_tier'):
                print(f'    ↳ brand_tier={resp["material_brand_tier"]}', flush=True)
    except urllib.error.HTTPError as e:
        fail_n += 1
        body = e.read().decode('utf-8', errors='ignore')[:200]
        print(f'{c["name"]:<38} HTTP {e.code}: {body}', flush=True)
    except Exception as e:
        fail_n += 1
        print(f'{c["name"]:<38} EXCEPTION: {e}', flush=True)

print('='*88)
print(f'PASS: {pass_n} / {len(CASES)}, FAIL: {fail_n}')
print('='*88)
