"""V4 fallback 全场景自检 - 8 case"""
import sys
import traceback
sys.path.insert(0, '.')

from app.models.schemas import QuoteRequest
from app.services.fallback import compute_fallback

CASES = [
    # V3 baseline 4 case (验证兼容性)
    {"name": "F1 V3 baseline 60m²简装全包瑶海", "expect_wan": (7, 9),
     "req": dict(area=60, layout='2室1厅1卫', grade='简装', pack='全包', style='简约', district='瑶海区', contact='13800138001')},
    {"name": "F2 V3 baseline 89m²中档半包蜀山", "expect_wan": (7, 8),
     "req": dict(area=89, layout='3室2厅1卫', grade='中档', pack='半包', style='现代', district='蜀山区', contact='13800138002')},
    {"name": "F3 V3 baseline 128m²高档全包滨湖", "expect_wan": (30, 50),
     "req": dict(area=128, layout='4室2厅2卫', grade='高档', pack='全包', style='轻奢', special=['地暖'], district='滨湖新区', contact='13800138003')},
    {"name": "F4 V3 baseline 200m²豪华整装蜀山", "expect_wan": (130, 180),
     "req": dict(area=200, layout='5室2厅3卫', grade='豪华', pack='整装', style='新中式', special=['中央空调','地暖','新风'], district='蜀山区', contact='13800138004')},
    # V4 新场景 4 case
    {"name": "V4-1 200m²+拆改+18层无电梯+高端品牌", "expect_wan": (130, 200),
     "req": dict(area=200, layout='5室2厅3卫', grade='豪华', pack='整装', style='新中式', special=['中央空调','地暖','新风'], district='蜀山区', contact='13800138011',
                 rooms='5-2-3', floor=18, has_elevator=True, demolition_wall_area=8.5, demolition_build_area=5.0,
                 brand_tier_tile='高端', brand_tier_floor='高端', brand_tier_cabinet='高端', brand_tier_bathroom='高端')},
    {"name": "V4-2 60m²+无V4字段(走V3 default)", "expect_wan": (7, 9),
     "req": dict(area=60, layout='2室1厅1卫', grade='简装', pack='全包', style='简约', district='瑶海区', contact='13800138012')},
    {"name": "V4-3 89m²+7层无电梯(搬运费)", "expect_wan": (7, 12),
     "req": dict(area=89, layout='3室2厅1卫', grade='中档', pack='半包', style='现代', district='蜀山区', contact='13800138013',
                 rooms='3-2-1', floor=7, has_elevator=False)},
    {"name": "V4-4 89m²+品牌档次=经济(降档,半包)", "expect_wan": (5, 10),
     "req": dict(area=89, layout='3室2厅1卫', grade='中档', pack='半包', style='现代', district='蜀山区', contact='13800138014',
                 brand_tier_tile='经济', brand_tier_floor='经济', brand_tier_cabinet='经济', brand_tier_bathroom='经济')},
]

print('='*72)
print(f'{"Case":<48} {"total(万)":>10} {"items":>5}  {"区间":<10} {"status"}')
print('='*72)
pass_n = 0
fail_n = 0
for c in CASES:
    try:
        req = QuoteRequest(**c['req'])
        r, raw = compute_fallback(req)
        total_wan = r.total / 10000
        in_range = c['expect_wan'][0] <= total_wan <= c['expect_wan'][1]
        status = '✅' if in_range else '❌'
        if in_range:
            pass_n += 1
        else:
            fail_n += 1
        print(f'{c["name"]:<48} {total_wan:>10.2f} {len(r.items):>5}  {str(c["expect_wan"]):<10} {status}', flush=True)
        # V4 字段检查
        if 'V4' in c['name']:
            print(f'  ↳ rooms={r.rooms} floor={r.floor} elevator={r.has_elevator} demol={r.demolition_cost} brand_tier={r.material_brand_tier}', flush=True)
    except Exception:
        traceback.print_exc()
        fail_n += 1
        print(f'{c["name"]:<48} EXCEPTION', flush=True)

print('='*72)
print(f'PASS: {pass_n} / {len(CASES)}, FAIL: {fail_n}')
print('='*72)
