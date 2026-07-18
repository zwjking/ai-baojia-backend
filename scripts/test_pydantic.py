"""test Pydantic parse on agnes output"""
import sys, json
sys.path.insert(0, r'C:\Users\Administrator\.qclaw\shared\AI报价网后端')
from app.models.schemas import QuoteResponse, QuoteItem, BreakdownItem, QuoteRequest
from datetime import datetime, timezone

# Replay the actual agnes output from previous test
content_str = '''{
  "total": 54847.55,
  "breakdown": {
    "material": 26120.00,
    "labor": 23185.60,
    "management": 3944.45,
    "tax": 1597.50
  },
  "items": [
    {"name": "水电改造人工", "category": "人工", "unit": "m²", "quantity": 89.00, "unit_price": 47.00, "total": 4183.00},
    {"name": "瓦工铺贴", "category": "人工", "unit": "m²", "quantity": 75.65, "unit_price": 52.00, "total": 3933.80},
    {"name": "木工吊顶", "category": "人工", "unit": "m²", "quantity": 40.05, "unit_price": 67.00, "total": 2683.35},
    {"name": "油漆工", "category": "人工", "unit": "m²", "quantity": 213.60, "unit_price": 42.00, "total": 8971.20},
    {"name": "防水工程", "category": "人工", "unit": "m²", "quantity": 25.00, "unit_price": 60.00, "total": 1500.00},
    {"name": "水泥", "category": "辅材", "unit": "袋", "quantity": 31.00, "unit_price": 26.00, "total": 806.00},
    {"name": "黄沙", "category": "辅材", "unit": "m³", "quantity": 5.34, "unit_price": 220.00, "total": 1174.80},
    {"name": "腻子粉", "category": "辅材", "unit": "袋", "quantity": 13.00, "unit_price": 20.00, "total": 260.00},
    {"name": "电线", "category": "辅材", "unit": "m", "quantity": 445.00, "unit_price": 2.50, "total": 1112.50},
    {"name": "水管", "category": "辅材", "unit": "m", "quantity": 107.00, "unit_price": 15.00, "total": 1605.00},
    {"name": "管理费", "category": "管理", "unit": "项", "quantity": 1.00, "unit_price": 3944.45, "total": 3944.45},
    {"name": "增值税税金", "category": "税金", "unit": "项", "quantity": 1.00, "unit_price": 1597.50, "total": 1597.50}
  ]
}'''
data = json.loads(content_str)
items = [QuoteItem(**it) for it in data['items']]
breakdown = BreakdownItem(**data['breakdown'])
print('items parsed:', len(items))
print('breakdown:', breakdown.model_dump())

# Now check sum invariants
items_sum = sum(i.total for i in items)
b_sum = breakdown.material + breakdown.labor + breakdown.management + breakdown.tax
print(f'items sum: {items_sum}')
print(f'breakdown sum: {b_sum}')
print(f'total: {data["total"]}')

# Try building the full QuoteResponse
try:
    resp = QuoteResponse(
        success=True,
        source='agnes',
        request_id='test',
        total=data['total'],
        breakdown=breakdown,
        items=items,
        area=89.0,
        grade='中档',
        pack='半包',
        district='蜀山区',
        generated_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    )
    print('Pydantic full response OK')
    print('  total:', resp.total)
    print('  breakdown:', resp.breakdown.model_dump())
    print('  items count:', len(resp.items))
    # Check totals sum
    material_from_items = sum(i.total for i in items if i.category in ('主材','辅材'))
    labor_from_items = sum(i.total for i in items if i.category == '人工')
    print(f'  items material: {material_from_items} (breakdown.material={breakdown.material}, diff={material_from_items-breakdown.material})')
    print(f'  items labor:    {labor_from_items} (breakdown.labor={breakdown.labor}, diff={labor_from_items-breakdown.labor})')
except Exception as e:
    print(f'Pydantic validation FAILED: {e}')
