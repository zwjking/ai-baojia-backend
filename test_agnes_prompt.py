"""V4 agnes prompt 自检"""
import sys
sys.path.insert(0, '.')

from app.models.schemas import QuoteRequest
from app.services.agnes_client import build_quote_prompt, call_agnes_chat, quote_via_agnes
from app.services.fallback import _load_prices

prices = _load_prices()
print(f"[1] prices loaded, version={prices.get('version')}")

# V4 完整 case
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
usr_msg = msgs[1]['content']
print(f"[2] system prompt: {len(sys_msg)} chars")
print(f"[3] user prompt: {len(usr_msg)} chars")

# 检查 V4 字段是否注入
checks = [
    ('breakdown_v4', '5 项分类'),
    ('main_material', '主材分类'),
    ('auxiliary', '辅材分类'),
    ('brand_tier', '品牌档'),
    ('拆墙', '拆改'),
    ('¥80/m', '拆墙价'),
    ('¥180/m', '砌墙价'),
    ('¥5/m', '楼层搬运费'),
    ('20-30 行', 'V4 items 行数'),
    ('rooms', '房间数'),
    ('floor', '楼层'),
]
print("[4] Prompt 字段检查:")
for k, name in checks:
    found = k in sys_msg
    print(f"  {'✅' if found else '❌'} {name}: '{k}' {'found' if found else 'MISSING'}")

# 用户 prompt V4 字段
print("[5] User prompt V4 块:")
usr_lines = usr_msg.split('\n')
v4_block_start = usr_lines.index('【V4 扩展输入】') if '【V4 扩展输入】' in usr_lines else -1
if v4_block_start >= 0:
    for line in usr_lines[v4_block_start:]:
        print(f"    {line}")

# 默认 max_tokens 应该是 16000
import inspect
sig = inspect.signature(call_agnes_chat)
print(f"[6] call_agnes_chat 默认 max_tokens={sig.parameters['max_tokens'].default} (期望 16000)")
print(f"[7] call_agnes_chat 默认 timeout={sig.parameters['timeout'].default} (期望 200.0)")

print('='*60)
print('AGNES V4 PROMPT TEST DONE')
