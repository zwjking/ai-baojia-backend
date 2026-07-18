"""
三层限流器 - P0-4 重构

三层:
  1. (ip, endpoint)        - 10 次/分钟      防单 IP 暴力
  2. (mobile, endpoint)    - 5 次/小时       防单号刷短信
  3. global                - 100 次/秒       防 DDoS

实现:
  - 内存 sliding window (单进程) - 够 demo
  - 启动时初始化,可被外部 redis 替换(留接口)

向后兼容:
  - 保留原 get_login_limiter() / get_quote_limiter() / get_lead_limiter()
    这些是全局 1 QPS 老接口(W2 P1),给 quote/lead 用
  - 新增三层桶给 register/login/forgot/sms 走
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, NamedTuple


class RateLimitResult(NamedTuple):
    allowed: bool
    retry_after: float = 0.0
    reason: str = ""  # blocked 时,具体被哪一层挡住


# ============================================================
# 1. 原版: 全局令牌桶(W2 P1 给 quote/lead 用, 不动)
# ============================================================
class TokenBucketRateLimiter:
    """滑动窗口限流器 - 允许 qps 个请求/秒, 超出时拒绝(不阻塞)"""
    def __init__(self, qps: int = 5):
        self.qps = qps
        self._timestamps: Deque[float] = deque()

    def acquire(self) -> RateLimitResult:
        now = time.monotonic()
        while self._timestamps and now - self._timestamps[0] > 1.0:
            self._timestamps.popleft()
        if len(self._timestamps) < self.qps:
            self._timestamps.append(now)
            return RateLimitResult(allowed=True)
        retry_after = 1.0 - (now - self._timestamps[0])
        return RateLimitResult(allowed=False, retry_after=max(0.0, retry_after))


_quote_limiter: TokenBucketRateLimiter | None = None
_login_limiter: TokenBucketRateLimiter | None = None
_lead_limiter: TokenBucketRateLimiter | None = None


def get_quote_limiter() -> TokenBucketRateLimiter:
    global _quote_limiter
    if _quote_limiter is None:
        from app.config import RATE_LIMIT_QPS
        _quote_limiter = TokenBucketRateLimiter(qps=RATE_LIMIT_QPS)
    return _quote_limiter


def get_login_limiter() -> TokenBucketRateLimiter:
    global _login_limiter
    if _login_limiter is None:
        from app.config import LOGIN_RATE_QPS
        _login_limiter = TokenBucketRateLimiter(qps=LOGIN_RATE_QPS)
    return _login_limiter


def get_lead_limiter() -> TokenBucketRateLimiter:
    global _lead_limiter
    if _lead_limiter is None:
        from app.config import LEAD_RATE_QPS
        _lead_limiter = TokenBucketRateLimiter(qps=LEAD_RATE_QPS)
    return _lead_limiter


# ============================================================
# 2. 新版: 三层桶限流器 (P0-4)
# ============================================================
class MultiLayerRateLimiter:
    """
    三层滑动窗口限流器

    层级:
      - L1 (ip, endpoint):       limit1 次/60s    防单 IP 暴力
      - L2 (mobile, endpoint):   limit2 次/3600s  防单号刷短信
      - L3 (global):             limit3 次/s      防 DDoS

    用法:
        limiter = MultiLayerRateLimiter(...)
        result = limiter.check(ip="1.2.3.4", endpoint="/api/register", mobile="138...")
        if not result.allowed:
            raise HTTPException(429, ...)
    """
    def __init__(
        self,
        ip_limit: int = 10,
        ip_window: float = 60.0,
        mobile_limit: int = 5,
        mobile_window: float = 3600.0,
        global_limit: int = 100,
        global_window: float = 1.0,
    ):
        self.ip_limit = ip_limit
        self.ip_window = ip_window
        self.mobile_limit = mobile_limit
        self.mobile_window = mobile_window
        self.global_limit = global_limit
        self.global_window = global_window
        # 三组 deque
        self._ip_buckets: dict[tuple[str, str], Deque[float]] = {}
        self._mobile_buckets: dict[tuple[str, str], Deque[float]] = {}
        self._global_buckets: Deque[float] = deque()
        self._lock = Lock()

    def _evict(self, dq: Deque[float], window: float) -> None:
        now = time.monotonic()
        while dq and now - dq[0] > window:
            dq.popleft()

    def check(
        self,
        ip: str,
        endpoint: str,
        mobile: str | None = None,
    ) -> RateLimitResult:
        """
        检查是否允许, 不在桶内则尝试放入(原子)

        返回:
          RateLimitResult(allowed=True) 放行
          RateLimitResult(allowed=False, retry_after=..., reason="...") 拒绝
        """
        with self._lock:
            now = time.monotonic()

            # L3: 全局
            self._evict(self._global_buckets, self.global_window)
            if len(self._global_buckets) >= self.global_limit:
                return RateLimitResult(
                    allowed=False,
                    retry_after=self.global_window - (now - self._global_buckets[0]),
                    reason="global",
                )

            # L1: (ip, endpoint)
            ip_key = (ip or "unknown", endpoint)
            ip_dq = self._ip_buckets.setdefault(ip_key, deque())
            self._evict(ip_dq, self.ip_window)
            if len(ip_dq) >= self.ip_limit:
                return RateLimitResult(
                    allowed=False,
                    retry_after=self.ip_window - (now - ip_dq[0]),
                    reason="ip_endpoint",
                )

            # L2: (mobile, endpoint) - 仅对提供 mobile 的接口生效
            if mobile:
                m_key = (mobile, endpoint)
                m_dq = self._mobile_buckets.setdefault(m_key, deque())
                self._evict(m_dq, self.mobile_window)
                if len(m_dq) >= self.mobile_limit:
                    return RateLimitResult(
                        allowed=False,
                        retry_after=self.mobile_window - (now - m_dq[0]),
                        reason="mobile_endpoint",
                    )
                m_dq.append(now)

            ip_dq.append(now)
            self._global_buckets.append(now)
            return RateLimitResult(allowed=True)


# 各接口独立三层限流器(配置)
_register_limiter: MultiLayerRateLimiter | None = None
_login_v2_limiter: MultiLayerRateLimiter | None = None
_forgot_limiter: MultiLayerRateLimiter | None = None
_sms_limiter: MultiLayerRateLimiter | None = None


def get_register_limiter() -> MultiLayerRateLimiter:
    """注册接口: 10/分钟/IP + 5/小时/mobile + 100/秒/全局"""
    global _register_limiter
    if _register_limiter is None:
        from app.config import REGISTER_IP_LIMIT, REGISTER_IP_WINDOW, REGISTER_MOBILE_LIMIT, REGISTER_MOBILE_WINDOW
        _register_limiter = MultiLayerRateLimiter(
            ip_limit=REGISTER_IP_LIMIT, ip_window=REGISTER_IP_WINDOW,
            mobile_limit=REGISTER_MOBILE_LIMIT, mobile_window=REGISTER_MOBILE_WINDOW,
            global_limit=100, global_window=1.0,
        )
    return _register_limiter


def get_login_v2_limiter() -> MultiLayerRateLimiter:
    """登录接口: 5/分钟/IP + 10/小时/mobile(允许正常用户偶尔密码错几次) + 100/秒/全局"""
    global _login_v2_limiter
    if _login_v2_limiter is None:
        from app.config import LOGIN_IP_LIMIT, LOGIN_IP_WINDOW, LOGIN_MOBILE_LIMIT, LOGIN_MOBILE_WINDOW
        _login_v2_limiter = MultiLayerRateLimiter(
            ip_limit=LOGIN_IP_LIMIT, ip_window=LOGIN_IP_WINDOW,
            mobile_limit=LOGIN_MOBILE_LIMIT, mobile_window=LOGIN_MOBILE_WINDOW,
            global_limit=100, global_window=1.0,
        )
    return _login_v2_limiter


def get_forgot_limiter() -> MultiLayerRateLimiter:
    """忘记密码: 5/分钟/IP + 3/小时/mobile + 100/秒/全局"""
    global _forgot_limiter
    if _forgot_limiter is None:
        from app.config import FORGOT_IP_LIMIT, FORGOT_IP_WINDOW, FORGOT_MOBILE_LIMIT, FORGOT_MOBILE_WINDOW
        _forgot_limiter = MultiLayerRateLimiter(
            ip_limit=FORGOT_IP_LIMIT, ip_window=FORGOT_IP_WINDOW,
            mobile_limit=FORGOT_MOBILE_LIMIT, mobile_window=FORGOT_MOBILE_WINDOW,
            global_limit=100, global_window=1.0,
        )
    return _forgot_limiter


def get_sms_limiter() -> MultiLayerRateLimiter:
    """短信发送: 3/分钟/IP + 5/天/mobile + 100/秒/全局"""
    global _sms_limiter
    if _sms_limiter is None:
        from app.config import SMS_IP_LIMIT, SMS_IP_WINDOW, SMS_MOBILE_LIMIT, SMS_MOBILE_WINDOW
        _sms_limiter = MultiLayerRateLimiter(
            ip_limit=SMS_IP_LIMIT, ip_window=SMS_IP_WINDOW,
            mobile_limit=SMS_MOBILE_LIMIT, mobile_window=SMS_MOBILE_WINDOW,
            global_limit=100, global_window=1.0,
        )
    return _sms_limiter
