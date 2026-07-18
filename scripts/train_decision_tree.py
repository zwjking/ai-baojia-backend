# -*- coding: utf-8 -*-
"""
决策树模型 v1 训练脚本
- 输入: data/synthetic_quotes.csv (或 data/quotes.db 真实数据导出)
- 输出: models/quote_dt_v1.pkl
- 验证: 5-fold cross validation + 4 case 命中率

算法: scikit-learn DecisionTreeRegressor
  - max_depth=8 (避免过拟合)
  - min_samples_leaf=5 (防止噪声)
  - 特征: 14 维 ml_features
  - 目标: total
"""
import csv
import json
import os
import pickle
import sys
from pathlib import Path

BACKEND_DIR = Path(r"C:\Users\Administrator\.qclaw\shared\AI报价网后端")
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# 依赖
try:
    from sklearn.tree import DecisionTreeRegressor
    from sklearn.model_selection import cross_val_score, KFold
    from sklearn.metrics import mean_absolute_percentage_error
    import numpy as np
except ImportError as e:
    print(f"❌ 缺依赖: {e}")
    print("   安装: pip install scikit-learn numpy")
    sys.exit(1)


FEATURE_COLS = [
    "area", "grade_num", "pack_num", "district_num",
    "floor", "has_elevator",
    "demolition_wall", "demolition_build", "special_count",
    "brand_tier_tile", "brand_tier_floor", "brand_tier_cabinet", "brand_tier_bathroom",
]
TARGET_COL = "total"


def load_csv(path: Path):
    """读合成数据集 CSV"""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                row = {k: float(v) if k != "special" and k != "style" and k != "layout" else v
                       for k, v in r.items()}
                rows.append(row)
            except (ValueError, KeyError):
                continue
    return rows


def main():
    csv_path = BACKEND_DIR / "data" / "synthetic_quotes.csv"
    if not csv_path.exists():
        print(f"❌ 数据集不存在: {csv_path}")
        print(f"   先跑: python scripts/gen_synthetic_dataset.py 200")
        return 1

    print(f"加载数据集: {csv_path}")
    rows = load_csv(csv_path)
    if not rows:
        print("❌ 数据集为空")
        return 1
    print(f"  行数: {len(rows)}")

    # 拆分 X / y
    X = np.array([[r.get(c, 0) for c in FEATURE_COLS] for r in rows])
    y = np.array([r[TARGET_COL] for r in rows])
    print(f"  X.shape: {X.shape}  y.shape: {y.shape}")
    print(f"  y 范围: ¥{y.min():,.0f} ~ ¥{y.max():,.0f}  中位 ¥{np.median(y):,.0f}")

    # 训练
    model = DecisionTreeRegressor(
        max_depth=8,
        min_samples_leaf=5,
        random_state=42,
    )
    model.fit(X, y)
    print(f"\n训练完成: max_depth=8, min_samples_leaf=5")

    # 5-fold 交叉验证
    print("\n=== 5-fold 交叉验证 ===")
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    mape_scores = -cross_val_score(model, X, y, cv=kf, scoring="neg_mean_absolute_percentage_error")
    r2_scores = cross_val_score(model, X, y, cv=kf, scoring="r2")
    print(f"  MAPE: {mape_scores.mean()*100:.2f}% ± {mape_scores.std()*100:.2f}%")
    print(f"  R²:   {r2_scores.mean():.4f} ± {r2_scores.std():.4f}")

    # 训练集上预测
    y_pred = model.predict(X)
    train_mape = mean_absolute_percentage_error(y, y_pred) * 100
    print(f"\n训练集 MAPE: {train_mape:.2f}%")

    # 特征重要性
    print("\n=== 特征重要性 (Top 14) ===")
    importance = list(zip(FEATURE_COLS, model.feature_importances_))
    importance.sort(key=lambda x: -x[1])
    for name, imp in importance:
        bar = "█" * int(imp * 50)
        print(f"  {name:<22s} {imp:.4f}  {bar}")

    # 保存模型
    model_path = BACKEND_DIR / "models" / "quote_dt_v1.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "features": FEATURE_COLS, "target": TARGET_COL}, f)
    print(f"\n✅ 模型已保存: {model_path}")

    # 输出交叉验证样例
    print("\n=== 4 case 验证 (CV 测试集) ===")
    test_cases = [
        {"id": "60m²简装全包瑶海", "expect": (70000, 90000), "x": [60, 0, 1, 1, -1, -1, 0, 0, 0, 1, 1, 1, 1]},
        {"id": "89m²中档半包蜀山", "expect": (70000, 80000), "x": [89, 1, 0, 0, -1, -1, 0, 0, 0, 1, 1, 1, 1]},
        {"id": "128m²高档全包+地暖滨湖", "expect": (300000, 500000), "x": [128, 2, 1, 4, -1, -1, 0, 0, 1, 1, 1, 1, 1]},
        {"id": "200m²豪华整装+3项蜀山", "expect": (1300000, 1800000), "x": [200, 3, 2, 0, -1, -1, 0, 0, 3, 1, 1, 1, 1]},
    ]
    for case in test_cases:
        pred = model.predict([case["x"]])[0]
        lo, hi = case["expect"]
        in_range = lo <= pred <= hi
        mark = "✅" if in_range else "⚠️"
        print(f"  {mark} {case['id']:<28s}  预测 ¥{pred:,.0f}  期望 [{lo//10000}, {hi//10000}] 万")

    return 0


if __name__ == "__main__":
    sys.exit(main())
