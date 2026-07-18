"""
W3 #4 agnes-only 重跑 - 改进 prompt 后只跑 A1-A4
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:8000"
SHARED_DIR = Path(r"C:\Users\Administrator\.qclaw\shared\AI报价网后端")
DESKTOP_DIR = Path(r"C:\Users\Administrator\Desktop")
LOG_SHARED = SHARED_DIR / "demo_v3_2026-07-10_agnes_rerun.log"
LOG_DESKTOP = DESKTOP_DIR / "AI报价网_W3_v3验证_2026-07-10_agnes_rerun.log"

CASES = [
    {
        "id": "A1", "name": "60m² 简装 全包 瑶海 (agnes 真实)",
        "payload": {
            "area": 60.0, "layout": "2室1厅1卫", "grade": "简装", "pack": "全包",
            "style": "简约", "special": [], "district": "瑶海区",
            "contact": "13800138011",
        },
        "force_fallback": False,
        "expected_min": 50000, "expected_max": 200000,
    },
    {
        "id": "A2", "name": "89m² 中档 半包 蜀山 (agnes 真实)",
        "payload": {
            "area": 89.0, "layout": "3室2厅1卫", "grade": "中档", "pack": "半包",
            "style": "现代", "special": [], "district": "蜀山区",
            "contact": "13800138012",
        },
        "force_fallback": False,
        "expected_min": 50000, "expected_max": 200000,
    },
    {
        "id": "A3", "name": "128m² 高档 全包 滨湖 (agnes 真实)",
        "payload": {
            "area": 128.0, "layout": "4室2厅2卫", "grade": "高档", "pack": "全包",
            "style": "轻奢", "special": ["地暖"], "district": "滨湖新区",
            "contact": "13800138013",
        },
        "force_fallback": False,
        "expected_min": 200000, "expected_max": 800000,
    },
    {
        "id": "A4", "name": "200m² 豪华 整装 蜀山 (agnes 真实)",
        "payload": {
            "area": 200.0, "layout": "5室3厅3卫", "grade": "豪华", "pack": "整装",
            "style": "新中式", "special": ["中央空调", "地暖", "新风"], "district": "蜀山区",
            "contact": "13800138014",
        },
        "force_fallback": False,
        "expected_min": 500000, "expected_max": 2000000,
    },
]


class TeeLogger:
    def __init__(self, paths):
        self.files = [open(p, "w", encoding="utf-8") for p in paths]

    def write(self, msg):
        try:
            print(msg, flush=True)
        except UnicodeEncodeError:
            print(msg.encode("ascii", "replace").decode("ascii"), flush=True)
        for f in self.files:
            f.write(msg + "\n")
            f.flush()

    def close(self):
        for f in self.files:
            f.close()


def main():
    logger = TeeLogger([LOG_SHARED, LOG_DESKTOP])
    logger.write(f"AI 报价网 W3 #4 agnes-only 重跑 (改进 prompt 后)")
    logger.write(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.write(f"目标: {BASE}")
    logger.write(f"Log: {LOG_SHARED}")

    # health
    health = requests.get(f"{BASE}/health", timeout=5)
    logger.write(f"health: {health.status_code}")

    results = {}
    for case in CASES:
        logger.write(f"\n{'='*70}\n  {case['id']}: {case['name']}\n{'='*70}")
        url = f"{BASE}/api/quote"
        logger.write(f"Payload: {json.dumps(case['payload'], ensure_ascii=False)}")

        t0 = time.perf_counter()
        try:
            r = requests.post(url, json=case["payload"], timeout=180)
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.write(f"❌ EXCEPTION {elapsed:.0f}ms: {e}")
            results[case["id"]] = {"status": -1, "elapsed_ms": elapsed, "body": {"error": str(e)}}
            continue
        elapsed = (time.perf_counter() - t0) * 1000

        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"text": r.text[:300]}
        logger.write(f"状态码: {r.status_code}  耗时: {elapsed:.0f}ms")
        logger.write(f"  source:     {body.get('source')}")
        logger.write(f"  request_id: {body.get('request_id')}")
        logger.write(f"  total:      {body.get('total', 0):,.2f} 元 ({body.get('total', 0)/10000:.2f} 万)")
        logger.write(f"  breakdown:  {body.get('breakdown')}")
        logger.write(f"  items 数量: {len(body.get('items', []))}")
        if "items" in body:
            for it in body["items"][:5]:
                logger.write(f"    - {it.get('category')} | {it.get('name')} | {it.get('quantity')}×{it.get('unit_price'):,.2f} = {it.get('total'):,.2f}")
        if body.get('total', 0) > 0:
            emin, emax = case["expected_min"], case["expected_max"]
            in_range = emin <= body["total"] <= emax
            mark = "✅" if in_range else "⚠️"
            logger.write(f"  {mark} 期望 [{emin/10000:.1f}, {emax/10000:.1f}] 万")

        results[case["id"]] = {"status": r.status_code, "elapsed_ms": elapsed, "body": body}

    # 对比 fallback (从主 log 读)
    logger.write(f"\n\n{'='*70}\n  对比 (v3 fallback vs agnes 真实)\n{'='*70}")
    fallback_totals = {
        "A1": 78078.39, "A2": 74057.87, "A3": 464947.60, "A4": 1615182.49,
    }
    logger.write(f"\n{'Case':<6} {'F total':>14} {'A total':>14} {'A source':>10} {'偏差':>10} 状态")
    logger.write("-" * 80)
    for cid in ["A1", "A2", "A3", "A4"]:
        f_total = fallback_totals[cid]
        a_res = results.get(cid, {})
        a_body = a_res.get("body", {})
        a_total = a_body.get("total", 0) if isinstance(a_body, dict) else 0
        a_source = a_body.get("source", "?") if isinstance(a_body, dict) else "?"
        if a_total == 0:
            dev = "N/A"
            mark = "❌ agnes 失败"
        else:
            dev_pct = (a_total - f_total) / f_total * 100
            dev = f"{dev_pct:+.1f}%"
            mark = "✅" if abs(dev_pct) <= 30 else f"❌ 偏差 {abs(dev_pct):.1f}% > 30%"
        logger.write(f"{cid:<6} {f_total:>14,.2f} {a_total:>14,.2f} {a_source:>10} {dev:>10}  {mark}")

    # 总结
    logger.write(f"\n\n{'='*70}\n  总结\n{'='*70}")
    a_ok = sum(1 for cid in ["A1", "A2", "A3", "A4"] if results.get(cid, {}).get("body", {}).get("source") == "agnes")
    logger.write(f"  agnes 真实调用成功: {a_ok}/4")
    logger.write(f"  偏差 ≤30% 案例: {sum(1 for cid in ['A1','A2','A3','A4'] if (lambda b: b.get('total',0) > 0 and abs((b['total']-fallback_totals[cid])/fallback_totals[cid]*100) <= 30)(results.get(cid, {}).get('body', {})))}/4")
    logger.close()


if __name__ == "__main__":
    main()
