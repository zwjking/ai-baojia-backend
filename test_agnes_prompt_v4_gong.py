"""V4+顾工 prompt 自检"""
import sys
sys.path.insert(0, '.')

from app.models.schemas import QuoteRequest
from app.services.agnes_client import build_quote_prompt
from app.services.fallback import _load_prices

prices = _load_prices()

req = QuoteRequest(
    area=200.0, layout='5室2厅3卫', grade='豪华', pack='整装', style='新中式',
    special=['中央空调', '地暖', '新风'], district='蜀山区', contact='13800138000',
    rooms='5-2-3', floor=18, has_elevator=True,
    demolition_wall_area=8.5, demolition_build_area=5.0,
    brand_tier_tile='高端', brand_tier_floor='高端',
    brand_tier_cabinet='高端', brand_tier_bathroom='高端',
)
msgs = build_quote_prompt(req, prices)
sys_msg = msgs[0]['content']
print(f"[1] system prompt: {len(sys_msg)} chars")

# 顾工 V4 关键算账公式
checks = [
    ('顾工 V4 算账公式', '顾工 V4 算账公式'),
    ('拆墙 80', '¥80/m²'),
    ('砌墙 120', '¥120/m²'),
    ('楼层系数 4%', '11-20层 +4%'),
    ('楼层系数 6%', '>20层 +6%'),
    ('无电梯 >6层 +12-20%', '>6层 +12-20%'),
    ('设计费 200', '200-500元/m²'),
    ('软装 5500', '5500元/m²'),
    ('管理费 4%', '4%(豪华)'),
    ('税 3.5%', '× 3.5%'),
    ('品牌档次 4 项', '品牌档次(4项)'),
    ('20-30 行', '20-30 行'),
    ('breakdown_v4', 'breakdown_v4'),
    ('主材/辅材/人工/管理费/税费', '5 项分类'),
]
print("[2] 顾工 V4 关键算账公式 注入检查:")
all_pass = True
for k, kw in checks:
    found = kw in sys_msg
    print(f"  {'✅' if found else '❌'} {k}: '{kw}' {'found' if found else 'MISSING'}")
    if not found: all_pass = False

print(f"\n{'✅ ALL PASS' if all_pass else '❌ SOME MISSING'}")
