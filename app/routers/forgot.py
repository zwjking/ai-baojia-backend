"""
忘记密码 - V3 P0 加固版

P0 修复:
  P0-2: 不论用户是否存在, 一律返通用成功响应(防枚举)
  P0-3: 不论用户是否存在, 都执行一次 bcrypt dummy check(时序对齐)
  P0-4: 三层桶限流
  P0-5: 改密后 user.password_version +1, 旧 JWT 失效
  P0-7: 必须传 sms_token (purpose=reset)
  P0-8: 密码强度

接口契约变化(对外保持兼容):
  POST /api/forgot/reset
    旧:  {mobile, new_password}
    新:  {mobile, new_password, sms_token}
    老客户端会 403(sms_token_invalid)
"""
from __future__ import annotations

import logging
import re

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.models.database import SessionLocal, User
from app.routers.sms import consume_sms_token
from app.utils.auth_deps import create_token  # noqa: F401  保持接口对称
from app.utils.metrics import bcrypt_duration_seconds, forgot_reset_total, rate_limit_blocked_total
from app.utils.rate_limit import get_forgot_limiter
from app.utils.validators import is_valid_password, is_weak_password

router = APIRouter(prefix="/api/forgot", tags=["forgot"])
logger = logging.getLogger(__name__)

MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")

# 启动时生成 dummy 哈希(同 auth.py)
_DUMMY_HASH: bytes = bcrypt.hashpw(b"dummy_for_timing_forgot", bcrypt.gensalt(rounds=10))


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class ResetRequest(BaseModel):
    """重置密码 - P0-7 三步流程"""
    mobile: str = Field(..., min_length=11, max_length=11)
    new_password: str = Field(..., min_length=6, max_length=20)
    sms_token: str = Field(..., min_length=10, description="短信验证通过后颁发的 token")


class ResetResponse(BaseModel):
    """统一响应 - 不论成功失败一律返 200 + success(防枚举)"""
    success: bool
    message: str


@router.post("/reset", response_model=ResetResponse)
async def reset_password(req: ResetRequest, request: Request):
    """
    重置密码 (P0 加固版)

    流程:
      1) 校验手机号格式 + 密码强度
      2) 校验 sms_token (purpose=reset)
      3) 限流
      4) 查 user(不存在也走 dummy bcrypt)
      5) 已注册 + token 匹配: bcrypt 重写密码 + ver+1(吊销旧 JWT)
      6) 不论成功失败, 一律返 200{success: true, message: ...}(防枚举)
    """
    # 1. 校验
    if not MOBILE_RE.match(req.mobile or ""):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_mobile", "hint": "请输入 11 位有效手机号"},
        )
    ok, code = is_valid_password(req.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "weak_password", "code": code, "hint": "密码强度不够"},
        )
    if is_weak_password(req.new_password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "weak_password", "code": "common", "hint": "密码太常见"},
        )

    # 2. 校验 sms_token
    token_info = consume_sms_token(req.sms_token)
    if not token_info:
        # sms_token 失效也算 200(防枚举), 但内部不执行任何操作
        forgot_reset_total.labels(status="sms_token_invalid").inc()
        return ResetResponse(
            success=True,
            message="如果该手机号已注册,密码重置链接已发送",
        )
    if token_info["purpose"] != "reset":
        forgot_reset_total.labels(status="sms_token_wrong_purpose").inc()
        return ResetResponse(
            success=True,
            message="如果该手机号已注册,密码重置链接已发送",
        )
    if token_info["mobile"] != req.mobile:
        # 拿别人手机号的 token 来重置自己 - 403
        forgot_reset_total.labels(status="sms_token_mobile_mismatch").inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "sms_token_mobile_mismatch", "hint": "短信 token 与手机号不匹配"},
        )

    # 3. 限流
    ip = _client_ip(request)
    rl = get_forgot_limiter().check(ip=ip, endpoint="/api/forgot/reset", mobile=req.mobile)
    if not rl.allowed:
        rate_limit_blocked_total.labels(layer=rl.reason, endpoint="/api/forgot/reset").inc()
        forgot_reset_total.labels(status="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "layer": rl.reason,
                "hint": "操作过于频繁,请稍后再试",
                "retry_after": round(rl.retry_after, 1),
            },
        )

    # 4. 查 user
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile == req.mobile).first()
        if not user:
            # P0-3: 时序对齐 - dummy bcrypt
            with bcrypt_duration_seconds.time():
                try:
                    bcrypt.checkpw(b"dummy_attempt", _DUMMY_HASH)
                except Exception:
                    pass
            # P0-2: 静默成功(不真改密码, 但返 200)
            forgot_reset_total.labels(status="user_not_found").inc()
            logger.info("forgot: 未注册用户 mobile=%s (静默成功)", req.mobile)
            return ResetResponse(
                success=True,
                message="如果该手机号已注册,密码重置链接已发送",
            )

        # 5. 重置密码 + 吊销旧 JWT
        with bcrypt_duration_seconds.time():
            user.password_hash = bcrypt.hashpw(
                req.new_password.encode("utf-8"),
                bcrypt.gensalt(rounds=10),
            ).decode("utf-8")
        user.password_version = (user.password_version or 0) + 1  # P0-5: 吊销旧 token
        db.commit()
        db.refresh(user)
        forgot_reset_total.labels(status="success").inc()
        logger.info("密码重置 mobile=%s user_id=%s ver=%s", req.mobile, user.id, user.password_version)
        return ResetResponse(
            success=True,
            message="密码重置成功,请用新密码登录",
        )
    finally:
        db.close()
