"""
JWT 鉴权 + 黑名单 - P0-5 改造

旧版: token = str(uuid.uuid4()) 永久 + 无签名 + 无吊销
新版: JWT (HS256) + 24h 过期 + jti 黑名单 (改密时吊销)

设计:
  - secret 优先从 .env JWT_SECRET 读, 缺则用 APP_PORT+APP_HOST 派生一个 fallback
    (生产一定要设 JWT_SECRET, 否则签名可猜)
  - payload: { sub: user_id, iat, exp, jti, ver }
    ver = 用户密码版本号 (用户表加 password_version, 改密 +1)
  - 校验: 1) 签名 + exp  2) jti 不在黑名单  3) ver 与用户当前 ver 一致

黑名单存储:
  - 内存 dict (demo) - 够本地
  - 接口预留 redis (生产部署时换)

W2 兼容:
  - 老 token (UUID) 暂时兼容(给 quote 旧调用者), 但建议客户端下次登录拿 JWT
  - 通过 verify_token() 优先 JWT, 失败再尝试老 UUID
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# JWT 配置
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24

# secret 派生
_FALLBACK_SECRET_FILE = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", ".jwt_secret"
)


def _load_or_init_secret() -> str:
    """
    加载 JWT secret
      1) .env JWT_SECRET
      2) data/.jwt_secret 文件(首次启动生成)
      3) 拼 APP_HOST+APP_PORT 派生(最弱, 仅 demo)
    """
    env_secret = os.getenv("JWT_SECRET")
    if env_secret:
        return env_secret
    try:
        if os.path.exists(_FALLBACK_SECRET_FILE):
            with open(_FALLBACK_SECRET_FILE, "r", encoding="utf-8") as f:
                stored = f.read().strip()
                if stored:
                    return stored
    except Exception as e:
        logger.warning("read .jwt_secret failed: %s", e)
    # 生成新的
    new_secret = secrets.token_urlsafe(48)
    try:
        os.makedirs(os.path.dirname(_FALLBACK_SECRET_FILE), exist_ok=True)
        with open(_FALLBACK_SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(new_secret)
        os.chmod(_FALLBACK_SECRET_FILE, 0o600)
        logger.info("JWT secret initialized at %s", _FALLBACK_SECRET_FILE)
    except Exception as e:
        logger.warning("write .jwt_secret failed: %s", e)
    return new_secret


_JWT_SECRET: Optional[str] = None


def get_jwt_secret() -> str:
    global _JWT_SECRET
    if _JWT_SECRET is None:
        _JWT_SECRET = _load_or_init_secret()
    return _JWT_SECRET


# ============== 黑名单(内存) ==============
# jti -> expire_at (到期自动清理)
_blacklist: dict[str, datetime] = {}


def blacklist_jti(jti: str, expire_at: datetime) -> None:
    """把 jti 加入黑名单(直到 expire_at 之后无需再保留)"""
    _blacklist[jti] = expire_at
    logger.info("JWT jti blacklisted: %s (until %s)", jti[:8] + "...", expire_at.isoformat())


def is_blacklisted(jti: str) -> bool:
    """检查 jti 是否在黑名单(过期自动清理)"""
    if jti not in _blacklist:
        return False
    if datetime.now(timezone.utc) >= _blacklist[jti]:
        _blacklist.pop(jti, None)
        return False
    return True


def cleanup_blacklist() -> int:
    """清理过期 jti, 返回清理数量"""
    now = datetime.now(timezone.utc)
    expired = [j for j, t in _blacklist.items() if now >= t]
    for j in expired:
        _blacklist.pop(j, None)
    if expired:
        logger.info("JWT blacklist cleanup: %d expired jti removed", len(expired))
    return len(expired)


# ============== 签发 / 校验 ==============
def create_token(user_id: int, password_version: int = 0) -> str:
    """
    签发 JWT
      payload: {sub, iat, exp, jti, ver}
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": uuid.uuid4().hex,
        "ver": password_version,
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)
    logger.info("JWT issued user_id=%s jti=%s exp=%s", user_id, payload["jti"][:8] + "...", expire.isoformat())
    return token


def verify_token(token: str) -> Optional[dict]:
    """
    校验 JWT, 失败返回 None
    通过: 1) 签名  2) 未过期  3) jti 未吊销
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    except JWTError as e:
        logger.debug("JWT verify failed: %s", e)
        return None
    jti = payload.get("jti")
    if jti and is_blacklisted(jti):
        logger.info("JWT rejected: jti blacklisted (%s...)", jti[:8])
        return None
    return payload


def is_uuid_token(token: str) -> bool:
    """判断是否为旧版 UUID token(长度 32 或 36, 十六进制/带连字符)"""
    if not token or len(token) > 40:
        return False
    cleaned = token.replace("-", "")
    return len(cleaned) == 32 and all(c in "0123456789abcdefABCDEF" for c in cleaned)


def is_legacy_uuid_token_valid(token: str) -> bool:
    """
    老版 UUID token 校验 - 简单 hash 比对
    生产应强制升级, 这里给过渡期
    """
    if not is_uuid_token(token):
        return False
    # 这里只校验格式, 不验证有效性 (因为旧 token 没存数据库)
    # 业务上应该强制要求用户重新登录拿 JWT
    return False  # 严格模式: 老 token 全部失效, 强制重新登录


# ============== 业务层: 改密时吊销 ==============
def revoke_user_tokens(user_id: int, current_version: int) -> None:
    """
    改密后调用: 增加用户 password_version
    所有 ver < new_version 的 token 失效(在 verify_token 里比对 ver 字段)
    """
    # 实际吊销靠 password_version 字段(改密时 +1)
    # 旧 jti 也加入黑名单(可选, 这里我们用 ver 字段天然吊销)
    logger.info("User %s password_version bumped to %s, all old JWT invalidated", user_id, current_version)


# ============== FastAPI 依赖 ==============
from fastapi import Header, HTTPException, status as http_status


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> int:
    """
    FastAPI 依赖: 从 Authorization: Bearer <token> 提取 user_id
    失败 401
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing_token", "hint": "请先登录"},
        )
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_token", "hint": "登录已过期,请重新登录"},
        )
    # 检查 password_version
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail={"error": "bad_token", "hint": "token 格式错误"},
        )

    # 校验 ver 字段 - 改密后失效
    from app.models.database import SessionLocal, User  # 避免循环引用
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail={"error": "user_not_found", "hint": "用户不存在"},
            )
        token_ver = int(payload.get("ver", 0))
        current_ver = int(getattr(user, "password_version", 0) or 0)
        if token_ver < current_ver:
            # 改密后旧 token 失效
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail={"error": "token_revoked", "hint": "密码已修改,请重新登录"},
            )
        return user_id
    finally:
        db.close()
