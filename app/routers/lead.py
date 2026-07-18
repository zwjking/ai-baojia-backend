"""
留资接口 - POST /api/lead

W1 阶段: 不入数据库,只打印日志 + 返回 lead_id
W2 P1 阶段: 强制 user_id + 接入 SQLite leads 表 + 限流 1 QPS
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.database import Lead, SessionLocal
from app.models.schemas import LeadRequest, LeadResponse
from app.utils.rate_limit import get_lead_limiter

router = APIRouter(prefix="/api", tags=["lead"])
logger = logging.getLogger(__name__)


class LeadRequestW2(LeadRequest):
    """POST /api/lead W2 版本,强制 user_id"""
    user_id: int = Field(..., description="用户 ID (登录后必填)")


@router.post("/lead", response_model=LeadResponse)
async def create_lead(req: LeadRequestW2):
    """
    留资 - W2 P1 强制登录 + 写入 SQLite + 限流 1 QPS
    """
    # 限流 (非阻塞,超限返回429)
    result = get_lead_limiter().acquire()
    if not result.allowed:
        logger.warning("rate limited: /api/lead")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "hint": "留资过于频繁,请稍后再试", "retry_after": result.retry_after},
        )

    db = SessionLocal()
    try:
        lead = Lead(
            user_id=req.user_id,
            name=req.name,
            phone=req.phone,
            district=req.district.value if req.district else None,
            remark=req.remark or "",
        )
        db.add(lead)
        db.commit()
        db.refresh(lead)

        lead_id = f"L{uuid.uuid4().hex[:10].upper()}"
        logger.info(
            "LEAD id=%s user_id=%s name=%s phone=%s district=%s remark=%s db_id=%s",
            lead_id, req.user_id, req.name, req.phone,
            req.district.value if req.district else None,
            req.remark or "",
            lead.id,
        )
        return LeadResponse(success=True, lead_id=lead_id)
    finally:
        db.close()
