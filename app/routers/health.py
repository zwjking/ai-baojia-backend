"""
健康检查 - GET /health
"""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """探活端点 - K8s/Docker/腾讯云 SLB 用"""
    return {"status": "ok", "service": "ai-quote-backend", "version": "0.1.0"}
