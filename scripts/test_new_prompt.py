"""test full new prompt"""
import sys, time, json
sys.path.insert(0, r'C:\Users\Administrator\.qclaw\shared\AI报价网后端')
import httpx
from app.config import AGNES_API_KEY, AGNES_BASE_URL, AGNES_MODEL
from app.models.schemas import QuoteRequest
from app.services.fallback import _load_prices
from app.services.agnes_client import build_quote_prompt

# Pre-warm
with httpx.Client(timeout=10.0) as c:
    c.get(f'{AGNES_BASE_URL}/models', headers={'Authorization': f'Bearer {AGNES_API_KEY}'})

req = QuoteRequest(
    area=89.0, layout='3室2厅1卫', grade='中档', pack='半包',
    style='现代', special=[], district='蜀山区', contact='13800138000'
)
prices = _load_prices()
messages = build_quote_prompt(req, prices)
print('system prompt长度:', len(messages[0]['content']))
print('user prompt长度:', len(messages[1]['content']))

# Call
print('Call agnes (180s)...')
t0 = time.perf_counter()
with httpx.Client(timeout=180.0) as c:
    r = c.post(
        f'{AGNES_BASE_URL}/chat/completions',
        headers={'Authorization': f'Bearer {AGNES_API_KEY}', 'Content-Type': 'application/json'},
        json={
            'model': AGNES_MODEL,
            'messages': messages,
            'temperature': 0.2,
            'max_tokens': 8000,
            'response_format': {'type': 'json_object'},
        }
    )
elapsed = time.perf_counter() - t0
print(f'status={r.status_code} elapsed={elapsed:.1f}s')
body = r.json()
print('id:', body.get('id'))
print('usage:', body.get('usage'))
print('finish:', body['choices'][0]['finish_reason'])
content = body['choices'][0]['message']['content']
print('content前200:', content[:200])
print('content后200:', content[-200:])
print('---parse---')
try:
    data = json.loads(content)
    print('keys:', list(data.keys()))
    if 'breakdown' in data:
        print('breakdown keys:', list(data['breakdown'].keys()))
        print('breakdown:', data['breakdown'])
    if 'items' in data:
        print(f'items数量: {len(data["items"])}')
        for it in data['items'][:3]:
            print(f'  - {it}')
    if 'total' in data:
        print('total:', data['total'])
except Exception as e:
    print(f'parse ERR: {e}')
