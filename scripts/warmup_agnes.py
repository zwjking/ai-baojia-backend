"""warmup agnes - check current speed"""
import sys, time, json
sys.path.insert(0, r'C:\Users\Administrator\.qclaw\shared\AI报价网后端')
import httpx
from app.config import AGNES_API_KEY, AGNES_BASE_URL, AGNES_MODEL

# Pre-warm
with httpx.Client(timeout=10.0) as c:
    c.get(f'{AGNES_BASE_URL}/models', headers={'Authorization': f'Bearer {AGNES_API_KEY}'})

# Simple test
print('Simple test...')
t0 = time.perf_counter()
with httpx.Client(timeout=120.0) as c:
    r = c.post(
        f'{AGNES_BASE_URL}/chat/completions',
        headers={'Authorization': f'Bearer {AGNES_API_KEY}', 'Content-Type': 'application/json'},
        json={'model': AGNES_MODEL, 'messages': [{'role':'user', 'content':'说一句话'}], 'max_tokens': 100}
    )
elapsed = time.perf_counter() - t0
body = r.json()
finish = body['choices'][0]['finish_reason']
content = body['choices'][0]['message']['content']
print(f'elapsed={elapsed:.1f}s finish={finish} content={content[:100]}')
print('usage:', body.get('usage'))
