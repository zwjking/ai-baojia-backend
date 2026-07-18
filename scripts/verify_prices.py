"""verify fallback_prices.json completeness"""
import json
path = r'C:\Users\Administrator\.qclaw\shared\AI报价网后端\app\data\fallback_prices.json'
data = json.load(open(path, encoding='utf-8'))
print(f'main (主材):  {len(data["main"])} 项')
for k in data['main']:
    print(f'  - {k}')
print(f'aux  (辅材):  {len(data["aux"])} 项')
for k in data['aux']:
    print(f'  - {k}')
print(f'labor(人工):  {len(data["labor"])} 项')
for k in data['labor']:
    print(f'  - {k}')
print(f'mgmt_rate:    {len([k for k in data["mgmt_rate"] if k != "_src"])} 档')
for k in data['mgmt_rate']:
    if k != '_src':
        print(f'  - {k}: {data["mgmt_rate"][k]}')
print()
print(f'version: {data["version"]}')
print(f'source:  {data["source"][:80]}')

# check requirement: 8 main + 5 aux + 5 labor + 4 tier
ok = (len(data['main']) >= 8 and len(data['aux']) >= 5 and
      len(data['labor']) >= 5 and len([k for k in data['mgmt_rate'] if k != '_src']) == 4)
print(f'\n8 主材 + 5 辅材 + 5 工种 + 4 档管理费: {"✅ 全部满足" if ok else "❌ 不满足"}')
