"""
AI 报价网 W1 - 端到端 demo 验证脚本

使用:
  python scripts/test_quote.py

要求:
  1. FastAPI 服务先在 8000 端口运行
  2. .env 已配置 AGNES_API_KEY

输出:
  - 打印 total / breakdown / items 前 3 行
  - 保存到 logs/demo_2026-07-15.log
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Windows GBK console fix - 强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

# 项目根
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = BASE_DIR / "logs" / "demo_2026-07-15.log"

API_URL = "http://127.0.0.1:8000/api/quote"

# W1 8 步问卷 - 硬编码 (89m² 3室2厅 中档半包 现代 蜀山区 张三 13800138000)
HARDCODED_REQUEST = {
    "area": 89.0,
    "layout": "3室2厅",
    "grade": "中档",
    "pack": "半包",
    "style": "现代",
    "special": [],
    "district": "蜀山区",
    "contact": "13800138000",
}

# 错误手机号 - 用来触发 422
INVALID_REQUEST = {
    "area": 89.0,
    "layout": "3室2厅",
    "grade": "中档",
    "pack": "半包",
    "style": "现代",
    "special": [],
    "district": "蜀山区",
    "contact": "12345",  # 错的
}


def banner(s: str) -> str:
    return f"\n{'='*60}\n{s}\n{'='*60}"


def main():
    log_lines = []
    def log(s=""):
        # Replace problematic chars for Windows GBK console
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode("ascii", "replace").decode("ascii"))
        log_lines.append(s)

    log(banner("AI 报价网 W1 - 端到端 demo 验证"))
    log(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"目标: {API_URL}")
    log(f"问卷: {json.dumps(HARDCODED_REQUEST, ensure_ascii=False, indent=2)}")

    with httpx.Client(timeout=200.0) as client:
        # ===== 1. /health =====
        log(banner("TEST 1: GET /health"))
        t0 = time.perf_counter()
        try:
            r = client.get("http://127.0.0.1:8000/health")
            elapsed = (time.perf_counter() - t0) * 1000
            log(f"状态码: {r.status_code}")
            log(f"耗时: {elapsed:.1f}ms")
            log(f"响应: {r.text}")
        except Exception as e:
            log(f"❌ FAIL: {e}")
            raise

        # ===== 2. 合法请求 =====
        log(banner("TEST 2: POST /api/quote (合法 8 步问卷)"))
        t0 = time.perf_counter()
        try:
            r = client.post(API_URL, json=HARDCODED_REQUEST)
            elapsed = (time.perf_counter() - t0) * 1000
            log(f"状态码: {r.status_code}")
            log(f"耗时: {elapsed:.0f}ms")
            if r.status_code == 200:
                data = r.json()
                log(f"✅ 200 OK")
                log(f"  source:       {data.get('source')}")
                log(f"  request_id:   {data.get('request_id')}")
                log(f"  total:        ¥{data.get('total'):,.2f}")
                log(f"  breakdown:    {json.dumps(data.get('breakdown'), ensure_ascii=False)}")
                log(f"  items 数量:   {len(data.get('items', []))}")
                log(f"  items 前 3 行:")
                for it in data.get('items', [])[:3]:
                    log(f"    - {it.get('category')} | {it.get('name')} | "
                        f"{it.get('quantity')}×{it.get('unit_price')} = ¥{it.get('total'):,.2f}")
                log(f"  generated_at: {data.get('generated_at')}")
            else:
                log(f"❌ 非 200: {r.text[:500]}")
        except Exception as e:
            log(f"❌ FAIL: {e}")

        # ===== 3. 422 校验(错误手机号) =====
        log(banner("TEST 3: POST /api/quote (错误手机号,期望 422)"))
        try:
            r = client.post(API_URL, json=INVALID_REQUEST)
            log(f"状态码: {r.status_code}")
            log(f"响应: {r.text[:600]}")
            if r.status_code == 422:
                log("✅ 422 校验失败(Pydantic 强校验生效)")
            else:
                log(f"❌ 应为 422,实际 {r.status_code}")
        except Exception as e:
            log(f"❌ FAIL: {e}")

        # ===== 4. 422 校验(area 超界) =====
        log(banner("TEST 4: POST /api/quote (area=10 平米,期望 422)"))
        bad_area = dict(HARDCODED_REQUEST)
        bad_area["area"] = 10
        try:
            r = client.post(API_URL, json=bad_area)
            log(f"状态码: {r.status_code}")
            log(f"响应: {r.text[:600]}")
            if r.status_code == 422:
                log("✅ 422 校验失败(area 30-300 强约束)")
        except Exception as e:
            log(f"❌ FAIL: {e}")

    # ===== 保存 =====
    log_path = LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"\n[LOG SAVED] {log_path}")


if __name__ == "__main__":
    main()
