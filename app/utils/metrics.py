"""
Prometheus 指标 - 盲点 3

指标:
  register_total{status=success|failed}        Counter
  login_total{status=success|failed}            Counter
  forgot_reset_total{status=success|failed}     Counter
  sms_send_total{purpose, status}               Counter
  captcha_generate_total                        Counter
  bcrypt_duration_seconds                       Histogram
  quote_total{path=agnes|fallback}              Counter
  http_requests_total{method, path, status}     Counter
  rate_limit_blocked_total{layer, endpoint}     Counter

暴露:
  GET /metrics  (prometheus_client.generate_latest)
"""
from __future__ import annotations

import time
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

# 用默认 registry 即可
REGISTRY = None  # 使用默认


# ============== 业务指标 ==============
register_total = Counter(
    "register_total",
    "注册请求总数",
    ["status"],  # success / failed
)
login_total = Counter(
    "login_total",
    "登录请求总数",
    ["status"],
)
forgot_reset_total = Counter(
    "forgot_reset_total",
    "忘记密码重置请求总数",
    ["status"],
)
sms_send_total = Counter(
    "sms_send_total",
    "短信发送请求总数",
    ["purpose", "status"],  # purpose: register|reset
)
captcha_generate_total = Counter(
    "captcha_generate_total",
    "图验生成总数",
)
rate_limit_blocked_total = Counter(
    "rate_limit_blocked_total",
    "被限流挡住的请求数",
    ["layer", "endpoint"],  # layer: ip_endpoint|global|mobile_endpoint
)
quote_total = Counter(
    "quote_total",
    "报价请求总数",
    ["path"],  # agnes / fallback
)

# ============== 性能指标 ==============
bcrypt_duration_seconds = Histogram(
    "bcrypt_duration_seconds",
    "bcrypt 校验耗时分布",
    buckets=(0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0),
)

http_requests_total = Counter(
    "http_requests_total",
    "HTTP 请求总数",
    ["method", "path", "status"],
)


# ============== 工具 ==============
@contextmanager
def bcrypt_timer():
    """bcrypt 计时上下文"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        bcrypt_duration_seconds.observe(elapsed)


def render_metrics() -> tuple[bytes, str]:
    """渲染 /metrics 响应"""
    return generate_latest(), CONTENT_TYPE_LATEST
