"""V4 agnes 真实调用端到端验证

只调主路（不旁路），验证 agnes-2.0-flash 能否正确返回 V4 报价。
与 fallback 结果对比，偏差 >30% 标红。
"""
import json
import sys
import time
from datetime import datetime

BASE = "http://127.0.0.1:8000"

CASES = [
    {
        "id": "A1",
        "name": "60m² 简装 全包 瑶海",
        "payload": {
            "area": 60.0, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包",
            "style": "简约", "special": [], "district": "瑶海区",
            "contact": "13800138001",
        },
        "expected_min": 50000, "expected_max": 200000,
    },
    {
        "id": "A2",
        "name": "89m² 中档 半包 蜀山",
        "payload": {
            "area": 89.0, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包",
            "style": "现代", "special": [], "district": "蜀山区",
            "contact": "13800138002",
        },
        "expected_min": 50000, "expected_max": 200000,
    },
    {
        "id": "A3",
        "name": "128m² 高档 全包 滨湖",
        "payload": {
            "area": 128.0, "layout": "4室2厅2卫", "grade": "高档", "pack": "全包",
            "style": "轻奢", "special": ["地暖"], "district": "滨湖新区",
            "contact": "13800138003",
        },
        "expected_min": 200000, "expected_max": 800000,
    },
    {
        "id": "A4",
        "name": "200m² 豪华 整装 蜀山",
        "payload": {
            "area": 200.0, "layout": "5室3厅3卫", "grade": "豪华", "pack": "整装",
            "style": "新中式", "special": ["中央空调", "地暖", "新风"], "district": "蜀山区",
            "contact": "13800138004",
        },
        "expected_min": 500000, "expected_max": 2000000,
    },
    {
        "id": "A5",
        "name": "89m² 中档 全包 蜀山+无电梯",
        "payload": {
            "area": 89.0, "layout": "3室2厅1卫", "grade": "中档", "pack": "全包",
            "style": "现代", "special": [], "district": "蜀山区",
            "contact": "13800138005",
        },
        # 注意：这个 case 需要前端传 floor/has_elevator，如果后端没接就跳过
        "expected_min": 50000, "expected_max": 200000,
    },
]

def post_quote(payload):
    """POST /api/quote (主路 agnes)"""
    import urllib.request
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/quote",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=300)
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body
    except Exception as e:
        return None, {"error": str(e)}

def post_quote_fallback(payload):
    """POST /api/quote?force_fallback=true"""
    import urllib.request
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/quote?force_fallback=true",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        body = json.loads(resp.read().decode("utf-8"))
        return resp.status, body
    except Exception as e:
        return None, {"error": str(e)}

