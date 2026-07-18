"""
服务端图验 API - P0-1

GET /api/captcha       生成图验, 返回 {code_id, image_base64}
POST /api/captcha/verify  校验图验, 内部用, 也可外部用(短信发送前)

设计:
  - 内存 store: code_id -> {code, issued_at}
  - 5 分钟 TTL
  - code_id 一次性 (verify 后立即失效, 防止重放)
"""
from __future__ import annotations

import base64
import logging
import time
import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.captcha_image import generate_captcha_png
from app.utils.metrics import captcha_generate_total

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/captcha", tags=["captcha"])

# 内存 store: code_id -> (code, issued_at, used)
_store: dict[str, tuple[str, float, bool]] = {}
_TTL = 300.0  # 5 分钟


def _cleanup() -> int:
    now = time.monotonic()
    expired = [k for k, (_, t, _) in _store.items() if now - t > _TTL]
    for k in expired:
        _store.pop(k, None)
    return len(expired)


class GenerateResponse(BaseModel):
    code_id: str
    image_base64: str  # data:image/png;base64,...


class VerifyRequest(BaseModel):
    code_id: str
    code: str


class VerifyResponse(BaseModel):
    valid: bool


@router.get("", response_model=GenerateResponse)
async def get_captcha():
    """
    生成图验
      返回 code_id + image_base64
      前端在 <img src="data:image/png;base64,..."> 直接用
    """
    _cleanup()
    png_bytes, code = generate_captcha_png()
    code_id = uuid.uuid4().hex
    _store[code_id] = (code.upper(), time.monotonic(), False)
    captcha_generate_total.inc()
    logger.info("captcha generated code_id=%s len=%d", code_id[:8] + "...", len(code))
    return GenerateResponse(
        code_id=code_id,
        image_base64="data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii"),
    )


@router.post("/verify", response_model=VerifyResponse)
async def verify_captcha(req: VerifyRequest):
    """
    校验图验(外部用, 例如短信发送前的前置校验)

    内部路由(routers/auth.py 等)也直接调 verify_captcha_internal()
    """
    valid = _verify_internal(req.code_id, req.code)
    return VerifyResponse(valid=valid)


# ============== Dev-only: 暴露 code (仅测试用) ==============
import os as _os
if _os.getenv("CAPTCHA_DEV_PEEK", "false").lower() == "true":
    @router.post("/dev-peek", include_in_schema=False)
    async def dev_peek(req: VerifyRequest):
        """
        仅 .env 设 CAPTCHA_DEV_PEEK=true 时可用
        测试/验收脚本专用, 返回 code_id 对应的 code
        生产环境必须保持 CAPTCHA_DEV_PEEK=false (默认)
        """
        rec = _store.get(req.code_id)
        if not rec:
            return {"code": None, "error": "no_such_code_id"}
        code, issued_at, used = rec
        if used:
            return {"code": None, "error": "already_used"}
        # 不 mark used, 允许后续 /api/sms/send-code 走正常验证
        return {"code": code}


def _verify_internal(code_id: str, code: str) -> bool:
    """
    内部校验: 一次性 + 5min TTL
    成功则 mark used, 防止重放
    """
    if not code_id or not code:
        return False
    rec = _store.get(code_id)
    if not rec:
        return False
    stored_code, issued_at, used = rec
    if used:
        return False
    if time.monotonic() - issued_at > _TTL:
        _store.pop(code_id, None)
        return False
    if stored_code != code.strip().upper():
        return False
    # 标记 used(防重放)
    _store[code_id] = (stored_code, issued_at, True)
    return True
