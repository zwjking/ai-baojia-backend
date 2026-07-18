"""
短信验证码 API - P0-7 + 盲点 1

POST /api/sms/send-code
  Body: {mobile, purpose, captcha_id, captcha_code}
  必传 captcha (防短信轰炸)
  返回 {success: true, ttl: 300} (无论用户是否注册都返, 防枚举)

POST /api/sms/verify-code
  Body: {mobile, code, purpose}
  返回 {valid: true, sms_token: ..., expire: 300}
  sms_token 用来后续 /api/register 或 /api/forgot/reset 提交
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.database import SessionLocal, User
from app.routers.captcha import _verify_internal
from app.services.sms_service import (
    CODE_TTL_SECONDS,
    send_code as sms_send,
    verify_code as sms_verify,
)
from app.utils.metrics import rate_limit_blocked_total, sms_send_total
from app.utils.rate_limit import get_sms_limiter
from app.utils.validators import is_valid_mobile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms", tags=["sms"])

# sms_token 内存 store: token -> {mobile, purpose, issued_at}
# 5min 有效, 一次性
_sms_tokens: dict[str, dict] = {}


def _cleanup_tokens() -> int:
    import time
    now = time.time()
    expired = [k for k, v in _sms_tokens.items() if now - v["issued_at"] > CODE_TTL_SECONDS]
    for k in expired:
        _sms_tokens.pop(k, None)
    return len(expired)


def consume_sms_token(token: str) -> dict | None:
    """
    消费 sms_token: 校验并标记 used
    返回: {mobile, purpose} 或 None
    """
    _cleanup_tokens()
    rec = _sms_tokens.get(token)
    if not rec:
        return None
    if rec.get("used"):
        return None
    import time
    if time.time() - rec["issued_at"] > CODE_TTL_SECONDS:
        _sms_tokens.pop(token, None)
        return None
    rec["used"] = True
    return {"mobile": rec["mobile"], "purpose": rec["purpose"]}


# ============== Schema ==============
class SendCodeRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    purpose: str = Field(..., pattern="^(register|reset)$")
    captcha_id: str = Field(..., min_length=8, description="图验 code_id")
    captcha_code: str = Field(..., min_length=4, max_length=4, description="图验值")


class SendCodeResponse(BaseModel):
    success: bool
    ttl: int
    message: str = "验证码已发送(若该手机号有效)"


class VerifyCodeRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    code: str = Field(..., min_length=6, max_length=6)
    purpose: str = Field(..., pattern="^(register|reset)$")


class SmsDevPeekRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    purpose: str = Field(..., pattern="^(register|reset)$")


class VerifyCodeResponse(BaseModel):
    valid: bool
    sms_token: str | None = None
    expire: int = 0


# ============== 路由 ==============
def _client_ip(request: Request) -> str:
    """获取客户端 IP(优先 X-Forwarded-For)"""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/send-code", response_model=SendCodeResponse)
async def send_code(req: SendCodeRequest, request: Request):
    """
    发送短信验证码
      1) 限流 (三层桶)
      2) 校验图验 (P0-1 + 盲点 1 防短信炸)
      3) 校验手机号格式
      4) 触发 sms_service.send_code (mock 模式控制台打印)
      5) 不论用户是否注册, 一律返成功 (防枚举)
    """
    # 1. 限流
    ip = _client_ip(request)
    rl = get_sms_limiter().check(ip=ip, endpoint="/api/sms/send-code", mobile=req.mobile)
    if not rl.allowed:
        rate_limit_blocked_total.labels(layer=rl.reason, endpoint="/api/sms/send-code").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "layer": rl.reason,
                "hint": "操作过于频繁,请稍后再试",
                "retry_after": round(rl.retry_after, 1),
            },
        )

    # 2. 校验图验(必须先过图验才能发短信)
    if not _verify_internal(req.captcha_id, req.captcha_code):
        sms_send_total.labels(purpose=req.purpose, status="captcha_failed").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_captcha", "hint": "图验错误,请刷新后重试"},
        )

    # 3. 校验手机号
    if not is_valid_mobile(req.mobile):
        sms_send_total.labels(purpose=req.purpose, status="invalid_mobile").inc()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_mobile", "hint": "请输入 11 位有效手机号"},
        )

    # 4. 触发发送(mobile 校验通过后, 不论用户是否注册都发 - 但 mock 模式一定会生成)
    sms_send(req.mobile, req.purpose)
    sms_send_total.labels(purpose=req.purpose, status="success").inc()
    logger.info("SMS sent mobile=%s purpose=%s", req.mobile, req.purpose)

    return SendCodeResponse(success=True, ttl=CODE_TTL_SECONDS)


@router.post("/verify-code", response_model=VerifyCodeResponse)
async def verify_code(req: VerifyCodeRequest):
    """
    校验短信码, 颁发 sms_token
      校验通过: 返回 sms_token (5min 有效, 一次性)
      失败: valid=False, sms_token=None
    """
    # 校验手机号
    if not is_valid_mobile(req.mobile):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_mobile", "hint": "请输入 11 位有效手机号"},
        )

    valid = sms_verify(req.mobile, req.code, req.purpose)
    if not valid:
        sms_send_total.labels(purpose=req.purpose, status="verify_failed").inc()
        return VerifyCodeResponse(valid=False, sms_token=None, expire=0)

    # 颁发 sms_token
    token = secrets.token_urlsafe(32)
    import time
    _sms_tokens[token] = {
        "mobile": req.mobile,
        "purpose": req.purpose,
        "issued_at": time.time(),
        "used": False,
    }
    sms_send_total.labels(purpose=req.purpose, status="verify_ok").inc()
    logger.info("sms_token issued mobile=%s purpose=%s", req.mobile, req.purpose)
    return VerifyCodeResponse(valid=True, sms_token=token, expire=CODE_TTL_SECONDS)


# ============== Dev-only: 暴露最近一次短信码 ==============
import os as _os_sms
if _os_sms.getenv("SMS_DEV_PEEK", "false").lower() == "true":
    @router.post("/dev-peek", include_in_schema=False)
    async def sms_dev_peek(req: SmsDevPeekRequest):
        """
        仅 .env 设 SMS_DEV_PEEK=true 时可用
        测试/验收脚本专用 - 返最近一次 send-code 的 code
        不 mark used, 允许后续 verify-code 走正常路径
        """
        from app.services.sms_service import _store as _sms_store, _cleanup_expired
        _cleanup_expired()
        rec = _sms_store.get((req.mobile, req.purpose))
        if not rec:
            return {"code": None, "error": "no_record"}
        if rec.used:
            return {"code": None, "error": "already_used"}
        # 不 mark used, 允许 /api/sms/verify-code 验证
        return {"code": rec.code}
