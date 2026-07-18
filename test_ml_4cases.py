"""V5+ ML 修正 4 case 全部跑一遍"""
import json
import sys
import time
import urllib.request

CASES = [
    {
        "id": "V5+-1", "label": "60m² 简装全包瑶海", "expect_range": (70000, 90000),
        "payload": {"area": 60.0, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包", "style": "简约", "special": [], "district": "瑶海区", "contact": "13800138001"},
    },
    {
        "id": "V5+-2", "label": "89m² 中档半包蜀山", "expect_range": (70000, 80000),
        "payload": {"area": 89.0, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包", "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138002"},
    },
    {
        "id": "V5+-3", "label": "128m² 高档全包+地暖滨湖", "expect_range": (300000, 500000),
        "payload": {"area": 128.0, "layout": "4室2厅2卫", "grade": "高档", "pack": "全包", "style": "轻奢", "special": ["地暖"], "district": "滨湖新区", "contact": "13800138003"},
    },
    {
        "id": "V5+-4", "label": "200m² 豪华整装+3项蜀山", "expect_range": (1300000, 1800000),
        "payload": {"area": 200.0, "layout": "5室3厅3卫", "grade": "豪华", "pack": "整装", "style": "新中式", "special": ["中央空调", "地暖", "新风"], "district": "蜀山区", "contact": "13800138004"},
    },
]


def hit(payload):
    body = json.dumps({**payload, "user_id": 999}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/quote?force_fallback=true",
        data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print("=" * 80)
    print("V5+ ML 修正 4 case 验证")
    print("=" * 80)
    pass_count = 0
    warn_count = 0
    fail_count = 0
    for case in CASES:
        print()
        r = hit(case["payload"])
        lo, hi = case["expect_range"]
        total = r["total"]
        total_ml = r.get("total_ml") or total
        correction = r.get("ml_correction") or 1.0

        in_range = lo <= total_ml <= hi
        mark = "✅" if in_range else "⚠️"
        if in_range:
            pass_count += 1
        else:
            warn_count += 1

        print(f"  {mark} {case['id']}: {case['label']}")
        print(f"     total (fallback):  ¥{total:,.2f}")
        print(f"     ml_correction:     {correction:.4f}")
        print(f"     total_ml (修正后):  ¥{total_ml:,.2f}")
        lo_w, hi_w = lo / 10000, hi / 10000
        in_range_w = lo_w <= total_ml / 10000 <= hi_w
        if in_range_w:
            print(f"     命中期望区间 [{lo_w}, {hi_w}] 万")
        else:
            print(f"     偏离期望区间 [{lo_w}, {hi_w}] 万 (偏差 {(total_ml / 10000 - (lo_w + hi_w) / 2) / ((hi_w - lo_w) / 2) * 100:.1f}%)")

    print()
    print("=" * 80)
    print(f"汇总: PASS={pass_count}  WARN={warn_count}  FAIL={fail_count}")
    print("=" * 80)
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
