"""给 QuoteResponse 加 ml_correction 和 total_ml 字段"""
import io
import sys

SCHEMAS = r"C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\models\schemas.py"

with open(SCHEMAS, "r", encoding="utf-8") as f:
    content = f.read()

# 锚点: ml_features 字段结束
anchor = '''    ml_features: Optional[dict] = Field(
        default=None,
        description="V5 14 缁?ML 鐗瑰緛瀛楀吀(area/grade_num/pack_num/district_num/floor/"
                    "has_elevator/demolition_wall/demolition_build/special_count/"
                    "brand_tier_tile/brand_tier_floor/brand_tier_cabinet/brand_tier_bathroom)",
    )'''

# 简化锚点（只取首行+中间+末行，避免 description 多行差异）
anchor_simple = '    ml_features: Optional[dict] = Field('

if anchor_simple not in content:
    print(f"❌ 找不到锚点")
    sys.exit(1)

# 找 ml_features 字段的最后一行 ") (闭合圆括号)
idx = content.find(anchor_simple)
# 找这一段的结束 "    )\n\n    @model_validator"
end_marker = "    @model_validator"
end_idx = content.find(end_marker, idx)
if end_idx == -1:
    print(f"❌ 找不到结束标记 @model_validator")
    sys.exit(1)

# 在 end_idx 前插入新字段
insertion = '''    # V5+: ML 修正系数 (1.0=不修正, <1=fallback偏贵, >1=fallback偏便宜)
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

'''

new_content = content[:end_idx] + insertion + content[end_idx:]

# 写回
with open(SCHEMAS, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"✅ 已插入 ml_correction + total_ml 字段")
print(f"   插入位置: 行 {content[:end_idx].count(chr(10)) + 1}")
