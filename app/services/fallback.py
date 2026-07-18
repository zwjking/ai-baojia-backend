"""
L2 降级服务 - agnes 调用失败时,使用本地价格基线计算

数据源: app/data/fallback_prices_v3.json
范围:   8 主材 + 5 辅材 + 5 工种 + 4 档管理费 + 4 档税金 + 5 区区域系数
档位:   简装 / 中档 / 高档 / 豪华
模式:   半包 = aux + labor  |  全包 = main + aux + labor  |  整装 = 全包 + 家具家电(全包价×0.4 估算)

工程量规则: 见模块级 _QTY_TABLE(建筑面积 → 各品类用量)
  - 防水工程量硬编码 18m²(厨卫面积,v3 JSON 未提供)
  - 整装家具家电无 v3 JSON,硬编码估算公式

W3 v3.5 算法收紧(在 v3 JSON 之上):
  - _FURNITURE_RATE  0.40 -> 0.20   (家具家电估算减半)
  - _qty_door        固定 4 -> max(2, ceil(a/25))  (按户型计算)
  - _mid_price       高档/豪华 改用 30% 分位   (压缩高端偏离)
  - mgmt_rate        高档 0.10 / 豪华 0.10  (豪华 0.12 封顶)

Pydantic 强约束(由 schemas.QuoteResponse 自动校验):
  - items ≥ 10 行
  - breakdown 4 类之和 == total(容差 5 元)
  - items 合价之和 == total(容差 50 元)
  - 任何 item total = round(qty * unit_price, 2) (容差 1 元)
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

from app.models.schemas import (
    BreakdownItem,
    BreakdownV4,
    CategoryBlock,
    QuoteItem,
    QuoteRequest,
    QuoteResponse,
)

logger = logging.getLogger(__name__)

# ============== 数据路径 ==============
# v3 为主(顾工 7/10 交付,10227 字节,高档/豪华档校准下浮 30-50%)
# v2 备份在 .bak-2026-07-10(已切到 v3)
# 写死路径避免外部传参
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DATA_PATH = _DATA_DIR / "fallback_prices_v3.json"
_PRICES_CACHE: Dict | None = None
_PRICES_LOADED_AT: str | None = None


# ============== 工程量系数表(顾工报告第6节) ==============
# key: 品类名(严格匹配 v3 JSON 字段) | value: callable(area) -> 工程量
# 注意: 所有函数签名统一为 (area: float) -> float
#       复杂逻辑(拆改/楼层/特殊需求)在 compute_fallback 中处理
# 这些系数也是 ML 模型的输入特征名(保持命名一致)
def _qty_main_tile(area: float) -> float:
    return round(area * 0.85, 2)

def _qty_main_floor(area: float) -> float:
    return round(area * 0.55, 2)

def _qty_cabinet(area: float) -> float:
    return 1.0  # 厨房橱柜固定 1 套

def _qty_wardrobe(area: float) -> float:
    return round(area * 0.45, 2)  # 全屋柜体定制投影面积

def _qty_door(area: float) -> float:
    # 室内门按户型计算:每 25m² 一樘,最少 2 樘(小户型保护)
    # 60m²→3, 89m²→4, 128m²→6, 200m²→8
    return float(max(2, math.ceil(area / 25)))

def _qty_bathroom(area: float) -> float:
    return 1.0  # 卫浴套装固定 1 套

def _qty_ceiling(area: float) -> float:
    return round(area * 0.55, 2)

def _qty_lighting(area: float) -> float:
    # V5 优化: 灯具不再固定 1 套, 按面积估算
    # 每 25m² 约 1 套, 最少 3 套(厨卫+客餐厅+过道)
    return max(3, round(area / 25))


# 辅材/人工 - 防水面积按卫生间数量估算
# 公式: 每 60m² ≈ 1 个卫生间, 每个卫生间防水面积约 6m²
def _qty_water_proof(area: float) -> float:
    bathrooms = max(1, round(area / 60))  # 最少 1 卫
    return round(bathrooms * 6.0, 2)  # 每个卫生间 6m² 防水


_QTY_TABLE: Dict[str, callable] = {
    # 主材
    "客餐厅瓷砖":     _qty_main_tile,
    "卧室地板":       _qty_main_floor,
    "厨房橱柜":       _qty_cabinet,
    "全屋柜体定制":   _qty_wardrobe,
    "室内门":         _qty_door,
    "卫浴套装":       _qty_bathroom,
    "吊顶(含灯槽)":   _qty_ceiling,
    "灯具":           _qty_lighting,
    # 辅材
    "水电料":         lambda a: round(a * 1.0, 2),
    "防水":           _qty_water_proof,
    "腻子":           lambda a: round(a * 2.4, 2),   # 涂刷面积
    "乳胶漆":         lambda a: round(a * 2.4, 2),   # 涂刷面积
    "五金件":         lambda a: 1.0,                   # 固定 1 套
    # 人工
    "水电":           lambda a: round(a * 1.0, 2),     # 建筑面积
    "瓦工":           lambda a: round(a * 0.85, 2),   # 铺贴面积
    "木工":           lambda a: round(a * 0.45, 2),   # 投影
    "油漆":           lambda a: round(a * 2.4, 2),    # 涂刷面积
    "安装":           lambda a: round(a * 1.0, 2),     # 建筑面积
}

# 整装家具家电估算系数(v3 JSON 无此部分,硬编码)
# W3 v3.5 收紧: 0.4 → 0.20(避免大户型家具家电成本爆炸)
# 200m² 豪华案例: (main+aux+labor) 约 178万 × 0.20 = 35.6 万
_FURNITURE_RATE = 0.20  # 整装家具家电 ≈ (main+aux+labor) × 0.20


# ============== V4 扩展常量 ==============
# 品牌档 → V3 档位映射(品牌档独立于 grade, 只影响主材价格)
# - 经济 → 简装价 (低端主导)
# - 中档 → 中档价
# - 高端 → 高档价 (中位价)
_BRAND_TIER_TO_GRADE = {
    "经济": "简装",
    "中档": "中档",
    "高端": "高档",
}

# 4 项主材 → 品牌档次 字段名(映射 QuoteRequest.brand_tier_* → v3 main 品类名)
_BRAND_TIER_FIELDS = {
    "地砖": "brand_tier_tile",       # 客餐厅瓷砖
    "地板": "brand_tier_floor",      # 卧室地板
    "橱柜": "brand_tier_cabinet",    # 厨房橱柜
    "卫浴": "brand_tier_bathroom",   # 卫浴套装
}

# 4 项主材 → v3 JSON 品类名
_MAIN_NAME_MAP = {
    "地砖": "客餐厅瓷砖",
    "地板": "卧室地板",
    "橱柜": "厨房橱柜",
    "卫浴": "卫浴套装",
}

# 拆改单价(顾工 7/11 合肥价格基准)
# 拆墙 (砖混 12cm): 40-60 元/m², 混凝土 24cm: 80-120 元/m², 取中位 80
# 砌墙 (12单墙): 85-110 元/m², 24双墙: 120-160 元/m², 取中位 120
_DEMOLITION_WALL_PRICE = 80.0  # 元/m² (顾工 7/11 中位)
_DEMOLITION_BUILD_PRICE = 120.0  # 元/m² (顾工 7/11 中位)

# 楼层搬运费(无电梯高楼层加收)
# 合肥 2026 行情: 5 元/m²/层 (无电梯)
_FLOOR_CARRY_PRICE = 5.0  # 元/m²/层
_FLOOR_NO_ELEVATOR_THRESHOLD = 6  # 6 层以上无电梯开始加搬运费

# ============== V5: 特殊需求计价(地暖/中央空调/新风等) ==============
# 这些是大项费用, 之前完全漏算! 89m² 三个全选应加约 5-6 万
_SPECIAL_PRICE = {
    "地暖": {"min": 150, "max": 250, "unit": "m²", "_desc": "含管道+分水器+安装"},
    "中央空调": {"min": 200, "max": 400, "unit": "m²", "_desc": "含室内机+室外机+安装"},
    "新风": {"min": 100, "max": 200, "unit": "m²", "_desc": "含主机+管道+安装"},
    "智能家居": {"flat": 15000, "_desc": "固定 1.5 万(全屋基础智能)"},
    "净水系统": {"flat": 8000, "_desc": "固定 8000(前置+末端)"},
    "地暖+中央空调": {"flat": 35000, "_desc": "组合优惠(单独买约 4 万+)"},
}

# ============== V5: ML 特征工程支持 ==============
# fallback 计算后输出结构化特征字典, 供未来决策树模型训练/推理使用
# 特征名与 scikit-learn Pipeline 完全对齐
def _extract_features(req: "QuoteRequest", area: float, grade: str, pack: str,
                      district: str, floor: int, has_elevator: bool,
                      demolition_wall: float, demolition_build: float,
                      special: list, brand_tier_out: dict) -> dict:
    """
    从请求 + 计算结果中提取 ML 特征
    
    输出格式与 scikit-learn DecisionTreeRegressor.fit(X, y) 完全兼容:
      X = pd.DataFrame(features_list)
      model.fit(X, y)  # y = total
    
    特征列表(14 维):
      area, grade_num, pack_num, style_num, district_num,
      floor, has_elevator, demolition_wall, demolition_build,
      special_count, brand_tier_tile, brand_tier_floor,
      brand_tier_cabinet, brand_tier_bathroom
    """
    # 数值编码
    grade_map = {"简装": 0, "中档": 1, "高档": 2, "豪华": 3}
    pack_map = {"半包": 0, "全包": 1, "整装": 2}
    district_map = {"蜀山区": 0, "瑶海区": 1, "包河区": 2, "庐阳区": 3, "滨湖新区": 4}
    brand_map = {"经济": 0, "中档": 1, "高端": 2}
    
    return {
        # 基础特征
        "area": area,
        "grade_num": grade_map.get(grade, 1),
        "pack_num": pack_map.get(pack, 1),
        "district_num": district_map.get(district, 0),
        "floor": floor if floor is not None else -1,
        "has_elevator": 1 if has_elevator else (0 if has_elevator is False else -1),
        # 拆改特征
        "demolition_wall": demolition_wall or 0.0,
        "demolition_build": demolition_build or 0.0,
        # 特殊需求特征
        "special_count": len(special) if special else 0,
        # 品牌档次特征(4 项独立)
        "brand_tier_tile": brand_map.get(brand_tier_out.get("地砖"), 1),
        "brand_tier_floor": brand_map.get(brand_tier_out.get("地板"), 1),
        "brand_tier_cabinet": brand_map.get(brand_tier_out.get("橱柜"), 1),
        "brand_tier_bathroom": brand_map.get(brand_tier_out.get("卫浴"), 1),
    }


# 品牌推荐表(SKU 品牌+规格, fallback 用, agnes 自由发挥)
_BRAND_RECOMMEND = {
    "地砖": {
        "经济": [("诺贝尔基础", "800x800 釉面"), ("欧神诺普通", "800x800 抛釉")],
        "中档": [("马可波罗", "800x800 抛釉砖"), ("东鹏", "800x800 抛釉砖")],
        "高端": [("简一大理石瓷砖", "900x1800 大板"), ("诺贝尔印象", "900x1800 大板")],
    },
    "地板": {
        "经济": [("圣象基础", "强化复合 12mm"), ("大自然普通", "实木复合 15mm")],
        "中档": [("圣象", "实木多层 15mm"), ("世友", "实木复合 18mm")],
        "高端": [("世友纯实木", "实木 18mm"), ("菲林格尔原木", "进口橡木 18mm")],
    },
    "橱柜": {
        "经济": [("欧派基础", "模压门 6m 地柜"), ("志邦普通", "烤漆门 6m")],
        "中档": [("欧派", "整体橱柜 6m+4m 吊柜"), ("志邦", "模压门 6m")],
        "高端": [("志邦高端", "实木门 6m"), ("博洛尼整体", "进口饰面 6m+4m")],
    },
    "卫浴": {
        "经济": [("箭牌基础", "8件套"), ("九牧普通", "8件套")],
        "中档": [("箭牌", "8件套 节水"), ("科勒基础", "8件套")],
        "高端": [("科勒", "8件套 智能"), ("汉斯格雅", "进口 8件套")],
    },
}


def _pick_brand(category: str, tier: str, idx: int = 0) -> Tuple[str, str]:
    """根据主材类别+品牌档选推荐品牌+规格, idx 用于多个品类时分散"""
    options = _BRAND_RECOMMEND.get(category, {}).get(tier, [])
    if not options:
        return ("", "")
    return options[idx % len(options)]


# ============== 价格加载(进程内缓存) ==============
def _read_prices_from_disk() -> Dict:
    """从磁盘读最新价格基线(每次重读,不缓存)
    用 utf-8-sig 兼容 BOM (Windows 工具保存的 JSON 经常带 BOM)
    """
    with _DATA_PATH.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _load_prices() -> Dict:
    """加载价格基线(进程内缓存)"""
    global _PRICES_CACHE
    if _PRICES_CACHE is None:
        if not _DATA_PATH.exists():
            raise FileNotFoundError(f"价格基线文件不存在: {_DATA_PATH}")
        _PRICES_CACHE = _read_prices_from_disk()
        logger.info("fallback 价格基线已加载 version=%s path=%s",
                    _PRICES_CACHE.get("version"), _DATA_PATH.name)
    return _PRICES_CACHE


def reload_prices() -> Dict:
    """
    热重载价格基线 - 清空内存缓存,重新从 JSON 读取

    用途:
      - 价格基线更新时,调 POST /api/admin/reload-prices 即可生效,无需重启服务

    返回:
      重新加载后的价格字典(供 admin 接口回显 version/loaded_at)
    """
    global _PRICES_CACHE, _PRICES_LOADED_AT
    if not _DATA_PATH.exists():
        raise FileNotFoundError(f"价格基线文件不存在: {_DATA_PATH}")
    new_data = _read_prices_from_disk()
    old_version = _PRICES_CACHE.get("version") if _PRICES_CACHE else None
    _PRICES_CACHE = new_data
    _PRICES_LOADED_AT = datetime.now(timezone.utc).isoformat(timespec="seconds")
    logger.info(
        "fallback 价格基线热重载完成 old_version=%s new_version=%s",
        old_version, new_data.get("version"),
    )
    return new_data


def get_cache_meta() -> Dict:
    """返回缓存元信息(供 admin 接口展示)"""
    return {
        "version": _PRICES_CACHE.get("version") if _PRICES_CACHE else None,
        "loaded_at": _PRICES_LOADED_AT,
        "path": str(_DATA_PATH),
        "cached": _PRICES_CACHE is not None,
    }


# ============== 内部辅助 ==============
def _mid_price(spec: Dict, grade: str) -> float:
    """从 v3 JSON 某品类 spec 中,按 grade 取出参考单价

    W3 v3.5 收紧: 简装/中档仍取中位数 (low+high)/2;
    高档/豪华 改取 30% 分位 low + (high-low)*0.3
    (顾工 v3 JSON 高档/豪华区间值偏高,自标 TODO;
     用低端主导更贴近合肥装修市场实际报价)
    """
    lo, hi = spec[grade]
    if grade in ("高档", "豪华"):
        # 30% 分位:低端主导,削弱豪华档偏离
        return round(lo + (hi - lo) * 0.30, 2)
    # 简装/中档:中位数
    return round((lo + hi) / 2, 2)


def _resolve_qty(name: str, area: float) -> float:
    """查 _QTY_TABLE 算工程量;找不到抛错(数据/代码不一致)"""
    fn = _QTY_TABLE.get(name)
    if fn is None:
        raise KeyError(f"未配置工程量规则: {name} (v3 JSON 出现新品类?)")
    return float(fn(area))


def _line(name: str, category: str, unit: str, qty: float, unit_price: float) -> Tuple[QuoteItem, float]:
    """生成一条 QuoteItem 并返回 (item, total)"""
    total = round(qty * unit_price, 2)
    item = QuoteItem(
        name=name, category=category, unit=unit,
        quantity=qty, unit_price=unit_price, total=total,
    )
    return item, total


# ============== 核心计算 ==============
def compute_fallback(req: QuoteRequest) -> Tuple[QuoteResponse, List[dict]]:
    """
    用 v2 本地价格基线算报价

    算法(顾工报告 + v3 JSON):
      1. 按 grade 选档位,每个品类取 [低,高] 中位数
      2. 乘以工程量系数 -> 算每项小计
      3. 汇总:
         - 半包 = aux_total + labor_total
         - 全包 = + main_total
         - 整装 = + (main+aux+labor) × 0.4 家具家电
      4. 乘以 district_factor(区域系数)
      5. 加管理费 mgmt_rate(grade)
      6. 加税金 tax_rate(grade)
      7. 输出 QuoteResponse(breakdown 4 类+items ≥ 10)

    返回: (QuoteResponse, 内部明细 raw 列表,便于日志)
    """
    prices = _load_prices()
    grade = req.grade.value     # "简装"/"中档"/"高档"/"豪华"
    logger.info("=== v3 fallback 计算启动 v3 路径 === _DATA_PATH=%s", _DATA_PATH.name)
    pack = req.pack.value       # "半包"/"全包"/"整装"
    area = req.area
    district = req.district.value  # "蜀山区"/"庐阳区"/...

    items: List[QuoteItem] = []
    raw_items: List[dict] = []

    main_total = 0.0
    aux_total = 0.0
    labor_total = 0.0

    # 区域系数:乘到主材/辅材/人工/家具家电的每行 unit_price 上(避免负 unit_price)
    # mgmt/tax 自身不乘(它们是按 base 算的派生项,不是基础消耗)
    district_factor = float(prices["district_factor"].get(district, 1.0))

    # ===== 1. 主材(全包/整装 才计入;半包业主自购) =====
    # V4: 根据 brand_tier_* 决定各主材的取值档位(独立于 grade)
    brand_tier_map = {
        "地砖": req.brand_tier_tile.value if req.brand_tier_tile else None,
        "地板": req.brand_tier_floor.value if req.brand_tier_floor else None,
        "橱柜": req.brand_tier_cabinet.value if req.brand_tier_cabinet else None,
        "卫浴": req.brand_tier_bathroom.value if req.brand_tier_bathroom else None,
    }
    # 收集品牌档位结果(用于回显)
    material_brand_tier_out = {}
    if pack in ("全包", "整装"):
        for name, spec in prices["main"].items():
            unit = spec["unit"]
            # V4: 找主材名对应的品牌档
            brand_cat = None
            for cat, main_name in _MAIN_NAME_MAP.items():
                if main_name == name:
                    brand_cat = cat
                    break
            if brand_cat and brand_tier_map.get(brand_cat):
                # 用了 V4 独立品牌档
                effective_grade = _BRAND_TIER_TO_GRADE[brand_tier_map[brand_cat]]
                material_brand_tier_out[brand_cat] = brand_tier_map[brand_cat]
            else:
                # 沿用 grade
                effective_grade = grade
                if brand_cat:
                    material_brand_tier_out[brand_cat] = grade  # 回显用
            base_unit_price = _mid_price(spec, effective_grade)
            # 区域系数作用在单价上(factor<1 时单价变小,自然无负值)
            unit_price = round(base_unit_price * district_factor, 2)
            qty = _resolve_qty(name, area)
            # V4: SKU 品牌+规格
            brand_name, brand_spec = "", ""
            if brand_cat and brand_tier_map.get(brand_cat):
                brand_name, brand_spec = _pick_brand(brand_cat, brand_tier_map[brand_cat])
            sku_id = f"{name}-{brand_name or '默认'}" if brand_name else None
            item, total = _line(name, "主材", unit, qty, unit_price)
            # 补充 V4 SKU 字段
            if brand_name:
                item = item.model_copy(update={
                    "brand": brand_name,
                    "spec": brand_spec or spec.get("spec", ""),
                    "sku": sku_id,
                })
            items.append(item)
            raw_items.append({"name": name, "category": "主材",
                              "qty": qty, "unit_price": unit_price, "total": total,
                              "base_unit_price": base_unit_price, "district_factor": district_factor,
                              "brand_tier": brand_tier_map.get(brand_cat),
                              "effective_grade": effective_grade,
                              "brand": brand_name, "spec": brand_spec})
            main_total += total

    # ===== 2. 辅材(半包/全包/整装 全部计入) =====
    for name, spec in prices["aux"].items():
        unit = spec["unit"]
        base_unit_price = _mid_price(spec, grade)
        unit_price = round(base_unit_price * district_factor, 2)
        qty = _resolve_qty(name, area)
        item, total = _line(name, "辅材", unit, qty, unit_price)
        items.append(item)
        raw_items.append({"name": name, "category": "辅材",
                          "qty": qty, "unit_price": unit_price, "total": total,
                          "base_unit_price": base_unit_price, "district_factor": district_factor})
        aux_total += total

    # ===== 3. 人工(半包/全包/整装 全部计入) =====
    for name, spec in prices["labor"].items():
        unit = spec["unit"]
        base_unit_price = _mid_price(spec, grade)
        unit_price = round(base_unit_price * district_factor, 2)
        qty = _resolve_qty(name, area)
        item, total = _line(name, "人工", unit, qty, unit_price)
        items.append(item)
        raw_items.append({"name": name, "category": "人工",
                          "qty": qty, "unit_price": unit_price, "total": total,
                          "base_unit_price": base_unit_price, "district_factor": district_factor})
        labor_total += total

    # ===== 4. 整装家具家电(仅整装模式;硬编码 (main+aux+labor)×0.4) =====
    furniture_total = 0.0
    if pack == "整装":
        # 家具家电估算基于"已应用区域系数"的主材+辅材+人工(更贴近实际)
        base = main_total + aux_total + labor_total
        furniture_total = round(base * _FURNITURE_RATE, 2)
        item = QuoteItem(
            name="家具家电(整体软装)", category="主材", unit="套",
            quantity=1, unit_price=furniture_total, total=furniture_total,
        )
        items.append(item)
        raw_items.append({"name": "家具家电", "category": "主材",
                          "qty": 1, "unit_price": furniture_total, "total": furniture_total,
                          "district_factor": 1.0})
        # 家具家电折入 material(breakdown 里 material 包含家具家电)
        main_total += furniture_total

    # ===== 4.4 V5: 特殊需求计价(地暖/中央空调/新风等) =====
    # P0 级修复: 之前完全漏算! 89m² 三个全选应加约 5-6 万
    special_total = 0.0
    special_items_added: List[str] = []
    if req.special:
        for s in req.special:
            if s in _SPECIAL_PRICE:
                spec = _SPECIAL_PRICE[s]
                if "flat" in spec:
                    special_total += spec["flat"]
                    special_items_added.append(f"{s}¥{int(spec['flat']/10000)}万")
                else:
                    # 按面积算: 取中位价 × 建筑面积
                    mid = (spec["min"] + spec["max"]) / 2
                    cost = round(mid * area, 2)
                    special_total += cost
                    special_items_added.append(f"{s}¥{int(mid)}/m²")
    
    if special_total > 0:
        # 名字控制在 40 字符内(避免 Pydantic max_length=40 错误)
        # 多个特殊需求时简写: "特殊需求×N项"
        if len(special_items_added) > 1:
            name = f"特殊需求({len(special_items_added)}项)"
        else:
            name = f"特殊需求({special_items_added[0]})"
        item = QuoteItem(
            name=name,
            category="辅材", unit="项", quantity=1,
            unit_price=special_total, total=special_total,
            brand="", spec="+".join(special_items_added) + "(顾工 V5 中位)",
        )
        items.append(item)
        raw_items.append({
            "name": "特殊需求", "category": "辅材",
            "qty": 1, "unit_price": special_total, "total": special_total,
        })
        aux_total += special_total

    # ===== 4.5 V4: 拆改费用(独立行, 加入主材) =====
    demolition_total = 0.0
    if req.demolition_wall_area and req.demolition_wall_area > 0:
        wall_qty = round(req.demolition_wall_area, 2)
        wall_total = round(wall_qty * _DEMOLITION_WALL_PRICE, 2)
        item = QuoteItem(
            name="拆墙(原有结构拆除)", category="主材", unit="m2",
            quantity=wall_qty, unit_price=_DEMOLITION_WALL_PRICE, total=wall_total,
            brand="", spec=f"拆墙 80元/m²(顾工 V4 中位,含清运)",
        )
        items.append(item)
        raw_items.append({"name": "拆墙", "category": "主材",
                          "qty": wall_qty, "unit_price": _DEMOLITION_WALL_PRICE, "total": wall_total})
        demolition_total += wall_total
        main_total += wall_total
    if req.demolition_build_area and req.demolition_build_area > 0:
        build_qty = round(req.demolition_build_area, 2)
        build_total = round(build_qty * _DEMOLITION_BUILD_PRICE, 2)
        item = QuoteItem(
            name="砌墙(新建轻质砖墙)", category="主材", unit="m2",
            quantity=build_qty, unit_price=_DEMOLITION_BUILD_PRICE, total=build_total,
            brand="", spec=f"砌墙 120元/m²(顾工 V4 中位,含双面抹灰)",
        )
        items.append(item)
        raw_items.append({"name": "砌墙", "category": "主材",
                          "qty": build_qty, "unit_price": _DEMOLITION_BUILD_PRICE, "total": build_total})
        demolition_total += build_total
        main_total += build_total

    # ===== 4.6 V4: 楼层搬运费(无电梯 + 高楼层) =====
    floor_carry_total = 0.0
    if req.floor is not None and req.floor > _FLOOR_NO_ELEVATOR_THRESHOLD:
        # 判断是否有电梯(缺省按楼层推测: 7 层以上通常有电梯)
        has_elevator = req.has_elevator if req.has_elevator is not None else (req.floor >= 7)
        if not has_elevator:
            extra_floors = req.floor - _FLOOR_NO_ELEVATOR_THRESHOLD
            carry_total = round(area * extra_floors * _FLOOR_CARRY_PRICE, 2)
            if carry_total > 0:
                item = QuoteItem(
                    name=f"高层搬运费(无电梯{req.floor}层)", category="辅材", unit="m2",
                    quantity=round(area * extra_floors, 2),
                    unit_price=_FLOOR_CARRY_PRICE, total=carry_total,
                    brand="", spec=f"{_FLOOR_CARRY_PRICE}元/m²/层,共{extra_floors}层",
                )
                items.append(item)
                raw_items.append({"name": "高层搬运费", "category": "辅材",
                                  "qty": area * extra_floors, "unit_price": _FLOOR_CARRY_PRICE, "total": carry_total})
                floor_carry_total = carry_total
                aux_total += carry_total

    # 基础消耗总和(主材含家具家电 + 辅材 + 人工,所有项均已应用区域系数)
    base_consumption = main_total + aux_total + labor_total
    logger.info(
        "区域系数应用 district=%s factor=%.2f base_consumption(含家具家电)=%.2f",
        district, district_factor, base_consumption,
    )

    # ===== 5. 管理费(基于基础消耗总和) =====
    # W3 v3.5 收紧:管理费率封顶 0.10(豪华 12% 太狠,178万×12%=21.4万)
    # 高档 0.10,豪华 0.10(跟中档平齐,体现管理费率不跟档位线性增长)
    raw_mgmt_rate = float(prices["mgmt_rate"][grade])
    mgmt_rate = min(raw_mgmt_rate, 0.10)
    mgmt_cost = round(base_consumption * mgmt_rate, 2)
    items.append(QuoteItem(
        name=f"管理费({int(mgmt_rate*100)}%)", category="管理", unit="项",
        quantity=1, unit_price=mgmt_cost, total=mgmt_cost,
    ))
    raw_items.append({"name": "管理费", "category": "管理",
                      "qty": 1, "unit_price": mgmt_cost, "total": mgmt_cost})

    # ===== 6. 税金(基于 base_consumption + mgmt_cost) =====
    tax_rate = float(prices["tax_rate"][grade])
    tax_base = base_consumption + mgmt_cost
    tax_cost = round(tax_base * tax_rate, 2)
    items.append(QuoteItem(
        name=f"税金(增值税{int(tax_rate*100)}%)", category="税金", unit="项",
        quantity=1, unit_price=tax_cost, total=tax_cost,
    ))
    raw_items.append({"name": "税金", "category": "税金",
                      "qty": 1, "unit_price": tax_cost, "total": tax_cost})

    # ===== 7. 汇总 =====
    # total = 基础消耗(含家具家电,已应用区域系数) + 管理费 + 税金
    # breakdown 4 类(主材+辅材 / 人工 / 管理费 / 税金) 之和必须 = total
    # material 字段 = 主材(含家具家电) + 辅材
    total = round(base_consumption + mgmt_cost + tax_cost, 2)

    breakdown = BreakdownItem(
        material=round(main_total + aux_total, 2),  # 主材(含家具家电) + 辅材
        labor=round(labor_total, 2),
        management=mgmt_cost,
        tax=tax_cost,
    )

    response = QuoteResponse(
        success=True,
        source="fallback",
        request_id=None,
        total=total,
        breakdown=breakdown,
        items=items,
        area=area,
        grade=grade,
        pack=pack,
        district=district,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # V4 回显
        rooms=req.rooms,
        floor=req.floor,
        has_elevator=req.has_elevator,
        demolition_cost=demolition_total if demolition_total > 0 else None,
        material_brand_tier=material_brand_tier_out if material_brand_tier_out else None,
    )

    # ===== V4 5 项分类 breakdown_v4 填充 =====
    main_items = [i for i in items if i.category == "主材"]
    aux_items = [i for i in items if i.category == "辅材"]
    labor_items = [i for i in items if i.category == "人工"]
    mgmt_items = [i for i in items if i.category == "管理"]
    tax_items = [i for i in items if i.category == "税金"]

    main_sum = round(sum(i.total for i in main_items), 2)
    aux_sum = round(sum(i.total for i in aux_items), 2)
    labor_sum = round(sum(i.total for i in labor_items), 2)
    mgmt_sum = round(sum(i.total for i in mgmt_items), 2)
    tax_sum = round(sum(i.total for i in tax_items), 2)

    # 5 项分类校验: main + aux + labor + mgmt + tax == total
    five_sum = main_sum + aux_sum + labor_sum + mgmt_sum + tax_sum
    if abs(five_sum - total) > 1.0:
        # 凑整修正(管理费/税金行可能因为浮点略有偏差, 用 total 减法校正)
        # 把偏差计入 主材(主材数量大,容错好)
        diff = round(total - five_sum, 2)
        if main_items:
            last_main = main_items[-1]
            corrected = last_main.model_copy(update={
                "total": round(last_main.total + diff, 2),
            })
            # 替换
            for idx, it in enumerate(items):
                if it.name == last_main.name:
                    items[idx] = corrected
                    break
            main_sum = round(main_sum + diff, 2)
            logger.warning("V4 5 项分类凑整修正 diff=%.2f 计入 %s", diff, last_main.name)

    breakdown_v4 = BreakdownV4(
        main_material=CategoryBlock(category="主材", total=main_sum, items=main_items),
        auxiliary=CategoryBlock(category="辅材", total=aux_sum, items=aux_items),
        labor=CategoryBlock(category="人工", total=labor_sum, items=labor_items),
        management=CategoryBlock(category="管理费", total=mgmt_sum, items=mgmt_items),
        tax=CategoryBlock(category="税费", total=tax_sum, items=tax_items),
    )
    response.breakdown_v4 = breakdown_v4
    
    # ===== V5: ML 特征工程(为自主决策树模型铺路) =====
    # 每次 fallback 计算都输出结构化特征字典
    # 格式与 scikit-learn DecisionTreeRegressor.fit(X, y) 完全兼容
    # X = pd.DataFrame(features_list)
    # model.fit(X, [total])  # 等顾工收集 100 条真实数据后训练
    ml_features = _extract_features(
        req=req, area=area, grade=grade, pack=pack, district=district,
        floor=req.floor, has_elevator=req.has_elevator,
        demolition_wall=req.demolition_wall_area or 0,
        demolition_build=req.demolition_build_area or 0,
        special=req.special or [],
        brand_tier_out=material_brand_tier_out,
    )
    # 附加到 response 上(前端不展示, 仅用于 DB 落库)
    response.ml_features = ml_features  # type: ignore[attr-defined]
    
    logger.info(
        "fallback v3 计算完成 area=%.1f grade=%s pack=%s district=%s "
        "main=%.2f aux=%.2f labor=%.2f base=%.2f factor=%.2f "
        "mgmt=%.2f tax=%.2f total=%.2f items=%d "
        "special_total=%.2f ml_features=%s",
        area, grade, pack, district,
        main_total, aux_total, labor_total, base_consumption, district_factor,
        mgmt_cost, tax_cost, total, len(items),
        special_total,
        json.dumps(ml_features, ensure_ascii=False),
    )
    return response, raw_items
