"""Railway 启动脚本 - 自动读取 PORT 环境变量"""
import os
from uvicorn import run

port = int(os.environ.get("PORT", 8000))
run("app.main:app", host="0.0.0.0", port=port, log_level="info")
