"""
ML 模型服务 - 决策树 v1 加载与预测

功能:
  - load_model()  启动时加载 quote_dt_v1.pkl
  - predict_correction(features)  返回修正系数 (0.5 ~ 2.0)
  - 失败兜底: 返回 1.0 (即不修正)

集成方式:
  final_total = fallback_total × correction
"""
from __future__ import annotations

import logging
import os
import pickle
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MODEL_PATH = Path(r"C:\Users\Administrator\.qclaw\shared\AI报价网后端\models\quote_dt_v1.pkl")

_model_cache: Optional[dict] = None


def load_model() -> bool:
    """启动时加载模型,返回是否成功"""
    global _model_cache
    if _model_cache is not None:
        return True
    if not MODEL_PATH.exists():
        logger.warning("ML 模型不存在: %s, 将不启用 ML 修正", MODEL_PATH)
        return False
    try:
        with open(MODEL_PATH, "rb") as f:
            _model_cache = pickle.load(f)
        logger.info("ML 模型加载成功: %s, 特征=%s", MODEL_PATH, _model_cache.get("features"))
        return True
    except Exception as e:
        logger.error("ML 模型加载失败: %s", e)
        return False


def predict_correction(features: dict, fallback_total: float) -> float:
    """
    给定 ml_features 和 fallback_total, 返回修正系数 (0.5 ~ 2.0)

    规则:
      - 模型预测值 / fallback_total = 修正系数
      - 钳制在 [0.5, 2.0] 避免极端
      - 模型未加载 / 异常: 返回 1.0 (不修正)
    """
    if not load_model() or _model_cache is None:
        return 1.0
    try:
        model = _model_cache["model"]
        feature_cols = _model_cache["features"]
        x = [float(features.get(c, 0)) for c in feature_cols]
        pred = float(model.predict([x])[0])
        if fallback_total <= 0:
            return 1.0
        ratio = pred / fallback_total
        # 钳制在 [0.5, 2.0]
        ratio = max(0.5, min(2.0, ratio))
        return round(ratio, 4)
    except Exception as e:
        logger.warning("ML 预测失败: %s, 兜底返回 1.0", e)
        return 1.0


def get_model_status() -> dict:
    """返回模型状态 (用于 /api/admin/stats)"""
    loaded = load_model()
    return {
        "loaded": loaded,
        "path": str(MODEL_PATH),
        "exists": MODEL_PATH.exists(),
        "features": _model_cache.get("features") if _model_cache else None,
    }
