"""
认证接口 - V3 P0 加固版

P0 修复汇总:
  P0-1: 服务端图验(/api/captcha, redis 风格内存存储)
  P0-2: 改 forgot (P0-2 在 forgot.py 这里只暴露通用错误码)
  P0-3: 时序对齐 - 不论用户是否存在都 bcrypt dummy check
  P0-4: 三层桶限流 (utils/rate_limit.py:get_register_limiter 等)
  P0-5: JWT + 24h 过期 + password_version 改密失效 (utils/auth_deps.py)
  P0-7: 注册走三步流程(send-code → verify-code → register with sms_token)
  P0-8: 密码强度 (utils/validators.py:is_valid_password)
  盲点 1: send-code 强制图验(在 sms.py)
  盲点 2: 注册写入 user_consent_log(必须传 policy_agreed=true)

接口契约保持兼容:
  POST /api/register  →  AuthResponse{token, user_id, mobile, has_password}
  POST /api/login     →  AuthResponse{...}
  但 register 现在多收: captcha_id, captcha_code, sms_token, policy_agreed
  老客户端不传这几个字段会 400(强制三步流程)
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

import bcrypt
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError

from app.models.database import SessionLocal, User, UserConsentLog
from app.routers.captcha import _verify_internal as verify_captcha_internal
from app.routers.sms import consume_sms_token
from app.utils.auth_deps import create_token
from app.utils.metrics import bcrypt_duration_seconds, login_total, rate_limit_blocked_total, register_total
from app.utils.rate_limit import get_login_v2_limiter, get_register_limiter

router = APIRouter(prefix="/api", tags=["auth"])
logger = logging.getLogger(__name__)

# ============== 通用校验 ==============
MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")

# 启动时生成一个 dummy 哈希, 用于时序对齐 (P0-3)
# 预生成比请求时生成更快, 一次到位
_DUMMY_HASH: bytes = bcrypt.hashpw(b"dummy_for_timing_v3", bcrypt.gensalt(rounds=10))
_DUMMY_HASH_DECODED = _DUMMY_HASH.decode("utf-8")

# 协议版本(改版时 +1, 入 consent_log)
POLICY_VERSION = "v1.0"


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_mobile(mobile: str) -> None:
    if not MOBILE_RE.match(mobile or ""):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "invalid_mobile", "hint": "请输入 11 位有效手机号"},
        )


def _validate_password_strength(password: str) -> None:
    """P0-8: 密码强度校验(后端为权威)"""
    from app.utils.validators import is_valid_password, is_weak_password
    ok, code = is_valid_password(password)
    if not ok:
        hint_map = {
            "empty": "密码不能为空",
            "too_short": "密码至少 8 位",
            "too_long": "密码不超过 20 位",
            "no_letter": "密码必须包含字母",
            "no_digit": "密码必须包含数字",
            "illegal_char": "密码含非法字符,请使用字母+数字+常用符号",
        }
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "weak_password", "code": code, "hint": hint_map.get(code, "密码不符合要求")},
        )
    if is_weak_password(password):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "weak_password", "code": "common", "hint": "密码太常见,请换一个(不能是 12345678 等)"},
        )


# ============== Pydantic 模型 ==============
class RegisterRequest(BaseModel):
    """注册请求 - P0-7 三步流程 + P0-8 密码强度"""
    mobile: str = Field(..., min_length=11, max_length=11, description="手机号")
    password: str = Field(..., min_length=6, max_length=20, description="密码 6-20 位")
    # P0-7: sms_token 由 /api/sms/verify-code 颁发
    sms_token: str = Field(..., min_length=10, description="短信验证通过后颁发的 token")
    # 盲点 2: 用户协议勾选(必须显式同意)
    policy_agreed: bool = Field(..., description="是否同意《用户协议》和《隐私政策》")
    # 旧字段保留兼容(可选)
    captcha_id: Optional[str] = Field(default=None, description="可选: 服务端图验 code_id(扩展用)")
    captcha_code: Optional[str] = Field(default=None, description="可选: 图验值")


class LoginRequest(BaseModel):
    """登录请求 - 密码优先, 验证码兜底"""
    mobile: str = Field(..., min_length=11, max_length=11, description="手机号")
    password: Optional[str] = Field(default=None, min_length=6, max_length=20, description="密码(优先)")
    code: Optional[str] = Field(default=None, min_length=6, max_length=6, description="验证码(兜底)")
    # 旧兼容: 老用户固定 123456
    legacy_code: Optional[str] = Field(default=None, description="兼容: 兜底验证码,默认 123456")


class AuthResponse(BaseModel):
    """响应(契约不变)"""
    token: str
    user_id: int
    mobile: str
    has_password: bool


# ============== /api/register ==============
@router.post("/register-sms", response_model=AuthResponse)  # V1 保留: 短信注册(密码版走 password.py /register)
async def register(req: RegisterRequest, request: Request):
    """
    V1 短信注册(保留备用, V2 走 password.py /register 密码注册)
    三步注册: 短信验证通过后, 凭 sms_token 注册
    1) 校验 sms_token (必须是 verify-code 颁发的, 5min 内, 一次性)
    2) 密码强度 (P0-8)
    3) 限流 (P0-4 三层桶)
    4) bcrypt 散列密码
    5) 写入 user_consent_log (盲点 2)
    6) 签发 JWT (P0-5)
    """
    _validate_mobile(req.mobile)
    _validate_password_strength(req.password)

    # 盲点 2: 必须显式勾选协议
    if not req.policy_agreed:
        register_total.labels(status="consent_denied").inc()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "consent_required", "hint": "请先勾选并同意《用户协议》和《隐私政策》"},
        )

    # 1. 校验 sms_token(必须先发短信 + 验证)
    token_info = consume_sms_token(req.sms_token)
    if not token_info:
        register_total.labels(status="sms_token_invalid").inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "sms_token_invalid", "hint": "短信验证已失效,请重新获取验证码"},
        )
    if token_info["purpose"] != "register":
        register_total.labels(status="sms_token_wrong_purpose").inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "sms_token_wrong_purpose", "hint": "短信 token 用途不匹配(应为 register)"},
        )
    if token_info["mobile"] != req.mobile:
        register_total.labels(status="sms_token_mobile_mismatch").inc()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "sms_token_mobile_mismatch", "hint": "短信 token 与手机号不匹配"},
        )

    # 3. 限流(在 token 校验后, 防止无谓消耗)
    ip = _client_ip(request)
    rl = get_register_limiter().check(ip=ip, endpoint="/api/register", mobile=req.mobile)
    if not rl.allowed:
        rate_limit_blocked_total.labels(layer=rl.reason, endpoint="/api/register").inc()
        register_total.labels(status="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "layer": rl.reason,
                "hint": "操作过于频繁,请稍后再试",
                "retry_after": round(rl.retry_after, 1),
            },
        )

    # 4. bcrypt 散列 + 计时(P0-3 时序对齐)
    with bcrypt_duration_seconds.time():
        pwd_hash = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.mobile == req.mobile).first()
        if existing and existing.password_hash:
            # 已注册 + 有密码 - 拒绝(P0-7: 不能覆盖别人账号)
            register_total.labels(status="mobile_exists").inc()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "mobile_exists", "hint": "该手机号已注册,请直接登录"},
            )

        client_ip = _client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:512]

        if existing:
            # 老用户补设密码
            existing.password_hash = pwd_hash
            existing.password_version = (existing.password_version or 0) + 1
            db.commit()
            db.refresh(existing)
            user = existing
            # 写同意日志(老用户补设, 也算再次同意)
            consent = UserConsentLog(
                user_id=user.id,
                mobile=user.mobile,
                ip=client_ip,
                user_agent=user_agent,
                policy_version=POLICY_VERSION,
            )
            db.add(consent)
            db.commit()
            logger.info("老用户补设密码 mobile=%s user_id=%s ver=%s", req.mobile, user.id, user.password_version)
        else:
            user = User(
                mobile=req.mobile,
                password_hash=pwd_hash,
                password_version=0,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            # 写同意日志
            consent = UserConsentLog(
                user_id=user.id,
                mobile=user.mobile,
                ip=client_ip,
                user_agent=user_agent,
                policy_version=POLICY_VERSION,
            )
            db.add(consent)
            db.commit()
            logger.info("新用户注册 mobile=%s user_id=%s ver=0", req.mobile, user.id)

        # 6. 签发 JWT
        token = create_token(user.id, password_version=user.password_version or 0)
        register_total.labels(status="success").inc()
        return AuthResponse(
            token=token,
            user_id=user.id,
            mobile=user.mobile,
            has_password=True,
        )
    except IntegrityError as e:
        db.rollback()
        register_total.labels(status="db_error").inc()
        logger.warning("register integrity error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "mobile_exists", "hint": "该手机号已注册"},
        )
    finally:
        db.close()


# ============== /api/login ==============
@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request):
    """
    登录 - 密码优先 / 验证码兜底

    P0 修复:
      P0-3: 不论用户是否存在, 都做一次 bcrypt dummy check
      P0-4: 三层桶限流
      P0-5: JWT 签发
    """
    _validate_mobile(req.mobile)

    # 限流
    ip = _client_ip(request)
    rl = get_login_v2_limiter().check(ip=ip, endpoint="/api/login", mobile=req.mobile)
    if not rl.allowed:
        rate_limit_blocked_total.labels(layer=rl.reason, endpoint="/api/login").inc()
        login_total.labels(status="rate_limited").inc()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limited",
                "layer": rl.reason,
                "hint": "登录过于频繁,请稍后再试",
                "retry_after": round(rl.retry_after, 1),
            },
        )

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.mobile == req.mobile).first()

        if not user:
            # P0-3: 时序对齐 - 对未注册用户也做一次 dummy bcrypt
            with bcrypt_duration_seconds.time():
                try:
                    bcrypt.checkpw(b"dummy_attempt", _DUMMY_HASH)
                except Exception:
                    pass
            login_total.labels(status="user_not_found").inc()
            # 模糊错误(不区分未注册 vs 密码错, 防枚举)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "auth_failed", "hint": "手机号或密码错误"},
            )

        if user.password_hash:
            if not req.password:
                login_total.labels(status="password_required").inc()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "auth_failed", "hint": "手机号或密码错误"},
                )
            with bcrypt_duration_seconds.time():
                try:
                    ok = bcrypt.checkpw(req.password.encode("utf-8"), user.password_hash.encode("utf-8"))
                except Exception as e:
                    logger.warning("bcrypt 校验异常 mobile=%s err=%s", req.mobile, e)
                    ok = False
            if not ok:
                login_total.labels(status="wrong_password").inc()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={"error": "auth_failed", "hint": "手机号或密码错误"},
                )
            # 登录成功 - 签发 JWT
            token = create_token(user.id, password_version=user.password_version or 0)
            login_total.labels(status="success").inc()
            logger.info("用户密码登录 mobile=%s user_id=%s", req.mobile, user.id)
            return AuthResponse(
                token=token,
                user_id=user.id,
                mobile=user.mobile,
                has_password=True,
            )

        # 老用户无密码 - 验证码兜底(保留老路径, 不发短信, 走固定码)
        import os
        fixed_code = os.getenv("LOGIN_FIXED_CODE", "123456")
        if not req.legacy_code or req.legacy_code != fixed_code:
            login_total.labels(status="invalid_legacy_code").inc()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "auth_failed", "hint": "手机号或验证码错误"},
            )
        token = create_token(user.id, password_version=user.password_version or 0)
        login_total.labels(status="success_legacy").inc()
        logger.info("老用户验证码登录 mobile=%s user_id=%s", req.mobile, user.id)
        return AuthResponse(
            token=token,
            user_id=user.id,
            mobile=user.mobile,
            has_password=False,
        )
    finally:
        db.close()
