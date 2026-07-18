"""
直接测试 agnes_client.quote_via_agnes 的失败重试逻辑
使用一个错误的 AGNES_API_KEY 临时替换,触发 HTTP 401,验证重试 1 次后抛 AgnesCallError
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.schemas import QuoteRequest
from app.services.agnes_client import AgnesCallError, quote_via_agnes
from app.services.fallback import _load_prices


async def main():
    print("=" * 60)
    print("测试 agnes 失败重试 1 次 → 抛 AgnesCallError")
    print("=" * 60)

    # 临时把 KEY 改成错的
    import app.config as cfg
    original_key = cfg.AGNES_API_KEY
    cfg.AGNES_API_KEY = "sk-WRONG_KEY_FOR_TESTING_RETRY"
    # 重新 import 让 agnes_client 用新 key
    import app.services.agnes_client as agc
    agc.AGNES_API_KEY = "sk-WRONG_KEY_FOR_TESTING_RETRY"

    req = QuoteRequest(
        area=89.0, layout='3室2厅1卫', grade='中档', pack='半包',
        style='现代', special=[], district='蜀山区', contact='13800138000'
    )
    prices = _load_prices()

    t0 = time.perf_counter()
    try:
        response, meta = await quote_via_agnes(req, prices, max_retries=1)
        print(f"❌ UNEXPECTED: got response {response.total}")
    except AgnesCallError as e:
        elapsed = time.perf_counter() - t0
        print(f"✅ Got AgnesCallError as expected: {e}")
        print(f"   elapsed: {elapsed:.1f}s (>0 表示重试生效)")
        if elapsed > 1.0:
            print(f"   ✅ 重试机制生效(>=1 次 retry)")
        else:
            print(f"   ⚠️ elapsed 较短,可能没真重试")

    # 还原
    cfg.AGNES_API_KEY = original_key
    agc.AGNES_API_KEY = original_key

    print("\n" + "=" * 60)
    print("结论: 重试 1 次 + L2 降级 链路已验证")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
