"""统一日志配置"""
import logging
import sys
from pathlib import Path

from app.config import LOG_LEVEL, LOG_FILE, BASE_DIR


def setup_logging():
    log_file_path = BASE_DIR / LOG_FILE
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # 防止重复添加
    if root.handlers:
        return

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # 文件
    fh = logging.FileHandler(log_file_path, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
