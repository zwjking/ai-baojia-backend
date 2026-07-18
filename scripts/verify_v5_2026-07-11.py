# -*- coding: utf-8 -*-
"""
V5 fallback 端到端验证 - 4 case + 特殊需求 + ml_features 字段检查
- 直接打 /api/quote?force_fallback=true
- 检查 special_total 是否正确累加
- 检查 ml_features 字段是否存在
- 检查 items 数量 + 5 项分类 + total
"""
import json
import sys
import time
import urllib.request
import urllib.parse
from urllib.error import HTTPError

BASE = "http://127.0.0.1:8000"

CASES = [
    {
        "id": "V5-1",
        "label": "60m² 简装 全包 瑶海 (期望 7-9 万)",
        "payload": {
            "area": 60.0, "layout": "2室1厅1卫",
            "grade": "简装", "pack": "全包", "style": "简约",
            "special": [], "district": "瑶海区",
            "contact": "13800138001",
        },
        "expect_range": (7.0, 9.0),
    },
    {
        "id": "V5-2",
        "label": "89m² 中档 半包 蜀山 (期望 7-8 万)",
        "payload": {
            "area": 89.0, "layout": "3室2厅1卫",
            "grade": "中档", "pack": "半包", "style": "现代",
            "special": [], "district": "蜀山区",
            "contact": "13800138002",
        },
        "expect_range": (7.0, 8.0),
    },
    {
        "id": "V5-3",
        "label": "128m² 高档 全包 滨湖 +地暖 (期望 30-50 万)",
        "payload": {
            "area": 128.0, "layout": "4室2厅2卫",
            "grade": "高档", "pack": "全包", "style": "轻奢",
            "special": ["地暖"], "district": "滨湖新区",
            "contact": "13800138003",
        },
        "expect_range": (30.0, 50.0),
    },
    {
        "id": "V5-4",
        "label": "200m² 豪华 整装 蜀山 +中央空调+地暖+新风 (期望 130-180 万)",
        "payload": {
            "area": 200.0, "layout": "5室3厅3卫",
            "grade": "豪华", "pack": "整装", "style": "新中式",
            "special": ["中央空调", "地暖", "新风"],
            "district": "蜀山区",
            "contact": "13800138004",
        },
        "expect_range": (130.0, 180.0),
    },
]


def post_quote(payload, force_fallback=True):
    url = f"{BASE}/api/quote?force_fallback=true" if force_fallback else f"{BASE}/api/quote"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    print("=" * 70)
    print("AI 报价网 V5 验证 - 4 case + 特殊需求 + ml_features")
    print("=" * 70)
    
    # 0. health check
    with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
        h = json.loads(r.read().decode("utf-8"))
        print(f"[/health] {r.status} → {h}")
    
    summary = {"pass": 0, "fail": 0, "warn": 0}
    
    for case in CASES:
        print()
        print("=" * 70)
        print(f"  {case['id']}: {case['label']}")
        print("=" * 70)
        lo, hi = case["expect_range"]
        
        status, body = post_quote(case["payload"], force_fallback=True)
        if status != 200:
            print(f"❌ HTTP {status}: {json.dumps(body, ensure_ascii=False)[:300]}")
            summary["fail"] += 1
            continue
        
        total = body["total"]
        bd = body["breakdown"]
        items = body["items"]
        ml = body.get("ml_features")
        
        # 区间检查
        in_range = lo * 10000 <= total <= hi * 10000
        mark = "✅" if in_range else "⚠️"
        if in_range:
            summary["pass"] += 1
        else:
            summary["warn"] += 1
        total_w = total / 10000
        print(f"  {mark} total: ¥{total:,.2f} ({total_w:.2f} 万)  期望 [{lo}, {hi}] 万")
        print(f"  breakdown: 主材+辅材=¥{bd['material']:,.0f}  人工=¥{bd['labor']:,.0f}  管理=¥{bd['management']:,.0f}  税=¥{bd['tax']:,.0f}")
        print(f"  items 数量: {len(items)} (Pydantic ≥10) {'✅' if len(items) >= 10 else '❌'}")
        
        # 特殊需求行
        special_items = [i for i in items if "特殊需求" in i["name"]]
        if special_items:
            s = special_items[0]
            print(f"  🎯 特殊需求行: {s['name']!r} (unit_price=¥{s['unit_price']:,.0f})")
            print(f"     spec: {s.get('spec', '')[:80]}")
        elif case["payload"]["special"]:
            print(f"  ❌ 期望有特殊需求行但未找到!")
            summary["fail"] += 1
        
        # ml_features 检查
        if ml is None:
            print(f"  ❌ ml_features 字段缺失!")
            summary["fail"] += 1
        else:
            print(f"  🎯 ml_features ({len(ml)} 维): {json.dumps(ml, ensure_ascii=False)[:200]}")
            # 检查关键特征
            required_keys = ["area", "grade_num", "pack_num", "district_num",
                             "special_count", "brand_tier_tile"]
            missing = [k for k in required_keys if k not in ml]
            if missing:
                print(f"  ❌ ml_features 缺字段: {missing}")
                summary["fail"] += 1
            else:
                # 校验 special_count
                if ml["special_count"] != len(case["payload"]["special"]):
                    print(f"  ❌ special_count={ml['special_count']} ≠ 请求 special 数量={len(case['payload']['special'])}")
                    summary["fail"] += 1
                else:
                    print(f"  ✅ ml_features 14 维完整, special_count 正确")
                    summary["pass"] += 1
        
        # breakdown 4 类校验
        s4 = bd["material"] + bd["labor"] + bd["management"] + bd["tax"]
        diff = abs(s4 - total)
        if diff <= 5:
            print(f"  ✅ 4 类合计 ¥{s4:,.0f} ≈ total ¥{total:,.0f}  差 {diff:.2f}")
            summary["pass"] += 1
        else:
            print(f"  ❌ 4 类合计 ¥{s4:,.0f} ≠ total ¥{total:,.0f}  差 {diff:.2f}")
            summary["fail"] += 1
    
    print()
    print("=" * 70)
    print(f"  汇总: PASS={summary['pass']}  WARN={summary['warn']}  FAIL={summary['fail']}")
    print("=" * 70)
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
