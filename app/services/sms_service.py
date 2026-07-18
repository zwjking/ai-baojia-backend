"""
短信服务 - P0-7

当前为 mock 模式:
  - console 输出验证码(开发用)
  - 内存缓存 (5min TTL, 验证一次后失效)

未来接阿里云/腾讯云/容联:
  - 实现 _send_via_provider(mobile, code) 即可
  - 通过 SMS_PROVIDER env 切换
"""
from __future__ import annotations

import logging
import os
import random
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 验证码有效期
CODE_TTL_SECONDS = 300  # 5 分钟

# Mock 模式: 是否打印到日志/控制台
MOCK_MODE = os.getenv("SMS_MOCK", "true").lower() == "true"


@dataclass
class SMSCode:
    mobile: str
    purpose: str  # register / reset
    code: str
    issued_at: float
    used: bool = False


# 内存存储: mobile:purpose -> SMSCode
_store: dict[tuple[str, str], SMSCode] = {}


def _gen_code() -> str:
    """生成 6 位数字验证码"""
    return f"{random.randint(0, 999999):06d}"


def _cleanup_expired() -> int:
    """清理过期验证码, 返回清理数"""
    now = time.time()
    expired = [k for k, v in _store.items() if now - v.issued_at > CODE_TTL_SECONDS]
    for k in expired:
        _store.pop(k, None)
    return len(expired)


def send_code(mobile: str, purpose: str) -> SMSCode:
    """
    发送验证码(返回存储对象, mock 模式下 code 在 .code 字段)
      purpose: register / reset
    """
    _cleanup_expired()

    # 同一 mobile+purpose 60 秒内只允许发一次(防刷)
    existing = _store.get((mobile, purpose))
    if existing and time.time() - existing.issued_at < 60:
        # 还在冷却, 直接返回旧的(不刷新, 也不重发)
        logger.info("SMS cooldown active mobile=%s purpose=%s", mobile, purpose)
        return existing

    code = _gen_code()
    record = SMSCode(
        mobile=mobile,
        purpose=purpose,
        code=code,
        issued_at=time.time(),
    )
    _store[(mobile, purpose)] = record

    if MOCK_MODE:
        # Mock: 打印到日志
        logger.warning(
            "[SMS-MOCK] mobile=%s purpose=%s code=%s (TTL=%ds)",
            mobile, purpose, code, CODE_TTL_SECONDS,
        )
    else:
        # TODO: 真实通道 - 阿里云/腾讯云/容联
        _send_via_provider(mobile, code, purpose)

    return record


def verify_code(mobile: str, code: str, purpose: str) -> bool:
    """
    校验验证码
      成功: True, 且标记 used=True(防重用)
      失败: False
    """
    _cleanup_expired()
    record = _store.get((mobile, purpose))
    if not record:
        logger.info("SMS verify failed: no record mobile=%s purpose=%s", mobile, purpose)
        return False
    if record.used:
        logger.info("SMS verify failed: already used mobile=%s purpose=%s", mobile, purpose)
        return False
    if record.code != code:
        logger.info("SMS verify failed: code mismatch mobile=%s purpose=%s", mobile, purpose)
        return False
    # 校验通过, 标记 used
    record.used = True
    return True


def clear_code(mobile: str, purpose: str) -> None:
    """用完清理(显式)"""
    _store.pop((mobile, purpose), None)


def _send_via_provider(mobile: str, code: str, purpose: str) -> None:
    """
    调用真实短信服务 - TODO

    阿里云:
      from alibabacloud_dysmsapi20170525.client import Client
      ...

    腾讯云:
      from tencentcloud.sms.v20210111 import sms_client
      ...
    """
    raise NotImplementedError(
        "真实短信服务未启用, 当前 MOCK_MODE=true. "
        "请在 .env 设置 SMS_MOCK=false 并实现 _send_via_provider"
    )
