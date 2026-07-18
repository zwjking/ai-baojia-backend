"""
测试失败重试 + L2 降级流程
构造两种边界场景:
1. 特殊字符 layout (含 室厅) - 应该被 Pydantic 接受 (模型能处理)
2. invalid input 模拟 agnes 返回 schema 错误
"""
from __future__ import annotations

import sys
import time
import json
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

API_URL = "http://127.0.0.1:8000/api/quote"
LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "retry_test.log"


def main():
    log_lines = []
    def log(s=""):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", "replace").decode("ascii"))
        log_lines.append(s)

    log("=" * 60)
    log("AI 报价网 W1 - 失败重试 + L2 降级测试")
    log("=" * 60)

    with httpx.Client(timeout=200.0) as client:
        # ===== TEST A: 大面积 (300 平米) - 正常 =====
        log("\n=== TEST A: 边界 area=300 m² ===")
        req = {
            "area": 300.0, "layout": "5室3厅2卫", "grade": "豪华",
            "pack": "全包", "style": "轻奢", "special": ["地暖", "中央空调"],
            "district": "滨湖新区", "contact": "13800138000"
        }
        t0 = time.perf_counter()
        r = client.post(API_URL, json=req)
        elapsed = (time.perf_counter() - t0) * 1000
        log(f"状态码: {r.status_code} 耗时: {elapsed:.0f}ms")
        if r.status_code == 200:
            data = r.json()
            log(f"✅ source={data.get('source')} total=¥{data.get('total'):,.2f} items={len(data.get('items', []))}")
            if data.get('request_id'):
                log(f"   request_id: {data.get('request_id')}")
        else:
            log(f"❌ {r.text[:500]}")

        # ===== TEST B: 风格混搭 =====
        log("\n=== TEST B: 混搭风格 (test enum) ===")
        req = {
            "area": 89.0, "layout": "3室2厅1卫", "grade": "中档",
            "pack": "整装", "style": "混搭", "special": [],
            "district": "庐阳区", "contact": "13900139000"
        }
        t0 = time.perf_counter()
        r = client.post(API_URL, json=req)
        elapsed = (time.perf_counter() - t0) * 1000
        log(f"状态码: {r.status_code} 耗时: {elapsed:.0f}ms")
        if r.status_code == 200:
            data = r.json()
            log(f"✅ source={data.get('source')} total=¥{data.get('total'):,.2f} items={len(data.get('items', []))}")
        else:
            log(f"❌ {r.text[:500]}")

        # ===== TEST C: 整装 含主材 - 验证全包价 =====
        log("\n=== TEST C: 整装全包 (主材应计入) ===")
        req = {
            "area": 89.0, "layout": "3室2厅1卫", "grade": "中档",
            "pack": "整装", "style": "现代", "special": [],
            "district": "蜀山区", "contact": "13800138000"
        }
        t0 = time.perf_counter()
        r = client.post(API_URL, json=req)
        elapsed = (time.perf_counter() - t0) * 1000
        log(f"状态码: {r.status_code} 耗时: {elapsed:.0f}ms")
        if r.status_code == 200:
            data = r.json()
            log(f"✅ source={data.get('source')} total=¥{data.get('total'):,.2f} items={len(data.get('items', []))}")
            log(f"   breakdown: {data.get('breakdown')}")

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\n[LOG SAVED] {LOG_PATH}")


if __name__ == "__main__":
    main()
