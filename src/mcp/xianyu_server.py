"""
闲鱼 MCP Server

基于 MCP (Model Context Protocol) 协议，将闲鱼平台能力封装为标准化工具，
供 Finder Agent 通过 A2A 协议调用。

实现方式：使用官方 mcp 包的 Server 类。
"""

from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    ListToolsRequest,
    TextContent,
)

from src.mcp.tools import get_tool_definitions
from src.utils.logger import get_logger

logger = get_logger(__name__)


class XianyuMCPServer:
    """
    闲鱼 MCP Server

    提供三个核心工具：
    1. search_items    — 搜索闲鱼商品列表
    2. get_item_detail — 获取商品详情
    3. get_seller_info — 获取卖家信用信息
    """

    def __init__(self, cookie: str = ""):
        self.server = Server("xianyu-mcp-server")
        self.cookie = cookie
        self._register_handlers()

    def _register_handlers(self):
        """注册 MCP 协议处理器"""

        @self.server.list_tools()
        async def list_tools(request: ListToolsRequest) -> list:
            """列出所有可用工具"""
            return get_tool_definitions()

        @self.server.call_tool()
        async def call_tool(request: CallToolRequest) -> list[TextContent]:
            """调用指定工具"""
            tool_name = request.params.name
            arguments = request.params.arguments or {}

            handler = getattr(self, f"_handle_{tool_name}", None)
            if handler is None:
                return [TextContent(
                    type="text",
                    text=f"未知工具: {tool_name}",
                )]

            try:
                result = await handler(**arguments)
                import json
                return [TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2),
                )]
            except Exception as e:
                logger.error(f"工具 {tool_name} 执行失败: {e}")
                return [TextContent(
                    type="text",
                    text=f"执行失败: {str(e)}",
                )]

    async def _handle_search_items(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        location: str | None = None,
        sort_by: str = "default",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """
        搜索闲鱼商品

        实现方式：
        1. 调用闲鱼内部 API（需要 cookie 认证）
        2. 或通过浏览器自动化（Playwright/Selenium）
        3. 当前版本：返回结构化的占位数据，接入时替换为真实 API 调用
        """
        logger.info(f"搜索闲鱼: keyword={keyword}, page_size={page_size}")

        # ================================================================
        # TODO: 替换为真实的闲鱼 API 调用
        # 闲鱼搜索 API 通常是: https://s.2.taobao.com/list/ 等
        # 需要处理反爬机制（cookie、签名、验证码等）
        #
        # 示例实现框架:
        #   async with httpx.AsyncClient() as client:
        #       resp = await client.get(
        #           "https://api.xianyu.xxx/search",
        #           params={"q": keyword, "page": page, ...},
        #           cookies=self._parse_cookie(),
        #           headers={"User-Agent": "..."},
        #       )
        #       return self._parse_response(resp.json())
        # ================================================================

        return {
            "items": [
                {
                    "xianyu_item_id": f"xy_{i:06d}",
                    "title": f"[占位数据] {keyword} - 第{i}条",
                    "price": 0.0,
                    "original_price": 0.0,
                    "condition": "good",
                    "seller_credit": 700,
                    "location": "北京",
                    "images": [],
                    "listing_url": f"https://www.goofish.com/item/{i}",
                    "listed_time": "2024-06-01T00:00:00",
                }
                for i in range(1, min(page_size + 1, 6))
            ],
            "total_count": page_size,
            "has_more": False,
            "page": page,
        }

    async def _handle_get_item_detail(self, item_id: str) -> dict[str, Any]:
        """获取闲鱼商品详情"""
        logger.info(f"获取商品详情: item_id={item_id}")

        # TODO: 实现真实 API 调用
        return {
            "item_id": item_id,
            "title": "[占位] 商品详情",
            "description": "商品描述内容...",
            "price": 0.0,
            "images": [],
            "seller": {"id": "unknown", "nickname": "卖家"},
            "views": 0,
            "wants": 0,
            "listed_time": "2024-06-01T00:00:00",
        }

    async def _handle_get_seller_info(self, seller_id: str) -> dict[str, Any]:
        """获取卖家信息"""
        logger.info(f"获取卖家信息: seller_id={seller_id}")

        # TODO: 实现真实 API 调用
        return {
            "seller_id": seller_id,
            "credit_score": 700,
            "ratings": {"good": 100, "neutral": 1, "bad": 0},
            "verified": True,
            "registered_days": 365,
        }

    async def run(self):
        """启动 MCP Server（stdio 模式）"""
        logger.info("闲鱼 MCP Server 启动中...")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )
