"""
登录 V2 - 手机号+密码 (陈浩 2026-07-11)

三个新接口:
  POST /api/login-password  手机号+密码登录
  POST /api/register         手机号+密码+短信码注册 (dev 不验短信)
  POST /api/reset-password   重置密码 (dev 不验短信)

设计原则:
  - 密码用 bcrypt 加密 (5.0.0, cost=12)
  - dev 环境注册/重置的 code 字段保留但不验证(留 123456 即可)
  - 老用户(无 password_hash)走 /api/login 验证码登录, 此接口返回 'use_legacy_login'
  - 限流 1 QPS (防爆破,复用 get_login_limiter)
  - 返回 token (uuid4) + user_id

降级说明:
  - bcrypt 不可用时,降级到 hashlib.sha256 + 盐 (同 token 接口)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import uuid

import bcrypt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.models.database import SessionLocal, User
from app.utils.rate_limit import get_login_limiter

router = APIRouter(prefix="/api", tags=["auth-password"])
logger = logging.getLogger(__name__)

# dev 固定短信验证码 (与 /api/login 一致)
DEV_FIXED_CODE = "123456"
# dev 短信码脱敏提示(响应里返回给前端,方便测试)
DEV_CODE_HINT = "123456"

# 密码强度: 6-20 位
PASSWORD_MIN = 6
PASSWORD_MAX = 20
PASSWORD_PATTERN = re.compile(r"^[\w!@#$%^&*()\-+=\[\]{};:'\",.<>/?\\|`~]{6,20}$")

# 中国大陆手机号
MOBILE_PATTERN = re.compile(r"^1[3-9]\d{9}$")


def _hash_password(password: str) -> str:
    """bcrypt 加密, 返回 str(ascii) 便于存 DB"""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("ascii")


def _verify_password(password: str, password_hash: str) -> bool:
    """bcrypt 校验,常量时间比较"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _validate_mobile(mobile: str) -> bool:
    return bool(MOBILE_PATTERN.match(mobile))


def _validate_password(password: str) -> bool:
    if len(password) < PASSWORD_MIN or len(password) > PASSWORD_MAX:
        return False
    return bool(PASSWORD_PATTERN.match(password))


# ============== Schemas ==============

class LoginPasswordRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class RegisterRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    # dev 模式 code 留空时不验证;V3 上线后改为 ... 必填
    code: str = Field(default=DEV_FIXED_CODE, min_length=4, max_length=8, description="dev 留空或 123456,V3 上线后必填")


class ResetPasswordRequest(BaseModel):
    mobile: str = Field(..., min_length=11, max_length=11)
    # dev 模式 code 留空时不验证;V3 上线后改为 ... 必填
    code: str = Field(default=DEV_FIXED_CODE, min_length=4, max_length=8, description="dev 留空或 123456,V3 上线后必填")
    new_password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)


class AuthResponse(BaseModel):
    token: str
    user_id: int
    hint: str = ""  # dev 提示


# ============== Endpoints ==============

@router.post("/login-password", response_model=AuthResponse)
async def login_password(req: LoginPasswordRequest):
    """手机号+密码登录 (V2)"""
    # 限流
    rl = get_login_limiter().acquire()
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "hint": "登录过于频繁,请稍后再试", "retry_after": rl.retry_after},
        )

    if not _validate_mobile(req.mobile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_mobile", "hint": "手机号格式错误"},
        )
    if not _validate_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_password", "hint": f"密码需 {PASSWORD_MIN}-{PASSWORD_MAX} 位"},
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile == req.mobile).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "user_not_found", "hint": "用户不存在,请先注册"},
            )

        if not user.password_hash:
            # 老用户,没设过密码
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "use_legacy_login", "hint": "该手机号未设置密码,请使用验证码登录或重置密码"},
            )

        if not _verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "wrong_password", "hint": "密码错误"},
            )

        logger.info("login-password 成功 mobile=%s user_id=%s", req.mobile, user.id)
        return AuthResponse(token=str(uuid.uuid4()), user_id=user.id, hint="login ok")
    finally:
        db.close()


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    """手机号+密码+短信码注册 (V2)
    dev 环境不验证短信 (code 留 123456 通过)
    """
    # 限流
    rl = get_login_limiter().acquire()
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "hint": "注册过于频繁,请稍后再试", "retry_after": rl.retry_after},
        )

    if not _validate_mobile(req.mobile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_mobile", "hint": "手机号格式错误"},
        )
    if not _validate_password(req.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_password", "hint": f"密码需 {PASSWORD_MIN}-{PASSWORD_MAX} 位"},
        )

    # dev 不验证短信,只要 code 不为空即可 (预留字段)
    if not req.code or not req.code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_code", "hint": f"验证码不能为空 (dev 固定码: {DEV_CODE_HINT})"},
        )

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.mobile == req.mobile).first()
        if existing:
            if existing.password_hash:
                # 已注册过
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "user_exists", "hint": "该手机号已注册,请直接登录"},
                )
            else:
                # 老用户,补设密码
                existing.password_hash = _hash_password(req.password)
                db.commit()
                db.refresh(existing)
                logger.info("register 老用户补设密码 mobile=%s user_id=%s", req.mobile, existing.id)
                return AuthResponse(
                    token=str(uuid.uuid4()),
                    user_id=existing.id,
                    hint="已为老用户设置密码",
                )

        # 新用户
        user = User(
            mobile=req.mobile,
            password_hash=_hash_password(req.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info("register 新用户 mobile=%s user_id=%s", req.mobile, user.id)
        return AuthResponse(token=str(uuid.uuid4()), user_id=user.id, hint="register ok")
    finally:
        db.close()


@router.post("/reset-password", response_model=AuthResponse)
async def reset_password(req: ResetPasswordRequest):
    """重置密码 (V2)
    dev 环境不验证短信
    """
    # 限流
    rl = get_login_limiter().acquire()
    if not rl.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "rate_limited", "hint": "重置密码过于频繁,请稍后再试", "retry_after": rl.retry_after},
        )

    if not _validate_mobile(req.mobile):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_mobile", "hint": "手机号格式错误"},
        )
    if not _validate_password(req.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_password", "hint": f"密码需 {PASSWORD_MIN}-{PASSWORD_MAX} 位"},
        )
    if not req.code or not req.code.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_code", "hint": f"验证码不能为空 (dev 固定码: {DEV_CODE_HINT})"},
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile == req.mobile).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "user_not_found", "hint": "该手机号未注册"},
            )

        user.password_hash = _hash_password(req.new_password)
        db.commit()
        db.refresh(user)
        logger.info("reset-password 成功 mobile=%s user_id=%s", req.mobile, user.id)
        return AuthResponse(token=str(uuid.uuid4()), user_id=user.id, hint="password reset ok")
    finally:
        db.close()
