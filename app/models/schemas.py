"""
Pydantic 数据模型 - 强校验

输入: 8 步问卷
  - area 数字 30-300
  - layout 字符串
  - grade 枚举(简装/中档/高档/豪华)
  - pack 枚举(半包/全包/整装)
  - style 字符串
  - special 数组(可空)
  - district 字符串
  - contact 合法手机号

输出: 报价 JSON
  - total 数字 > 0
  - breakdown 4 类费用
  - items 数组 ≥ 10 行
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ============== 枚举(硬约束) ==============
class GradeEnum(str, Enum):
    """装修档次(整体装修定位)"""
    SIMPLE = "简装"
    MIDDLE = "中档"
    HIGH = "高档"
    LUXURY = "豪华"


class BrandTierEnum(str, Enum):
    """主材品牌档次 - V4 新增(4 项主材每项可独立选 3 档)
    - ECONOMY  经济:基础品牌(诺贝尔/欧普普通线/欧派基础)
    - MIDDLE    中档:中端品牌(马可波罗/圣象/欧派/箭牌)
    - PREMIUM   高端:高端品牌(简一/世友/志邦高端线/汉斯格雅)
    """
    ECONOMY = "经济"
    MIDDLE = "中档"
    PREMIUM = "高端"


# V4 主材 4 项的字段名常量
MAIN_MATERIAL_CATEGORIES = ["地砖", "地板", "橱柜", "卫浴"]


class PackEnum(str, Enum):
    """包工模式"""
    HALF = "半包"  # 施工方包辅材+人工,业主自购主材
    FULL = "全包"  # 施工方包主材+辅材+人工
    WHOLE = "整装"  # 全包 + 软装家电


class DistrictEnum(str, Enum):
    """合肥主要区域 - W1 简化版只支持 5 区"""
    SHUSHAN = "蜀山区"
    BAOHE = "包河区"
    YAOHai = "瑶海区"
    LUYANG = "庐阳区"
    BINHU = "滨湖新区"


# ============== 输入 - 8 步问卷 ==============
class QuoteRequest(BaseModel):
    """POST /api/quote 请求体 - 8 步问卷"""
    # 步骤 1: 建筑面积(30-300 平米)
    area: float = Field(
        ...,
        ge=30.0,
        le=300.0,
        description="建筑面积(平米),30-300 之间",
        examples=[89.0],
    )

    # 步骤 2: 户型
    layout: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="户型,如 '3室2厅1卫'",
        examples=["3室2厅1卫"],
    )

    # 步骤 3: 档次(V4 后来可省,从 brand_tier 自动推断)
    grade: Optional[GradeEnum] = Field(
        default=None,
        description="装修档次: 简装/中档/高档/豪华,缺省从 brand_tier 自动推断",
        examples=["中档"],
    )

    # 步骤 4: 包工模式
    pack: PackEnum = Field(
        ...,
        description="包工模式: 半包/全包/整装",
        examples=["半包"],
    )

    # 步骤 5: 风格
    style: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="装修风格: 现代/北欧/中式/简欧/工业/美式",
        examples=["现代"],
    )

    # 步骤 6: 特殊需求(数组,可空)
    special: List[str] = Field(
        default_factory=list,
        max_length=10,
        description="特殊需求: 新风/地暖/中央空调/智能家居 等",
        examples=[["地暖"]],
    )

    # 步骤 7: 区域
    district: DistrictEnum = Field(
        ...,
        description="合肥区域: 蜀山区/包河区/瑶海区/庐阳区/滨湖新区",
        examples=["蜀山区"],
    )

    # ====== V4 新增字段(可选,缺失时按 V3 默认) ======

    # 房间数: 几室几厅几卫 (例 "3-2-1" 表示 3室2厅1卫)
    rooms: Optional[str] = Field(
        default=None,
        max_length=20,
        description="V4 房间数(几室几厅几卫),格式 'X-Y-Z' 或 '3室2厅1卫'",
        examples=["3-2-1"],
    )

    # 楼层信息
    floor: Optional[int] = Field(
        default=None,
        ge=-3,
        le=120,
        description="V4 所在楼层(地下-3 到 120)",
        examples=[18],
    )

    has_elevator: Optional[bool] = Field(
        default=None,
        description="V4 是否有电梯(true/false,缺省按楼层判断)",
        examples=[True],
    )

    # 拆改量
    demolition_wall_area: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=500.0,
        description="V4 拆墙面积 m²(0=不拆改)",
        examples=[8.5],
    )
    demolition_build_area: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=500.0,
        description="V4 砌墙面积 m²(0=不新建)",
        examples=[5.0],
    )

    # 主材品牌档次(4 项独立选档)
    brand_tier_tile: Optional[BrandTierEnum] = Field(
        default=None,
        description="V4 地砖品牌档次: 经济/中档/高端",
        examples=["中档"],
    )
    brand_tier_floor: Optional[BrandTierEnum] = Field(
        default=None,
        description="V4 地板品牌档次: 经济/中档/高端",
        examples=["中档"],
    )
    brand_tier_cabinet: Optional[BrandTierEnum] = Field(
        default=None,
        description="V4 橱柜品牌档次: 经济/中档/高端",
        examples=["中档"],
    )
    brand_tier_bathroom: Optional[BrandTierEnum] = Field(
        default=None,
        description="V4 卫浴品牌档次: 经济/中档/高端",
        examples=["中档"],
    )

    # 步骤 8: 联系方式(留资)
    contact: str = Field(
        ...,
        description="手机号(11位,1开头)",
        examples=["13800138000"],
    )

    @field_validator("contact")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        """校验手机号: 11位, 1[3-9]开头"""
        v = v.strip()
        if not v.isdigit():
            raise ValueError("手机号必须是纯数字")
        if len(v) != 11:
            raise ValueError("手机号必须 11 位")
        if not v.startswith(("13", "14", "15", "16", "17", "18", "19")):
            raise ValueError("手机号必须 1[3-9] 开头")
        return v

    @field_validator("layout")
    @classmethod
    def validate_layout(cls, v: str) -> str:
        """户型: 必须含数字+室+厅(可含卫/厨/书房)"""
        v = v.strip()
        if "室" not in v and "厅" not in v:
            raise ValueError("户型格式不合法,应为 '3室2厅1卫' 类似格式")
        return v

    @field_validator("rooms")
    @classmethod
    def validate_rooms(cls, v):
        """V4 房间数: '3-2-1' 或 '3室2厅1卫' 两种格式"""
        if v is None:
            return v
        v = v.strip()
        if "-" in v:
            parts = v.split("-")
            if len(parts) != 3:
                raise ValueError("rooms 格式应为 'X-Y-Z' (几室-几厅-几卫)")
            try:
                bed, living, bath = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                raise ValueError("rooms 数字格式不合法")
            if bed < 0 or living < 0 or bath < 0 or bed > 20 or living > 10 or bath > 10:
                raise ValueError("rooms 数值超出合理范围")
        else:
            # 中文格式兼容
            if "室" not in v and "厅" not in v:
                raise ValueError("rooms 中文格式应为 '3室2厅1卫'")
        return v

    @field_validator("style")
    @classmethod
    def validate_style(cls, v: str) -> str:
        """风格: 必须在常见风格列表中"""
        allowed = {
            "现代", "简约", "北欧", "日式", "中式", "新中式",
            "欧式", "简欧", "美式", "工业", "轻奢", "侘寂", "混搭",
        }
        v = v.strip()
        if v not in allowed:
            raise ValueError(f"风格 '{v}' 不在支持列表中: {sorted(allowed)}")
        return v

    @model_validator(mode="after")
    def auto_infer_grade(self):
        """V4 后来: grade 缺失时,从 4 项 brand_tier 自动推断
        - 4 项全高端 -> 豪华
        - 至少 1 项中档 -> 中档
        - 其它 -> 简装
        """
        if self.grade is not None:
            return self
        tiers = [
            self.brand_tier_tile,
            self.brand_tier_floor,
            self.brand_tier_cabinet,
            self.brand_tier_bathroom,
        ]
        tiers = [t for t in tiers if t is not None]
        if not tiers:
            return self
        # 用 .value 拿真实字符串(Pydantic enum str() = "EnumClass.MEMBER")
        s = [t.value for t in tiers]
        v_high = sum(1 for x in s if "高端" in x)
        v_mid  = sum(1 for x in s if "中档" in x)
        if v_high >= 3:
            self.grade = GradeEnum.LUXURY
        elif v_mid >= 1:
            self.grade = GradeEnum.MIDDLE
        else:
            self.grade = GradeEnum.SIMPLE
        return self


# ============== 输出 - 报价 JSON ==============
class BreakdownItem(BaseModel):
    """4 类费用之一"""
    material: float = Field(..., ge=0, description="材料费")
    labor: float = Field(..., ge=0, description="人工费")
    management: float = Field(..., ge=0, description="管理费")
    tax: float = Field(..., ge=0, description="税金")


class QuoteItem(BaseModel):
    """报价明细行 - V4 升级支持 SKU 级别"""
    name: str = Field(..., min_length=2, max_length=40, description="项目名称")
    category: str = Field(..., description="类别: 主材/辅材/人工/管理/税金")
    unit: str = Field(..., min_length=1, max_length=10, description="计量单位")
    quantity: float = Field(..., ge=0, description="工程量")
    unit_price: float = Field(..., ge=0, description="单价(元)")
    total: float = Field(..., ge=0, description="合价(元)")

    # ====== V4 SKU 级别字段(可选,展开/折叠 UI 用) ======
    sku: Optional[str] = Field(
        default=None,
        max_length=80,
        description="V4 SKU 标识,如 '地砖-马可波罗-800x800'",
        examples=["客餐厅瓷砖-马可波罗-800x800"],
    )
    brand: Optional[str] = Field(
        default=None,
        max_length=30,
        description="V4 品牌名",
        examples=["马可波罗"],
    )
    spec: Optional[str] = Field(
        default=None,
        max_length=60,
        description="V4 规格/型号",
        examples=["800x800 抛釉砖"],
    )
    sub_items: Optional[List["QuoteItem"]] = Field(
        default=None,
        description="V4 子项(展开用),如 客餐厅瓷砖 → 抛光砖 25m² + 防滑砖 15m²",
    )

    @model_validator(mode="after")
    def check_total(self):
        # 容差 1 元(浮点)
        expected = round(self.quantity * self.unit_price, 2)
        if abs(self.total - expected) > 1.0:
            raise ValueError(
                f"合价 {self.total} 与 单价×工程量 {expected} 偏差过大"
            )
        return self


class QuoteResponse(BaseModel):
    """POST /api/quote 响应 - agnes 真实输出 / fallback V4"""
    success: bool = Field(default=True, description="是否成功")
    source: str = Field(..., description="数据源: agnes / fallback")
    request_id: Optional[str] = Field(default=None, description="agnes request id")
    total: float = Field(..., gt=0, description="总价(元)")
    breakdown: BreakdownItem = Field(..., description="4 类费用 (主材+辅材/人工/管理/税金)")
    items: List[QuoteItem] = Field(..., min_length=10, description="明细行(≥10,SKU 级别)")
    area: float = Field(..., description="回显: 建筑面积")
    grade: str = Field(..., description="回显: 档次")
    pack: str = Field(..., description="回显: 包工")
    district: str = Field(..., description="回显: 区域")
    generated_at: str = Field(..., description="生成时间(ISO8601)")

    # ====== V4 扩展字段 ======
    # 5 项分类统计(V4 任务要求: 主材/辅材/人工/管理费/税费 5 项分类,每项含 SKU 级别)
    breakdown_v4: Optional["BreakdownV4"] = Field(
        default=None,
        description="V4 5 项分类: 主材/辅材/人工/管理费/税费,含每项下 SKU 展开",
    )
    # V4 输入回显
    rooms: Optional[str] = Field(default=None, description="V4 房间数回显")
    floor: Optional[int] = Field(default=None, description="V4 楼层回显")
    has_elevator: Optional[bool] = Field(default=None, description="V4 电梯回显")
    demolition_cost: Optional[float] = Field(
        default=None, ge=0,
        description="V4 拆改费用合计(元,拆墙+砌墙)",
    )
    material_brand_tier: Optional[dict] = Field(
        default=None,
        description="V4 4 项主材品牌档次(地砖/地板/橱柜/卫浴)",
    )

    # ====== V5: ML 特征字典(为自主决策树模型铺路) ======
    # 14 维结构化特征, 与 scikit-learn DecisionTreeRegressor 输入完全兼容
    # X = pd.DataFrame([ml_features]) → model.predict(X) → total
    # 训练时用 DB 落库的真实数据; 推理时可作为输入校验或与 fallback 交叉验证
    ml_features: Optional[dict] = Field(
        default=None,
        description="V5 14 维 ML 特征字典(area/grade_num/pack_num/district_num/floor/"
                    "has_elevator/demolition_wall/demolition_build/special_count/"
                    "brand_tier_tile/brand_tier_floor/brand_tier_cabinet/brand_tier_bathroom)",
    )

    # V5+: ML 修正系数 (1.0=不修正, <1=fallback偏贵, >1=fallback偏便宜)
    # 算法: ratio = model.predict(ml_features) / fallback_total
    # 钳制在 [0.5, 2.0] 避免极端
    ml_correction: Optional[float] = Field(
        default=None,
        description="V5+ ML 修正系数 (0.5~2.0), 1.0=不修正",
    )
    # V5+: ML 修正后的总价 (fallback_total × ml_correction)
    # null = 未启用 ML 修正
    total_ml: Optional[float] = Field(
        default=None,
        description="V5+ ML 修正后总价 (fallback_total × ml_correction), null=未启用",
    )

    @model_validator(mode="after")
    def check_breakdown_4sum(self):
        """V3 兼容: 校验 breakdown 4 类费用之和 ≈ total - 硬约束(容差 5 元)"""
        s = (
            self.breakdown.material
            + self.breakdown.labor
            + self.breakdown.management
            + self.breakdown.tax
        )
        if abs(s - self.total) > 5.0:
            raise ValueError(
                f"4 类费用之和 {s:.2f} 与总价 {self.total:.2f} 偏差 > 5 元"
            )
        return self

    @model_validator(mode="after")
    def check_breakdown_v4_5sum(self):
        """V4 校验: breakdown_v4 5 项分类之和 ≈ total (容差 5 元)"""
        if self.breakdown_v4 is None:
            return self
        s = (
            self.breakdown_v4.main_material.total
            + self.breakdown_v4.auxiliary.total
            + self.breakdown_v4.labor.total
            + self.breakdown_v4.management.total
            + self.breakdown_v4.tax.total
        )
        if abs(s - self.total) > 5.0:
            raise ValueError(
                f"V4 5 项分类之和 {s:.2f} 与总价 {self.total:.2f} 偏差 > 5 元"
            )
        return self


class BreakdownV4(BaseModel):
    """V4 5 项分类明细 - 每项下挂 SKU 级别展开
    用于前端展开/折叠展示
    """
    main_material: "CategoryBlock" = Field(..., description="主材(含家具家电)")
    auxiliary: "CategoryBlock" = Field(..., description="辅材")
    labor: "CategoryBlock" = Field(..., description="人工")
    management: "CategoryBlock" = Field(..., description="管理费")
    tax: "CategoryBlock" = Field(..., description="税费")


class CategoryBlock(BaseModel):
    """5 项分类中的某一项: 合计 + SKU 列表"""
    category: str = Field(..., description="类别名: 主材/辅材/人工/管理费/税费")
    total: float = Field(..., ge=0, description="小计(元)")
    items: List[QuoteItem] = Field(default_factory=list, description="该分类下的明细(SKU 级别)")

    @model_validator(mode="after")
    def check_items_sum(self):
        """校验 CategoryBlock 内部 items 合价之和 ≈ total - 容差 5 元
        V4 兼容:
          - items 为空: 跳过(管理费/税金通常是按比例的总价,无 SKU 明细)
          - items 含 sub_items(子项): 跳过求和校验(展开后才是合价)
        """
        if not self.items:
            return self  # 空 items 不校验(管理费/税金场景)
        flat_totals = []
        for item in self.items:
            if item.sub_items:
                continue  # 分组容器,不计入
            flat_totals.append(item.total)
        s = sum(flat_totals)
        if abs(s - self.total) > 5.0:
            raise ValueError(
                f"分类 '{self.category}' 明细合价之和 {s:.2f} 与小计 {self.total:.2f} 偏差 > 5 元"
                f"(items={len(self.items)} 行,flat={len(flat_totals)} 行)"
            )
        return self


# ============== 留资 ==============
class LeadRequest(BaseModel):
    """POST /api/lead - 留资"""
    name: str = Field(..., min_length=1, max_length=20, description="姓名")
    phone: str = Field(..., description="手机号")
    district: Optional[DistrictEnum] = Field(default=None, description="区域")
    remark: Optional[str] = Field(default=None, max_length=200, description="备注")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit() or len(v) != 11 or not v.startswith(("13", "14", "15", "16", "17", "18", "19")):
            raise ValueError("手机号格式不合法(11位,1[3-9]开头)")
        return v


class LeadResponse(BaseModel):
    """POST /api/lead 响应"""
    success: bool
    lead_id: str
    message: str = "留资成功,稍后联系"

# ============== V4 自引用模型重建 ==============
QuoteItem.model_rebuild()
BreakdownV4.model_rebuild()
QuoteResponse.model_rebuild()
