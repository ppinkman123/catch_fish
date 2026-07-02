"""
异步 HTTP 客户端 — 基于 httpx
提供重试、超时、代理等通用能力
"""

from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AsyncHTTPClient:
    """异步 HTTP 客户端，封装 httpx.AsyncClient"""

    def __init__(
        self,
        base_url: str = "",
        timeout: int = settings.request_timeout,
        proxy: Optional[str] = None,
        cookies: Optional[dict] = None,
        headers: Optional[dict] = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        self.proxy = proxy or settings.scraper_proxy
        self.cookies = cookies or {}
        self.headers = headers or {
            "User-Agent": settings.xianyu_user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            proxy=self.proxy,
            cookies=self.cookies,
            headers=self.headers,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET 请求（带自动重试）"""
        logger.debug(f"HTTP GET {url}")
        response = await self._client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """POST 请求（带自动重试）"""
        logger.debug(f"HTTP POST {url}")
        response = await self._client.post(url, **kwargs)
        response.raise_for_status()
        return response

    async def get_json(self, url: str, **kwargs) -> dict[str, Any]:
        """GET 并直接返回 JSON"""
        response = await self.get(url, **kwargs)
        return response.json()

    async def get_text(self, url: str, **kwargs) -> str:
        """GET 并直接返回文本"""
        response = await self.get(url, **kwargs)
        return response.text
