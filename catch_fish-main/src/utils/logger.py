"""
日志配置模块 — 基于 loguru
"""

import sys
from pathlib import Path

from loguru import logger

from src.config import settings

# 移除默认 handler
logger.remove()

# 控制台输出（彩色）
logger.add(
    sys.stdout,
    level=settings.log_level,
    format=(
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    ),
    colorize=True,
)

# 文件输出（所有级别）
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logger.add(
    log_dir / "app_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    rotation="00:00",          # 每天轮转
    retention="30 days",       # 保留30天
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
)

# 错误日志单独记录
logger.add(
    log_dir / "error_{time:YYYY-MM-DD}.log",
    level="ERROR",
    rotation="00:00",
    retention="90 days",
    compression="zip",
)


def get_logger(name: str):
    """获取带模块名的 logger"""
    return logger.bind(name=name)
