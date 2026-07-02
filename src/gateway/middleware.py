"""
FastAPI 中间件 — 请求日志、限流、CORS
"""

import time

from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件"""

    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start

        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} "
            f"({elapsed:.3f}s)"
        )
        return response


class SimpleRateLimiter:
    """
    简易内存限流器（生产环境应替换为 Redis 实现）

    每个 IP 每分钟最多 rate_limit_per_minute 次请求
    """

    def __init__(self, max_requests: int = 20):
        self.max_requests = max_requests
        self._store: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """检查是否允许请求"""
        now = time.time()
        window_start = now - 60  # 1 分钟窗口

        # 清理过期记录
        if key in self._store:
            self._store[key] = [t for t in self._store[key] if t > window_start]
        else:
            self._store[key] = []

        if len(self._store[key]) < self.max_requests:
            self._store[key].append(now)
            return True
        return False


rate_limiter = SimpleRateLimiter(max_requests=settings.rate_limit_per_minute)


def setup_middleware(app):
    """注册所有中间件"""

    # CORS — 允许所有来源（开发环境），生产需收紧
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应限制为具体域名
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求日志
    app.add_middleware(RequestLoggingMiddleware)
