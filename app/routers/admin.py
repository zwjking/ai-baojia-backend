"""
管理接口 (W2 调整版 P0+P1)

- POST /api/admin/reload-prices  热重载价格基线 (P0)
- GET  /api/admin/stats          今日报价/留资/用户计数 (P1)

鉴权: Bearer Token,从 .env 读 ADMIN_TOKEN
  - 无 token / 错 token -> 401
  - 读 .env 缺失 ADMIN_TOKEN -> 启动期 fail-fast (config.py 强校验)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from app.config import ADMIN_TOKEN, mask_api_key
from app.models.database import Lead, Quote, SessionLocal, User
from app.services.fallback import get_cache_meta, reload_prices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============== 鉴权依赖 ==============
def require_admin(authorization: Optional[str] = Header(default=None)) -> str:
    """
    简单 Bearer Token 鉴权

    Header:  Authorization: Bearer <ADMIN_TOKEN>
    失败:    401
    """
    if not authorization:
        logger.warning("admin 接口无 Authorization 头")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_authorization", "hint": "需要 Header: Authorization: Bearer <ADMIN_TOKEN>"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("admin 接口 Authorization 格式错误: %r", authorization[:30])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_authorization", "hint": "格式: Bearer <token>"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if token != ADMIN_TOKEN:
        logger.warning("admin 接口 token 不匹配 (got=%s...)", token[:6])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


# ============== Pydantic 响应 ==============
class ReloadPricesResponse(BaseModel):
    success: bool
    version: Optional[str] = None
    loaded_at: str
    path: str
    message: str = "价格基线已热重载"


# ============== P0: 热重载接口 ==============
@router.post("/reload-prices", response_model=ReloadPricesResponse)
async def post_reload_prices(_token: str = Depends(require_admin)):
    """
    热重载价格基线 - POST (非 GET,避免被爬虫/搜索引擎误触)

    用途:
      1. 修改 app/data/fallback_prices.json 中的某个价格
      2. 调本接口
      3. 立即调用 /api/quote 即可看到新价格生效
    """
    try:
        new_data = reload_prices()
    except FileNotFoundError as e:
        logger.error("热重载失败 - 文件不存在: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "prices_file_not_found", "message": str(e)},
        )
    except Exception as e:
        logger.exception("热重载失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "reload_failed", "message": str(e)},
        )

    meta = get_cache_meta()
    logger.info(
        "POST /api/admin/reload-prices OK version=%s loaded_at=%s",
        meta["version"], meta["loaded_at"],
    )
    return ReloadPricesResponse(
        success=True,
        version=meta["version"],
        loaded_at=meta["loaded_at"],
        path=meta["path"],
    )


# ============== P1: Stats 接口 ==============
class StatsResponse(BaseModel):
    today_quotes: int
    today_leads: int
    total_users: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats(_token: str = Depends(require_admin)):
    """
    统计数据 - 今日报价数 / 今日留资数 / 总用户数
    """
    db = SessionLocal()
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        today_quotes = db.query(Quote).filter(Quote.generated_at >= today).count()
        today_leads = db.query(Lead).filter(Lead.created_at >= today).count()
        total_users = db.query(User).count()

        logger.info("GET /api/admin/stats today_quotes=%d today_leads=%d total_users=%d",
                    today_quotes, today_leads, total_users)
        return StatsResponse(
            today_quotes=today_quotes,
            today_leads=today_leads,
            total_users=total_users,
        )
    finally:
        db.close()
