# -*- coding: utf-8 -*-
"""
合成数据集生成器 - 为决策树模型准备训练数据
- 思路: 规则 fallback 算的 total 作为"伪标签" + ml_features 作为 X
- 当真实客户报价数据不足时, 用此方法快速训练 v1 模型
- 后续真实数据回流后, 直接 retrain 即可替换

输入: 合成 N 条 (ml_features, total) 对
输出: data/synthetic_quotes.csv
"""
import csv
import json
import os
import random
import sys
import time
from pathlib import Path

# 路径
BACKEND_DIR = Path(r"C:\Users\Administrator\.qclaw\shared\AI报价网后端")
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# 让脚本能直接 import app
import urllib.request
import urllib.parse

BASE = "http://127.0.0.1:8000"

# 4 档
GRADES = ["简装", "中档", "高档", "豪华"]
PACKS = ["半包", "全包", "整装"]
DISTRICTS = ["蜀山区", "瑶海区", "包河区", "庐阳区", "滨湖新区"]
STYLES = ["现代", "简约", "北欧", "中式", "新中式", "轻奢"]
SPECIAL_OPTS = [
    [], ["地暖"], ["中央空调"], ["新风"],
    ["地暖", "中央空调"], ["地暖", "中央空调", "新风"],
    ["智能家居"], ["地暖", "智能家居"],
    ["净水系统"], ["地暖", "新风", "智能家居"],
]


def random_request(rng: random.Random) -> dict:
    """生成 1 条合成请求"""
    area = rng.uniform(50, 220)
    bed = rng.choice([1, 2, 3, 3, 4, 4, 5])
    living = rng.choice([1, 1, 2, 2, 3])
    bath = rng.choice([1, 1, 2, 2, 3])
    layout = f"{bed}室{living}厅{bath}卫"

    grade = rng.choice(GRADES)
    pack = rng.choice(PACKS)
    district = rng.choice(DISTRICTS)
    style = rng.choice(STYLES)
    special = rng.choice(SPECIAL_OPTS)
    contact = "13800" + str(rng.randint(100000, 999999)).zfill(6)

    # 半包户型
    if pack == "半包":
        style = rng.choice(["现代", "简约", "北欧"])
    # 豪华通常配特殊
    if grade == "豪华" and not special:
        special = rng.choice([["地暖", "中央空调"], ["地暖", "中央空调", "新风"], ["中央空调", "新风"]])

    return {
        "area": round(area, 1),
        "layout": layout,
        "grade": grade,
        "pack": pack,
        "style": style,
        "special": special,
        "district": district,
        "contact": contact,
    }


def post_quote(payload):
    """调 fallback 接口拿 total + ml_features"""
    # 加 user_id 触发写库(后端只对 user_id != None 的请求落库)
    payload = {**payload, "user_id": 999}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/quote?force_fallback=true",
        data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    # 限流 5 QPS → 间隔 0.3s 避免被限
    time.sleep(0.25)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("total"), data.get("ml_features"), data.get("items", [])
    except Exception as e:
        return None, None, []


def main(n: int = 200, seed: int = 42, out: str = "data/synthetic_quotes.csv"):
    rng = random.Random(seed)
    out_path = BACKEND_DIR / out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 健康检查
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
            print(f"[/health] {r.status} → service ok")
    except Exception as e:
        print(f"❌ 服务未启动: {e}")
        return 1

    rows = []
    fail = 0
    for i in range(n):
        req = random_request(rng)
        total, ml, items = post_quote(req)
        if total is None or ml is None:
            fail += 1
            continue
        row = {
            **ml,
            "total": total,
            "n_items": len(items),
            "special": "|".join(req["special"]),
            "style": req["style"],
            "layout": req["layout"],
        }
        rows.append(row)
        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{n}  成功={len(rows)}  失败={fail}")

    if not rows:
        print("❌ 无有效数据, 请检查服务")
        return 1

    # 写 CSV
    feature_keys = list(rows[0].keys())
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=feature_keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"\n✅ 合成数据集已生成: {out_path}")
    print(f"   行数: {len(rows)}")
    print(f"   列数: {len(feature_keys)} (含 total 标签)")
    print(f"   特征: {feature_keys[:-3]} ...")

    # 简单统计
    totals = [r["total"] for r in rows]
    print(f"   total 范围: ¥{min(totals):,.0f} ~ ¥{max(totals):,.0f}")
    print(f"   total 中位: ¥{sorted(totals)[len(totals)//2]:,.0f}")
    return 0


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    sys.exit(main(n))
