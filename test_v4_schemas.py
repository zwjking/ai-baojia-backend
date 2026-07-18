"""V4 schemas 自检脚本 - 干净版"""
import sys
sys.path.insert(0, '.')

from app.models.schemas import (
    QuoteRequest, QuoteResponse, QuoteItem, BreakdownV4,
    CategoryBlock, BrandTierEnum, BreakdownItem
)

# 测试 1: V4 输入
req = QuoteRequest(
    area=200.0, layout='5室2厅3卫', grade='豪华', pack='整装', style='新中式',
    special=['中央空调'], district='蜀山区', contact='13800138000',
    rooms='5-2-3', floor=18, has_elevator=True,
    demolition_wall_area=8.5, demolition_build_area=5.0,
    brand_tier_tile='高端', brand_tier_floor='高端',
    brand_tier_cabinet='高端', brand_tier_bathroom='高端',
)
print('OK T1 QuoteRequest V4, area:', req.area, 'rooms:', req.rooms, 'floor:', req.floor)
print('OK T1 brand_tier:', req.brand_tier_tile.value, req.brand_tier_floor.value)

# 测试 2: V4 5 项分类 (构造完美合计的数据)
v4 = BreakdownV4(
    main_material=CategoryBlock(category='主材', total=389500, items=[
        QuoteItem(name='客餐厅瓷砖', category='主材', unit='m2', quantity=170.0, unit_price=650.0, total=110500, brand='马可波罗', spec='800x800'),
        QuoteItem(name='全屋柜体定制', category='主材', unit='m2', quantity=90.0, unit_price=3100.0, total=279000, brand='索菲亚康纯', spec='18mm'),
    ]),
    auxiliary=CategoryBlock(category='辅材', total=70000, items=[
        QuoteItem(name='水电料', category='辅材', unit='m2', quantity=200.0, unit_price=350.0, total=70000),
    ]),
    labor=CategoryBlock(category='人工', total=65000, items=[
        QuoteItem(name='水电工', category='人工', unit='m2', quantity=200.0, unit_price=325.0, total=65000),
    ]),
    management=CategoryBlock(category='管理费', total=45830, items=[]),
    tax=CategoryBlock(category='税费', total=47421, items=[]),
)
s = v4.main_material.total + v4.auxiliary.total + v4.labor.total + v4.management.total + v4.tax.total
print(f'OK T2 BreakdownV4 5 类 sum={s}')

# 测试 3: V3 兼容 (4 类费用 + 22 items)
items = [
    QuoteItem(name='客餐厅瓷砖', category='主材', unit='m2', quantity=170.0, unit_price=650.0, total=110500),
    QuoteItem(name='卧室地板', category='主材', unit='m2', quantity=110.0, unit_price=780.0, total=85800),
    QuoteItem(name='厨房橱柜', category='主材', unit='套', quantity=1.0, unit_price=39000.0, total=39000),
    QuoteItem(name='全屋柜体定制', category='主材', unit='m2', quantity=90.0, unit_price=3100.0, total=279000),
    QuoteItem(name='室内门', category='主材', unit='樘', quantity=8.0, unit_price=6500.0, total=52000),
    QuoteItem(name='卫浴套装', category='主材', unit='套', quantity=3.0, unit_price=25000.0, total=75000),
    QuoteItem(name='吊顶', category='主材', unit='m2', quantity=110.0, unit_price=350.0, total=38500),
    QuoteItem(name='灯具', category='主材', unit='套', quantity=1.0, unit_price=25000.0, total=25000),
    QuoteItem(name='水电料', category='辅材', unit='m2', quantity=200.0, unit_price=200.0, total=40000),
    QuoteItem(name='防水', category='辅材', unit='m2', quantity=60.0, unit_price=120.0, total=7200),
    QuoteItem(name='腻子', category='辅材', unit='m2', quantity=480.0, unit_price=20.0, total=9600),
    QuoteItem(name='乳胶漆', category='辅材', unit='m2', quantity=480.0, unit_price=40.0, total=19200),
    QuoteItem(name='五金件', category='辅材', unit='套', quantity=1.0, unit_price=15000.0, total=15000),
    QuoteItem(name='水电工', category='人工', unit='m2', quantity=200.0, unit_price=200.0, total=40000),
    QuoteItem(name='瓦工', category='人工', unit='m2', quantity=170.0, unit_price=180.0, total=30600),
    QuoteItem(name='木工', category='人工', unit='m2', quantity=90.0, unit_price=300.0, total=27000),
    QuoteItem(name='油漆工', category='人工', unit='m2', quantity=480.0, unit_price=120.0, total=57600),
    QuoteItem(name='安装', category='人工', unit='m2', quantity=200.0, unit_price=250.0, total=50000),
    QuoteItem(name='管理费', category='管理', unit='项', quantity=1.0, unit_price=45830.0, total=45830.0),
    QuoteItem(name='税金', category='税金', unit='项', quantity=1.0, unit_price=47421.0, total=47421.0),
    QuoteItem(name='拆墙', category='主材', unit='m2', quantity=8.5, unit_price=80.0, total=680.0),
    QuoteItem(name='砌墙', category='主材', unit='m2', quantity=5.0, unit_price=180.0, total=900.0),
]
total = sum(i.total for i in items)
print(f'OK T3 items sum={total}')
# 4 类合计: 主材+辅材+人工+管理+税金
material = sum(i.total for i in items if i.category == '主材')
labor = sum(i.total for i in items if i.category == '人工')
mgmt = sum(i.total for i in items if i.category == '管理')
tax = sum(i.total for i in items if i.category == '税金')
print(f'OK T3 4 类 material={material} labor={labor} mgmt={mgmt} tax={tax} sum={material+labor+mgmt+tax}')

r = QuoteResponse(
    success=True, source='fallback', total=total,
    breakdown=BreakdownItem(material=total - labor - mgmt - tax, labor=labor, management=mgmt, tax=tax),
    items=items, area=200.0, grade='豪华', pack='整装', district='蜀山区',
    generated_at='2026-07-11T10:00:00',
    rooms='5-2-3', floor=18, has_elevator=True,
    demolition_cost=1580.0,
    material_brand_tier={'tile': '高端', 'floor': '高端', 'cabinet': '高端', 'bathroom': '高端'},
)
print(f'OK T3 QuoteResponse V3 兼容, total={r.total}, rooms={r.rooms}, demolition_cost={r.demolition_cost}')

print('=' * 60)
print('ALL V4 SCHEMA TESTS PASSED')
