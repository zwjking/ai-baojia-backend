"""
报价接口 - POST /api/quote

V6 调整 (2026-07-12, 君哥拍板):
  - 默认走 fallback V4 (顾工公式) + ML 决策树修正
  - 不再默认调用 agnes (太慢 + 8 case 不稳定)
  - agnes 调用代码保留 (注释掉), 等净化器上线后再启用
  - 5 QPS 限流保留

流程 (V6):
  1. Pydantic 强校验
  2. 限流 5 QPS
  3. fallback V4 算账 (顾工公式)
  4. ML 决策树修正 (R²=0.952)
  5. 返回报价 JSON
  6. 写入 SQLite quotes 表
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import Field

from app.models.database import Quote, SessionLocal
from app.models.schemas import QuoteRequest, QuoteResponse
# V6: agnes 暂不调用,保留 import 以便后续启用
# from app.services.agnes_client import AgnesCallError, quote_via_agnes
from app.services.fallback import _load_prices, compute_fallback
from app.utils.rate_limit import get_quote_limiter
from app.utils.metrics import quote_total

router = APIRouter(prefix="/api", tags=["quote"])
logger = logging.getLogger(__name__)


# W2 调整: user_id 关联(可选, 未登录也能报)
class QuoteRequestW2(QuoteRequest):
    """POST /api/quote W2 版本,增加 user_id(可选)"""
    user_id: Optional[int] = Field(
        default=None,
        description="W2 关联用户 ID (登录后必填,W2 P1)",
    )


@router.post("/quote", response_model=QuoteResponse)
async def create_quote(
    req: QuoteRequestW2,
    force_fallback: bool = Query(
        default=True,  # V6 调整: 默认 True (跳过 agnes, 走 fallback + ML)
        description="V6: 默认 true 走 fallback+ML; agnes 暂不启用 (净化器未上线)",
    ),
    use_ml: bool = Query(
        default=True,  # V6 新增: ML 决策树修正开关
        description="V6: 用 ML 决策树修正 fallback 算账结果",
    ),
):
    """
    V6 报价接口 - fallback V4 优先 + ML 决策树兜底
    agnes 已停用,等净化器上线后再启用
    """
    t0 = time.perf_counter()
    logger.info(
        "POST /api/quote area=%.1f grade=%s pack=%s district=%s user_id=%s force_fallback=%s use_ml=%s",
        req.area, req.grade.value, req.pack.value, req.district.value,
        req.user_id, force_fallback, use_ml,
    )

    # 限流
    result = get_quote_limiter().acquire()
    if not result.allowed:
        logger.warning("rate limited: /api/quote")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "hint": "请求过于频繁,请稍后再试", "retry_after": result.retry_after},
        )

    prices = _load_prices()
    source = "fallback"
    request_id = None
    agnes_error = None  # V6: 保留以便日后开启 agnes 时打印
    db = SessionLocal()
    try:
        # ===== L1: agnes 已停用 (V6 决策, 净化器上线前不再调用) =====
        # 调用代码保留作参考, 需要时可恢复
        if not force_fallback and False:  # V6: 强制条件 False, 永不进 agnes
            pass  # 注释掉的内容全部跳过
        # else:
        #     agnes_error = AgnesCallError("V6: agnes 暂不启用 (force_fallback=true)")
        #     logger.info("V6: 跳过 agnes, 直接走 L2 fallback + ML")

        # ===== L2: fallback (V4 顾工公式) =====
        try:
            response, raw = compute_fallback(req)
            response.source = "fallback"

            # V5+: ML 决策树修正 (R²=0.952, MAPE 17%)
            # V6 临时禁: ML 修正后 total 与 4 类费用之和偏差大,触发 Pydantic 校验失败
            # 需要重新设计: ML 修正后按比例分配 4 类, 或者去掉 Pydantic sum 校验
            if use_ml and response.ml_features and False:  # V6: 临时禁用 ML
                try:
                    from app.services.ml_model import predict_correction
                    correction = predict_correction(response.ml_features, response.total)
                    response.ml_correction = correction
                    response.total_ml = round(response.total * correction, 2)
                    # V6: ML 修正后的总价 = 主用值 (fallback 单独不准)
                    # ⚠️ 但这会触发 Pydantic "4 类费用之和 偏差 > 5 元" 错误
                    response.total = response.total_ml
                    response.source = "fallback+ml"
                    logger.info(
                        "ML correction: %.4f -> total_ml=%.2f (fallback=%.2f)",
                        correction, response.total_ml, response.total,
                    )
                except Exception as e:
                    logger.warning("ML correction failed: %s", e)
                    response.ml_correction = 1.0
                    response.total_ml = None
            else:
                # V6 临时: 只算 ML 修正系数, 不改 total (避免 Pydantic 校验失败)
                if use_ml and response.ml_features:
                    try:
                        from app.services.ml_model import predict_correction
                        correction = predict_correction(response.ml_features, response.total)
                        response.ml_correction = correction
                        response.total_ml = round(response.total * correction, 2)
                        logger.info(
                            "ML correction (preview only): %.4f -> total_ml=%.2f (fallback=%.2f)",
                            correction, response.total_ml, response.total,
                        )
                    except Exception as e:
                        logger.warning("ML correction preview failed: %s", e)
                        response.ml_correction = 1.0
                        response.total_ml = None

            # V5: 写 quotes 表 (为 ML 训练准备数据)
            # V7 改动: user_id=None 也写库, 拿 quote.id 当 request_id 用于导出
            if True:
                quote_record = Quote(
                    user_id=req.user_id,
                    survey_json=json.dumps(
                        {
                            "area": req.area, "layout": req.layout,
                            "grade": req.grade.value, "pack": req.pack.value,
                            "style": req.style, "special": req.special,
                            "district": req.district.value,
                            # V4 扩展字段(全部可选)
                            "rooms": req.rooms, "floor": req.floor,
                            "has_elevator": req.has_elevator,
                            "demolition_wall_area": req.demolition_wall_area,
                            "demolition_build_area": req.demolition_build_area,
                            "brand_tier_tile": req.brand_tier_tile.value if req.brand_tier_tile else None,
                            "brand_tier_floor": req.brand_tier_floor.value if req.brand_tier_floor else None,
                            "brand_tier_cabinet": req.brand_tier_cabinet.value if req.brand_tier_cabinet else None,
                            "brand_tier_bathroom": req.brand_tier_bathroom.value if req.brand_tier_bathroom else None,
                        },
                        ensure_ascii=False,
                    ),
                    quote_json=json.dumps(
                        {
                            "total": response.total,
                            "source": response.source,
                            "items_count": len(response.items),
                            "ml_correction": response.ml_correction,
                            "breakdown": response.breakdown.model_dump() if hasattr(response.breakdown, 'model_dump') else dict(response.breakdown),
                        },
                        ensure_ascii=False,
                    ),
                    source=response.source,
                    request_id=None,
                    ml_features_json=json.dumps(response.ml_features, ensure_ascii=False) if response.ml_features else None,
                    total_amount=response.total,
                )
                db.add(quote_record)
                db.commit()
                db.refresh(quote_record)
                # V7 改动: 把 DB 主键写到响应,供前端导出 PDF/Excel 用
                response.request_id = str(quote_record.id)
                logger.info(
                    "V6 quote saved id=%s user_id=%s source=%s total=%.2f request_id=%s",
                    quote_record.id, req.user_id, response.source, response.total, response.request_id,
                )
            quote_total.labels(path=response.source).inc()
            if agnes_error:
                logger.warning("V6 fallback used because: %s", agnes_error)
            return response
        except Exception as e:
            logger.exception("V6 fallback failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"报价失败(fallback V4 失败): {e}",
            )
    finally:
        db.close()
