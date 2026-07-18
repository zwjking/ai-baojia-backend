"""直接调 agnes 看原始输出"""
import asyncio
import json
import sys
sys.path.insert(0, r"C:\Users\Administrator\.qclaw\shared\AI报价网后端")
from app.config import AGNES_API_KEY, AGNES_BASE_URL
from app.services.agnes_client import build_quote_prompt
from app.models.schemas import QuoteRequest, GradeEnum, PackEnum, DistrictEnum
from app.services.fallback import _load_prices

async def main():
    req = QuoteRequest(
        area=60.0, layout="2室1厅1卫", grade=GradeEnum.SIMPLE, pack=PackEnum.FULL,
        style="简约", special=[], district=DistrictEnum.YAOHai, contact="13800138000"
    )
    prices = _load_prices()
    messages = build_quote_prompt(req, prices)
    print(f"=== System prompt length: {len(messages[0]['content'])} chars ===")
    print(f"=== User prompt: {messages[1]['content']} ===", flush=True)
    import sys; sys.stdout.reconfigure(encoding='utf-8')

    import httpx
    headers = {"Authorization": f"Bearer {AGNES_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "agnes-2.0-flash",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 12000,  # 让 agnes 有足够 output budget
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=150) as client:
        r = await client.post(f"{AGNES_BASE_URL}/chat/completions", headers=headers, json=payload)
        body = r.json()
        content = body["choices"][0]["message"]["content"]
        print(f"=== AGNES RAW ({len(content)} chars) ===", flush=True)
        try:
            print(content, flush=True)
        except UnicodeEncodeError:
            print(content.encode("utf-8", "replace").decode("utf-8"), flush=True)
        print(f"\n=== USAGE ===\n{body.get('usage')}", flush=True)

asyncio.run(main())
