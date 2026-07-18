"""
通用校验器 - P0-8 密码强度 / 手机号 / 验证码格式

约束:
  - 所有校验「后端为权威」,前端提示仅供参考
  - 错误信息走业务错误码 (error),UI 层做映射
"""
from __future__ import annotations

import re
from typing import Tuple

# 国内手机号 (11 位, 1[3-9] 开头)
MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")

# 密码强度: 8-20 位, 至少一个字母 + 一个数字
PASSWORD_RE = re.compile(
    r"""^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9!@#$%^&*()_\-+=\[\]{};:'",.<>/?\\|`~]{8,20}$"""
)

# 短信验证码: 6 位数字
SMS_CODE_RE = re.compile(r"^\d{6}$")

# 服务端图验: 4 位字母数字(去 I/L/0/1)
CAPTCHA_RE = re.compile(r"^[A-Z2-9]{4}$")


def is_valid_mobile(mobile: str | None) -> bool:
    """手机号格式校验"""
    return bool(MOBILE_RE.match(mobile or ""))


def is_valid_password(password: str | None) -> Tuple[bool, str]:
    """
    密码强度校验
    返回: (是否通过, 错误码)

    错误码:
      - empty          密码为空
      - too_short      不足 8 位
      - too_long       超过 20 位
      - no_letter      缺字母
      - no_digit       缺数字
      - illegal_char   含非法字符
      - ok             通过
    """
    if not password:
        return False, "empty"
    if len(password) < 8:
        return False, "too_short"
    if len(password) > 20:
        return False, "too_long"
    if not re.search(r"[A-Za-z]", password):
        return False, "no_letter"
    if not re.search(r"\d", password):
        return False, "no_digit"
    if not PASSWORD_RE.match(password):
        return False, "illegal_char"
    return True, "ok"


def is_valid_sms_code(code: str | None) -> bool:
    """短信验证码: 6 位数字"""
    return bool(SMS_CODE_RE.match(code or ""))


def is_valid_captcha_text(code: str | None) -> bool:
    """服务端图验: 4 位字母数字(去 I/L/0/1)"""
    return bool(CAPTCHA_RE.match((code or "").upper()))


# 常见弱密码黑名单(top 100, 拦住最常见)
WEAK_PASSWORDS = frozenset({
    "12345678", "123456789", "1234567890",
    "password", "password1", "password123",
    "qwerty123", "qwertyuiop",
    "abc12345", "abc123456", "abcdefgh",
    "11111111", "00000000", "66666666", "88888888",
    "iloveyou", "admin123", "welcome1",
    "monkey123", "dragon123", "master123",
    "12341234", "12344321", "11223344",
    "asdf1234", "qwer1234", "zxcv1234",
})


def is_weak_password(password: str) -> bool:
    """是否在弱密码黑名单(不区分大小写)"""
    return (password or "").lower() in WEAK_PASSWORDS