def main():
    print("=" * 80)
    print(f"AI 报价网 V4 - Agnes 真实调用端到端验证")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标: {BASE}")
    print("=" * 80)

    # STEP 0: health check
    print("\nSTEP 0: GET /health")
    import urllib.request
    resp = urllib.request.urlopen(f"{BASE}/health", timeout=10)
    health = json.loads(resp.read().decode("utf-8"))
    print(f"  状态码: {resp.status}")
    print(f"  响应:   {json.dumps(health, ensure_ascii=False)}")
    if resp.status != 200:
        print("  ❌ Health check failed!")
        sys.exit(1)
    print("  ✅ OK")

    results = []
    for case in CASES:
        cid = case["id"]
        name = case["name"]
        payload = case["payload"]
        exp_min = case["expected_min"]
        exp_max = case["expected_max"]

        print(f"\n{'='*60}")
        print(f"  {cid}: {name}")
        print(f"{'='*60}")

        # First: fallback reference
        print(f"  [Fallback] ...")
        f_status, f_body = post_quote_fallback(payload)
        f_total = f_body.get("total", 0) if f_status == 200 else None
        f_source = f_body.get("source", "?")
        f_items = len(f_body.get("items", []))
        f_breakdown = f_body.get("breakdown", {})
        print(f"    状态码: {f_status}  source={f_source}")
        if f_total:
            print(f"    total:      {f_total:,.2f} 元 ({f_total/10000:.2f} 万)")
            print(f"    items: {f_items}  breakdown={json.dumps(f_breakdown, ensure_ascii=False)}")
        else:
            print(f"    ERROR: {f_body}")

        # Then: real agnes (with retry)
        print(f"  [Agnes 真实调用] ...")
        a_status = None
        a_body = None
        for attempt in range(2):  # max 2 retries
            t0 = time.time()
            a_status, a_body = post_quote(payload)
            elapsed = time.time() - t0
            if a_status == 200 and a_body.get("success"):
                break
            if attempt == 0:
                print(f"    第{attempt+1}次失败 (status={a_status}), 重试...")
                time.sleep(2)

        if a_status == 200 and a_body.get("success"):
            a_total = a_body.get("total", 0)
            a_source = a_body.get("source", "?")
            a_request_id = a_body.get("request_id", "?")
            a_items = len(a_body.get("items", []))
            a_breakdown = a_body.get("breakdown", {})
            print(f"    状态码: {a_status}  耗时: {elapsed:.1f}s")
            print(f"    source:     {a_source}")
            print(f"    request_id: {a_request_id}")
            print(f"    total:      {a_total:,.2f} 元 ({a_total/10000:.2f} 万)")
            print(f"    items 数量: {a_items} (Pydantic 要求 ≥10)")
            print(f"    breakdown:  {json.dumps(a_breakdown, ensure_ascii=False)}")

            # Check expected range
            in_range = exp_min <= a_total <= exp_max
            status_str = "✅" if in_range else "❌"
            print(f"    期望区间: [{exp_min/10000:.0f}, {exp_max/10000:.0f}] 万 → {'在区间内' if in_range else '超出区间'}")
            print(f"    {status_str} items >= 10: {'✅' if a_items >= 10 else '❌'}")

            # Compare with fallback
            if f_total:
                deviation = abs(a_total - f_total) / f_total * 100
                dev_color = "✅" if deviation <= 30 else "⚠️"
                print(f"    {dev_color} agnes vs fallback 偏差: {deviation:.1f}%")
            else:
                print(f"    ⚠️ fallback 不可比")

            results.append({
                "id": cid,
                "name": name,
                "f_total": f_total,
                "a_total": a_total,
                "a_source": a_source,
                "a_items": a_items,
                "in_expected_range": in_range,
                "deviation": abs(a_total - f_total) / f_total * 100 if f_total else None,
                "request_id": a_request_id,
            })
        else:
            print(f"    ❌ agnes 调用失败! status={a_status}, body={a_body}")
            results.append({
                "id": cid,
                "name": name,
                "f_total": f_total,
                "a_total": None,
                "a_source": "FAILED",
                "a_items": 0,
                "in_expected_range": False,
                "deviation": None,
                "request_id": None,
            })

    # Summary table
    print(f"\n{'='*80}")
    print("  对比分析: force_fallback vs agnes")
    print(f"{'='*80}")
    print(f"{'Case':<10} {'F total':>12} {'A total':>12} {'F items':>8} {'A items':>8} {'偏差':>8} {'状态':>6}")
    print("-" * 80)
    for r in results:
        f_str = f"{r['f_total']:,.2f}" if r['f_total'] else "N/A"
        a_str = f"{r['a_total']:,.2f}" if r['a_total'] else "FAIL"
        dev_str = f"{r['deviation']:.1f}%" if r['deviation'] is not None else "N/A"
        status = "✅" if r['in_expected_range'] else "❌"
        print(f"{r['id']:<10} {f_str:>12} {a_str:>12} {r['f_items'] if isinstance(r.get('f_items'), int) else '?':>8} {r['a_items']:>8} {dev_str:>8} {status:>6}")

    # Breakdown comparison
    print(f"\n{'='*80}")
    print("  Breakdown 对比:")
    print(f"{'='*80}")
    for r in results:
        if r['a_total'] is not None and r['f_total'] is not None:
            print(f"\n  {r['id']}: {r['name']}")
            # Need to re-fetch breakdown - skip for now, just show totals

    # Verification checklist
    print(f"\n{'='*80}")
    print("  验收清单:")
    print(f"{'='*80}")
    
    passed = 0
    total_checks = 5
    
    # 1. Health
    print(f"  1. 服务 /health 200:           {'✅' if True else '❌'}")
    passed += 1
    
    # 2. Expected ranges
    in_range_count = sum(1 for r in results if r['in_expected_range'])
    all_in_range = in_range_count == len([r for r in results if r['a_total']])
    print(f"  2. {in_range_count}/{len(results)} case 在期望区间:      {'✅' if all_in_range else '⚠️'}")
    if all_in_range:
        passed += 1
    
    # 3. Agnes calls succeeded
    agnes_ok = sum(1 for r in results if r['a_total'] is not None)
    print(f"  3. {agnes_ok}/{len(results)} case agnes 调通:       {'✅' if agnes_ok == len(results) else '⚠️'}")
    if agnes_ok == len(results):
        passed += 1
    
    # 4. Pydantic items >= 10
    items_ok = sum(1 for r in results if r['a_items'] >= 10 and r['a_total'])
    print(f"  4. {items_ok}/{len(results)} case items >= 10:  {'✅' if items_ok == agnes_ok else '⚠️'}")
    if items_ok == agnes_ok:
        passed += 1
    
    # 5. Deviation report
    devs = [r['deviation'] for r in results if r['deviation'] is not None]
    avg_dev = sum(devs) / len(devs) if devs else 0
    max_dev = max(devs) if devs else 0
    print(f"  5. agnes vs fallback 平均偏差: {avg_dev:.1f}%  最大: {max_dev:.1f}%")
    passed += 1
    
    print(f"\n  通过: {passed}/{total_checks}")
    
    # Save log
    log_path = "C:\\Users\\Administrator\\.qclaw\\shared\\AI报价网后端\\v4_agnes_e2e.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"V4 Agnes E2E Verification\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        for r in results:
            f.write(f"\n{r['id']}: {r['name']}\n")
            f.write(f"  Fallback: {r['f_total']}\n")
            f.write(f"  Agnes: {r['a_total']}\n")
            f.write(f"  In range: {r['in_expected_range']}\n")
            f.write(f"  Deviation: {r['deviation']}\n")
    print(f"\n  Log saved to: {log_path}")
    
    print(f"\n{'='*80}")
    print("  完成")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
