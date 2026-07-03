"""
闲鱼 MCP Server

基于 MCP (Model Context Protocol) 协议，将闲鱼平台能力封装为标准化工具，
供 Finder Agent 通过 A2A 协议调用。

实现方式：使用官方 mcp 包的 Server 类，通过 httpx 请求 Goofish 页面并解析 HTML。
"""

import json
import re
from typing import Any

import httpx
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

# Goofish 搜索基础 URL
GOOFISH_SEARCH_URL = "https://www.goofish.com/search"
# 默认请求头，模拟浏览器
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.goofish.com/",
}

# 排序参数映射
SORT_PARAMS: dict[str, str] = {
    "default": "_default",
    "price_asc": "price_asc",
    "price_desc": "price_desc",
    "newest": "time_desc",
    "credit_desc": "credit_desc",
}


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

    # ----------------------------------------------------------------
    # MCP 协议处理器
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # 工具处理器
    # ----------------------------------------------------------------

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

        通过 httpx 请求 Goofish 搜索页面，解析 HTML 获取商品列表。

        参数:
            keyword:    搜索关键词
            min_price:  最低价（元）
            max_price:  最高价（元）
            location:   所在地（如 "北京"、"上海"）
            sort_by:    排序方式（default/price_asc/price_desc/newest/credit_desc）
            page:       页码（从 1 开始）
            page_size:  每页条数
        """
        logger.info(f"搜索闲鱼: keyword={keyword}, page_size={page_size}")

        # 构建请求参数
        params: dict[str, str] = {
            "q": keyword,
            "page": str(page),
            "pageSize": str(page_size),
            "sort": SORT_PARAMS.get(sort_by, "_default"),
        }
        if min_price is not None:
            params["minPrice"] = str(min_price)
        if max_price is not None:
            params["maxPrice"] = str(max_price)
        if location:
            params["location"] = location

        # 构建 cookie 字典
        cookies = self._parse_cookie()

        try:
            async with httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                cookies=cookies,
                follow_redirects=True,
                timeout=15.0,
            ) as client:
                resp = await client.get(GOOFISH_SEARCH_URL, params=params)
                resp.raise_for_status()
                html = resp.text

            return self._parse_search_results(html, keyword, page, page_size)

        except httpx.HTTPStatusError as e:
            logger.error(f"搜索请求失败 (HTTP {e.response.status_code}): {e}")
            return self._empty_result(keyword, page, error=f"HTTP {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"搜索请求网络错误: {e}")
            return self._empty_result(keyword, page, error=f"网络错误: {e}")
        except Exception as e:
            logger.error(f"搜索解析失败: {e}")
            return self._empty_result(keyword, page, error=str(e))

    async def _handle_get_item_detail(self, item_id: str) -> dict[str, Any]:
        """获取闲鱼商品详情"""
        logger.info(f"获取商品详情: item_id={item_id}")

        # 商品详情页 URL
        item_url = f"https://www.goofish.com/item/{item_id}"
        api_url = f"https://www.goofish.com/api/item/detail"

        cookies = self._parse_cookie()

        try:
            async with httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                cookies=cookies,
                follow_redirects=True,
                timeout=15.0,
            ) as client:
                # 先尝试 JSON API
                resp = await client.get(
                    api_url,
                    params={"itemId": item_id},
                    headers={**DEFAULT_HEADERS, "Accept": "application/json"},
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                    data = resp.json()
                    return self._parse_item_detail_api(data, item_id)

                # 降级为 HTML 解析
                logger.info(f"API 接口不可用，降级为 HTML 解析: item_id={item_id}")
                resp = await client.get(item_url)
                resp.raise_for_status()
                return self._parse_item_detail_html(resp.text, item_id)

        except httpx.RequestError as e:
            logger.error(f"获取商品详情网络错误: {e}")
            return self._empty_detail(item_id, error=f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取商品详情失败: {e}")
            return self._empty_detail(item_id, error=str(e))

    async def _handle_get_seller_info(self, seller_id: str) -> dict[str, Any]:
        """获取卖家信息"""
        logger.info(f"获取卖家信息: seller_id={seller_id}")

        seller_url = f"https://www.goofish.com/seller/{seller_id}"
        api_url = f"https://www.goofish.com/api/seller/info"

        cookies = self._parse_cookie()

        try:
            async with httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                cookies=cookies,
                follow_redirects=True,
                timeout=15.0,
            ) as client:
                # 先尝试 JSON API
                resp = await client.get(
                    api_url,
                    params={"sellerId": seller_id},
                    headers={**DEFAULT_HEADERS, "Accept": "application/json"},
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                    data = resp.json()
                    return self._parse_seller_info_api(data, seller_id)

                # 降级为 HTML 解析
                logger.info(f"API 接口不可用，降级为 HTML 解析: seller_id={seller_id}")
                resp = await client.get(seller_url)
                resp.raise_for_status()
                return self._parse_seller_info_html(resp.text, seller_id)

        except httpx.RequestError as e:
            logger.error(f"获取卖家信息网络错误: {e}")
            return self._empty_seller_info(seller_id, error=f"网络错误: {e}")
        except Exception as e:
            logger.error(f"获取卖家信息失败: {e}")
            return self._empty_seller_info(seller_id, error=str(e))

    # ----------------------------------------------------------------
    # 搜索页面 HTML 解析
    # ----------------------------------------------------------------

    def _parse_search_results(
        self,
        html: str,
        keyword: str,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """解析 Goofish 搜索页面的 HTML，提取商品列表"""
        items: list[dict[str, Any]] = []
        total_count = 0
        has_more = False

        # ================================================================
        # Goofish 搜索页面的商品数据通常内嵌在 <script> 标签的
        # window.__INITIAL_STATE__ 或类似 JSON 结构中。
        # 下面提供两种提取策略：
        #   策略 A：从 __INITIAL_STATE__ JS 变量中提取 JSON
        #   策略 B：直接从 HTML DOM 结构中解析
        # ================================================================

        # ---- 策略 A: 从 __INITIAL_STATE__ 提取 ----
        try:
            match = re.search(
                r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>',
                html,
                re.DOTALL,
            )
            if match:
                state = json.loads(match.group(1))
                # 根据实际返回结构调整提取路径
                search_data = state.get("searchResult") or state.get("search") or state
                items_raw = (
                    search_data.get("items")
                    or search_data.get("itemList")
                    or search_data.get("list")
                    or []
                )
                total_count = search_data.get("totalCount") or search_data.get("total") or len(items_raw)
                has_more = search_data.get("hasMore", False)

                for i, raw in enumerate(items_raw[:page_size], start=1):
                    items.append({
                        "xianyu_item_id": raw.get("itemId") or raw.get("id") or f"unknown_{i:06d}",
                        "title": raw.get("title", ""),
                        "price": float(raw.get("price", raw.get("priceInt", 0))) / 100,
                        "original_price": float(raw.get("originalPrice", raw.get("originPrice", 0))) / 100,
                        "condition": raw.get("condition", "unknown"),
                        "seller_credit": int(raw.get("sellerCredit", raw.get("credit", 0))),
                        "location": raw.get("location", raw.get("city", "")),
                        "images": raw.get("images", raw.get("imgs", [])),
                        "listing_url": f"https://www.goofish.com/item/{raw.get('itemId', raw.get('id', ''))}",
                        "listed_time": raw.get("listedTime", raw.get("createTime", "")),
                    })

                logger.info(f"从 __INITIAL_STATE__ 解析到 {len(items)} 条商品")
                if items:
                    return {
                        "items": items,
                        "total_count": total_count,
                        "has_more": has_more,
                        "page": page,
                    }

        except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as e:
            logger.warning(f"__INITIAL_STATE__ 解析失败，尝试 HTML DOM 解析: {e}")

        # ---- 策略 B: HTML DOM 解析 ----
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
        except ImportError:
            logger.warning("BeautifulSoup 未安装，使用正则表达式降级解析")
            soup = None

        if soup:
            # 尝试多种可能的选择器来提取商品卡片
            card_selectors = [
                "div[class*='item-card']",
                "div[class*='card-item']",
                "div[class*='item']",
                "li[class*='item']",
                "a[class*='item']",
            ]
            cards = []
            for selector in card_selectors:
                cards = soup.select(selector)
                if cards:
                    break

            for i, card in enumerate(cards[:page_size], start=1):
                # 从卡片中提取字段（适配不同 HTML 结构）
                title_el = (
                    card.select_one("[class*='title']")
                    or card.select_one("h3")
                    or card.select_one("a[class*='title']")
                )
                price_el = card.select_one("[class*='price']")
                location_el = card.select_one("[class*='location']")
                link_el = card.select_one("a[href*='/item/']") or card.select_one("a[href*='goofish']")
                img_el = card.select_one("img")

                title = title_el.get_text(strip=True) if title_el else f"{keyword} - 第{i}条"
                price_text = price_el.get_text(strip=True) if price_el else "0"
                # 提取价格数字
                price_match = re.search(r"[\d.]+", price_text)
                price = float(price_match.group()) if price_match else 0.0
                location = location_el.get_text(strip=True) if location_el else "未知"

                href = link_el.get("href", "") if link_el else ""
                if href and not href.startswith("http"):
                    href = f"https://www.goofish.com{href}"
                item_id_match = re.search(r"/item/(\d+)", href)
                item_id = item_id_match.group(1) if item_id_match else f"dom_{i:06d}"

                img_src = img_el.get("src") or img_el.get("data-src", "") if img_el else ""

                items.append({
                    "xianyu_item_id": item_id,
                    "title": title,
                    "price": price,
                    "original_price": 0.0,
                    "condition": "unknown",
                    "seller_credit": 0,
                    "location": location,
                    "images": [img_src] if img_src else [],
                    "listing_url": href or f"https://www.goofish.com/item/{item_id}",
                    "listed_time": "",
                })

            logger.info(f"从 DOM 解析到 {len(items)} 条商品")

        # ---- 如果完全解析失败，返回空结果 ----
        if not items:
            logger.warning(f"搜索解析结果为空: keyword={keyword}")
            return self._empty_result(keyword, page)

        return {
            "items": items,
            "total_count": len(items),
            "has_more": len(items) >= page_size,
            "page": page,
        }

    def _parse_item_detail_html(self, html: str, item_id: str) -> dict[str, Any]:
        """从商品详情页 HTML 中解析详细信息"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
        except ImportError:
            soup = None

        result: dict[str, Any] = {
            "item_id": item_id,
            "title": "",
            "description": "",
            "price": 0.0,
            "original_price": 0.0,
            "images": [],
            "seller": {"id": "", "nickname": ""},
            "views": 0,
            "wants": 0,
            "listed_time": "",
            "condition": "unknown",
            "location": "",
        }

        # 尝试从 __INITIAL_STATE__ 提取完整 JSON
        try:
            match = re.search(
                r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>',
                html,
                re.DOTALL,
            )
            if match:
                state = json.loads(match.group(1))
                detail = state.get("itemDetail") or state.get("detail") or state.get("item") or {}
                if detail:
                    result.update({
                        "title": detail.get("title", ""),
                        "description": detail.get("description", detail.get("desc", "")),
                        "price": float(detail.get("price", 0)) / 100,
                        "original_price": float(detail.get("originalPrice", detail.get("originPrice", 0))) / 100,
                        "images": detail.get("images", detail.get("imgs", [])),
                        "seller": {
                            "id": detail.get("sellerId", detail.get("userId", "")),
                            "nickname": detail.get("sellerNick", detail.get("nick", "")),
                        },
                        "views": int(detail.get("views", detail.get("viewCount", 0))),
                        "wants": int(detail.get("wants", detail.get("wantCount", 0))),
                        "listed_time": detail.get("listedTime", detail.get("createTime", "")),
                        "condition": detail.get("condition", "unknown"),
                        "location": detail.get("location", detail.get("city", "")),
                    })
                    return result
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"详情页 __INITIAL_STATE__ 解析失败: {e}")

        # DOM 解析降级
        if soup:
            title_el = (
                soup.select_one("[class*='title'] h1")
                or soup.select_one("h1")
                or soup.select_one("[class*='title']")
            )
            if title_el:
                result["title"] = title_el.get_text(strip=True)

            price_el = soup.select_one("[class*='price']")
            if price_el:
                m = re.search(r"[\d.]+", price_el.get_text(strip=True))
                if m:
                    result["price"] = float(m.group())

            desc_el = soup.select_one("[class*='description']") or soup.select_one("[class*='desc']")
            if desc_el:
                result["description"] = desc_el.get_text(strip=True)

            seller_el = soup.select_one("[class*='seller']") or soup.select_one("[class*='shop']")
            if seller_el:
                result["seller"]["nickname"] = seller_el.get_text(strip=True)

            img_els = soup.select("img[class*='detail']") or soup.select("[class*='gallery'] img") or soup.select("img")
            result["images"] = [
                img.get("src") or img.get("data-src", "")
                for img in img_els[:10]
                if img.get("src") or img.get("data-src")
            ]

        return result

    def _parse_seller_info_html(self, html: str, seller_id: str) -> dict[str, Any]:
        """从卖家页面 HTML 中解析信息"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
        except ImportError:
            soup = None

        result: dict[str, Any] = {
            "seller_id": seller_id,
            "nickname": "",
            "credit_score": 0,
            "ratings": {"good": 0, "neutral": 0, "bad": 0},
            "verified": False,
            "registered_days": 0,
        }

        # 尝试 JSON 数据提取
        try:
            match = re.search(
                r'<script[^>]*>window\.__INITIAL_STATE__\s*=\s*({.*?});?\s*</script>',
                html,
                re.DOTALL,
            )
            if match:
                state = json.loads(match.group(1))
                seller = state.get("sellerInfo") or state.get("seller") or state.get("user") or {}
                if seller:
                    result.update({
                        "nickname": seller.get("nick", seller.get("nickname", "")),
                        "credit_score": int(seller.get("creditScore", seller.get("creditScore", 0))),
                        "ratings": {
                            "good": int(seller.get("goodRatings", 0)),
                            "neutral": int(seller.get("neutralRatings", 0)),
                            "bad": int(seller.get("badRatings", 0)),
                        },
                        "verified": bool(seller.get("verified", False)),
                        "registered_days": int(seller.get("registeredDays", seller.get("createDays", 0))),
                    })
                    return result
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"卖家页 __INITIAL_STATE__ 解析失败: {e}")

        # DOM 解析降级
        if soup:
            name_el = soup.select_one("[class*='name']") or soup.select_one("[class*='nick']")
            if name_el:
                result["nickname"] = name_el.get_text(strip=True)

            score_el = soup.select_one("[class*='credit']") or soup.select_one("[class*='score']")
            if score_el:
                m = re.search(r"\d+", score_el.get_text(strip=True))
                if m:
                    result["credit_score"] = int(m.group())

            # 认证标记
            verified_el = soup.select_one("[class*='verified']") or soup.select_one("[class*='authenticated']")
            result["verified"] = verified_el is not None

        return result

    # ----------------------------------------------------------------
    # API JSON 解析（如果 Goofish 提供了 JSON API）
    # ----------------------------------------------------------------

    def _parse_item_detail_api(self, data: dict[str, Any], item_id: str) -> dict[str, Any]:
        """解析商品详情 API 的 JSON 响应"""
        d = data.get("data") or data.get("result") or data
        return {
            "item_id": item_id,
            "title": d.get("title", ""),
            "description": d.get("description", d.get("desc", "")),
            "price": float(d.get("price", 0)) / 100,
            "original_price": float(d.get("originalPrice", d.get("originPrice", 0))) / 100,
            "images": d.get("images", d.get("imgs", [])),
            "seller": {
                "id": d.get("sellerId", d.get("userId", "")),
                "nickname": d.get("sellerNick", d.get("nick", "")),
            },
            "views": int(d.get("views", d.get("viewCount", 0))),
            "wants": int(d.get("wants", d.get("wantCount", 0))),
            "listed_time": d.get("listedTime", d.get("createTime", "")),
            "condition": d.get("condition", "unknown"),
            "location": d.get("location", d.get("city", "")),
        }

    def _parse_seller_info_api(self, data: dict[str, Any], seller_id: str) -> dict[str, Any]:
        """解析卖家信息 API 的 JSON 响应"""
        d = data.get("data") or data.get("result") or data
        return {
            "seller_id": seller_id,
            "nickname": d.get("nick", d.get("nickname", "")),
            "credit_score": int(d.get("creditScore", d.get("creditScore", 0))),
            "ratings": {
                "good": int(d.get("goodRatings", 0)),
                "neutral": int(d.get("neutralRatings", 0)),
                "bad": int(d.get("badRatings", 0)),
            },
            "verified": bool(d.get("verified", False)),
            "registered_days": int(d.get("registeredDays", d.get("createDays", 0))),
        }

    # ----------------------------------------------------------------
    # 辅助方法
    # ----------------------------------------------------------------

    def _parse_cookie(self) -> dict[str, str]:
        """将 cookie 字符串解析为字典"""
        if not self.cookie:
            return {}
        cookies: dict[str, str] = {}
        for part in self.cookie.split(";"):
            part = part.strip()
            if "=" in part:
                key, value = part.split("=", 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def _empty_result(self, keyword: str, page: int, error: str = "") -> dict[str, Any]:
        """返回空搜索结果"""
        result: dict[str, Any] = {
            "items": [],
            "total_count": 0,
            "has_more": False,
            "page": page,
        }
        if error:
            result["error"] = error
        return result

    def _empty_detail(self, item_id: str, error: str = "") -> dict[str, Any]:
        """返回空商品详情"""
        result: dict[str, Any] = {
            "item_id": item_id,
            "title": "",
            "description": "",
            "price": 0.0,
            "images": [],
            "seller": {"id": "", "nickname": ""},
            "views": 0,
            "wants": 0,
            "listed_time": "",
        }
        if error:
            result["error"] = error
        return result

    def _empty_seller_info(self, seller_id: str, error: str = "") -> dict[str, Any]:
        """返回空卖家信息"""
        result: dict[str, Any] = {
            "seller_id": seller_id,
            "credit_score": 0,
            "ratings": {"good": 0, "neutral": 0, "bad": 0},
            "verified": False,
            "registered_days": 0,
        }
        if error:
            result["error"] = error
        return result

    # ----------------------------------------------------------------
    # Server 启动
    # ----------------------------------------------------------------

    async def run(self):
        """启动 MCP Server（stdio 模式）"""
        logger.info("闲鱼 MCP Server 启动中...")
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )


if __name__ == '__main__':
    import asyncio

    async def main():
        server = XianyuMCPServer()
        result = await server._handle_search_items(keyword="iPhone 15 Pro")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())