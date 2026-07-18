"""V5+ ML 修正 单独测试"""
import json
import sys
import time
import urllib.request

def hit(payload, force=True):
    body = json.dumps({**payload, 'user_id': 999}, ensure_ascii=False).encode('utf-8')
    url = 'http://127.0.0.1:8000/api/quote?force_fallback=true' if force else 'http://127.0.0.1:8000/api/quote'
    req = urllib.request.Request(
        url, data=body, method='POST',
        headers={'Content-Type': 'application/json; charset=utf-8'},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode('utf-8'))


def main():
    case = {
        'area': 89.0, 'layout': '3室2厅1卫', 'grade': '中档',
        'pack': '半包', 'style': '现代', 'special': [],
        'district': '蜀山区', 'contact': '13800138099',
    }
    r = hit(case)
    print('=== V5+ ML 修正测试 (89m²中档半包蜀山) ===')
    print(f"  total:         ¥{r['total']:,.2f}")
    print(f"  ml_correction: {r.get('ml_correction')}")
    if r.get('total_ml') is not None:
        print(f"  total_ml:      ¥{r['total_ml']:,.2f}")
    else:
        print(f"  total_ml:      (null)")
    print()
    print('完整 ml_features:')
    print(json.dumps(r.get('ml_features', {}), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
