"""
A2A Client — 异步 HTTP 客户端，调用远程 Agent

用法:
    from src.a2a import A2AClient
    from src.models.schemas import FinderResult

    client = A2AClient()
    client.register("finder", "http://localhost:8001")
    client.register("encyclopedia", "http://localhost:8002")

    # 调用 Finder
    data = await client.call_agent("finder", product_name="劳力士")
    result = FinderResult(**data)

    # 调用 Calculator（传入 Pydantic 模型，自动序列化）
    data = await client.call_agent("calculator",
        finder_result=finder_result,
        encyclopedia_result=enc_result,
    )
    result = CalculatorResult(**data)

    await client.close()
"""

from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel

from src.utils.logger import get_logger

logger = get_logger("a2a.client")


def _serialize_value(value: Any) -> Any:
    """将单个值序列化为 JSON 兼容格式"""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


class A2AClient:
    """A2A Agent 异步客户端

    核心能力:
      - Agent 注册表: 维护 name → base_url 映射
      - 自动序列化: Pydantic 模型参数 → JSON
      - 类型安全: 返回值是 dict，调用方自行构建 Pydantic 模型
      - 超时控制: 默认 60s，可配置
    """

    def __init__(self, timeout: float = 60.0):
        self._registry: dict[str, str] = {}  # name → base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """延迟创建 HTTP 客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    # ---- 注册 ----

    def register(self, name: str, base_url: str) -> "A2AClient":
        """注册一个 Agent

        Args:
            name: Agent 名称（如 "finder"）
            base_url: Agent 服务地址（如 "http://localhost:8001"）
        """
        self._registry[name] = base_url.rstrip("/")
        logger.info(f"注册 Agent: {name} → {base_url}")
        return self

    def register_many(self, agents: dict[str, str]) -> "A2AClient":
        """批量注册"""
        for name, url in agents.items():
            self.register(name, url)
        return self

    def list_agents(self) -> list[str]:
        """列出已注册的 Agent"""
        return list(self._registry.keys())

    # ---- 核心调用 ----

    async def call_agent(
        self,
        name: str,
        **params,
    ) -> dict[str, Any]:
        """通过注册名调用 Agent

        Args:
            name: Agent 注册名
            **params: Agent.execute(**kwargs) 的参数

        Returns:
            Agent 返回的 JSON dict

        Raises:
            ValueError: Agent 未注册
            httpx.HTTPError: HTTP 调用失败
        """
        if name not in self._registry:
            raise ValueError(
                f"未知 Agent: '{name}'，已注册: {list(self._registry.keys())}"
            )
        return await self.call(self._registry[name], **params)

    async def call(
        self,
        base_url: str,
        **params,
    ) -> dict[str, Any]:
        """直接通过 URL 调用 Agent（无需注册）

        Args:
            base_url: Agent 服务地址
            **params: Agent.execute(**kwargs) 的参数

        Returns:
            Agent 返回的 JSON dict
        """
        client = await self._get_client()

        # 序列化参数（Pydantic 模型 → JSON dict）
        serialized = _serialize_value(params)

        url = urljoin(base_url.rstrip("/") + "/", "execute")

        logger.debug(f"A2A 调用 → {url}")
        logger.debug(f"  参数: {list(serialized.keys())}")

        try:
            response = await client.post(url, json={"params": serialized})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response else str(e)
            logger.error(f"A2A [{url}] 返回 {e.response.status_code}: {detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"A2A [{url}] 连接失败: {e}")
            raise

    # ---- 并行调用 ----

    async def gather(
        self,
        calls: list[dict],
    ) -> list[dict[str, Any] | None]:
        """并行调用多个 Agent（asyncio.gather 包装）

        Args:
            calls: 调用列表，如 [
                {"name": "finder", "product_name": "iPhone"},
                {"name": "encyclopedia", "product_name": "iPhone"},
            ]

        Returns:
            与 calls 顺序对应的结果列表（失败项为 None）
        """
        import asyncio

        async def safe_call(i: int, call: dict) -> tuple[int, dict | None]:
            name = call.pop("name")
            try:
                return i, await self.call_agent(name, **call)
            except Exception as e:
                logger.warning(f"并行调用 [{name}] 失败: {e}")
                return i, None

        tasks = [safe_call(i, {**c}) for i, c in enumerate(calls)]
        results = await asyncio.gather(*tasks)
        # 按原始顺序排列
        sorted_results = sorted(results, key=lambda x: x[0])
        return [r[1] for r in sorted_results]

    # ---- Agent Card ----

    async def get_agent_card(self, name: str) -> dict:
        """获取已注册 Agent 的元信息"""
        base_url = self._registry.get(name)
        if not base_url:
            raise ValueError(f"未知 Agent: '{name}'")
        return await self._fetch_agent_card(base_url)

    async def _fetch_agent_card(self, base_url: str) -> dict:
        """从 URL 获取 Agent Card"""
        client = await self._get_client()
        url = urljoin(base_url.rstrip("/") + "/", "agent-card")
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def discover(self, url: str) -> dict:
        """从 URL 发现 Agent Card（无需注册）"""
        return await self._fetch_agent_card(url)

    # ---- 生命周期 ----

    async def close(self):
        """关闭 HTTP 客户端，释放连接"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.debug("A2A 客户端已关闭")


# ---- 全局单例 ----

_default_client: A2AClient | None = None


def get_client() -> A2AClient:
    """获取全局 A2A 客户端单例"""
    global _default_client
    if _default_client is None:
        _default_client = A2AClient()
    return _default_client
