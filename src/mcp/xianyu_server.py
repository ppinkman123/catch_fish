"""
闲鱼 MCP Server

基于 MCP (Model Context Protocol) 协议，将闲鱼平台能力封装为标准化工具，
供 Finder Agent 通过 A2A 协议调用。

实现方式：逆向闲鱼 MTOP API 签名算法，直接请求后端 JSON 接口。
"""
# import sys
# from pathlib import Path

# # 将项目根目录加入 Python 搜索路径，支持直接 `python src/mcp/xianyu_server.py` 运行
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


import hashlib
import json
import re
import time
import traceback
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

# ============================================================
# 常量
# ============================================================
APP_KEY = "34839810"
MTOP_BASE = "https://h5api.m.goofish.com/h5"

# MTOP 接口路径
MTOP_SEARCH = f"{MTOP_BASE}/mtop.taobao.idlemtopsearch.pc.search/1.0/"
MTOP_ITEM_DETAIL = f"{MTOP_BASE}/mtop.taobao.idle.item.pc.detail/1.0/"
MTOP_SELLER_CREDIT = f"{MTOP_BASE}/mtop.taobao.idle.user.credit.query/1.0/"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh;q=0.9",
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


# ============================================================
# 签名工具函数（来自 xianyu_monitor.py 方案）
# ============================================================

def _extract_token(cookie_str: str) -> str | None:
    """从 Cookie 中提取 MTOP 签名 token（_m_h5_tk 前 32 位）"""
    parts = cookie_str.replace("; ", ";").split(";")
    for part in parts:
        part = part.strip()
        if part.startswith("_m_h5_tk="):
            token = part.split("=", 1)[1].split("_")[0]
            if token:
                return token
    return None


def _make_sign(token: str, timestamp_ms: int, data_json: str) -> str:
    """生成闲鱼 MTOP MD5 签名"""
    raw = f"{token}&{timestamp_ms}&{APP_KEY}&{data_json}"
    return hashlib.md5(raw.encode()).hexdigest()


def _utc_timestamp_ms() -> int:
    """返回当前 UTC 毫秒时间戳"""
    return int(time.time() * 1000)


# ============================================================
# MCP Server
# ============================================================

class XianyuMCPServer:
    """
    闲鱼 MCP Server

    提供三个核心工具：
    1. search_items    — 搜索闲鱼商品列表（MTOP API + 签名）
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
            return get_tool_definitions()

        @self.server.call_tool()
        async def call_tool(request: CallToolRequest) -> list[TextContent]:
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

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """
        便捷调用工具（无需 MCP 协议包装）

        Args:
            tool_name: 工具名，如 search_items / get_item_detail / get_seller_info
            arguments: 工具参数

        Returns:
            工具执行结果 dict
        """
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            raise ValueError(f"未知工具: {tool_name}")
        return await handler(**(arguments or {}))

    # ----------------------------------------------------------------
    # 通用 MTOP API 调用
    # ----------------------------------------------------------------

    async def _call_mtop_api(
        self,
        url: str,
        body: dict[str, Any],
        api_name: str,
        client: httpx.AsyncClient | None = None,
        cookie_str: str | None = None,
    ) -> dict[str, Any] | None:
        """
        调用闲鱼 MTOP 接口，自动处理签名。

        参数:
            url:        MTOP 接口完整 URL
            body:       请求体（JSON 对象）
            api_name:   MTOP API 名称（用于 params 中的 api 字段）
            client:     可复用的 httpx.AsyncClient
            cookie_str: Cookie 字符串

        返回:
            JSON 响应 dict，失败返回 None
        """
        cookie = cookie_str or self.cookie
        token = _extract_token(cookie)
        if not token:
            logger.error("Cookie 中找不到 _m_h5_tk，请更新 .env 中的 XIANYU_COOKIE")
            return None

        data_json = json.dumps(body, separators=(",", ":"))
        ts = _utc_timestamp_ms()
        sign = _make_sign(token, ts, data_json)

        # ---- 调试：打印签名关键信息 ----
        # logger.info(f"[调试] 提取的 token: {token}")
        # logger.info(f"[调试] 时间戳(ms): {ts}")
        # logger.info(f"[调试] 数据体: {data_json}")
        # logger.info(f"[调试] 签名串: {token}&{ts}&{APP_KEY}&{data_json}")
        # logger.info(f"[调试] MD5 签名: {sign}")
        # logger.info(f"[调试] Cookie 前 120 字符: {cookie[:120]}")
        # logger.info(f"[调试] _m_h5_tk 完整值: {[p for p in cookie.split(';') if '_m_h5_tk' in p]}")

        params = {
            "jsv": "2.7.2",
            "appKey": APP_KEY,
            "t": str(ts),
            "sign": sign,
            "v": "1.0",
            "type": "originaljson",
            "dataType": "json",
            "api": api_name,
            "data": data_json,
        }

        headers = {**DEFAULT_HEADERS, "Cookie": cookie}

        async def _do_request(clt: httpx.AsyncClient) -> dict[str, Any] | None:
            try:
                resp = await clt.get(url, params=params, headers=headers, timeout=15.0)
                logger.info(f"[调试] HTTP 状态: {resp.status_code}, 响应长度: {len(resp.text)}")
                logger.info(f"[调试] 完整响应: {resp.text[:1000]}")
                data = resp.json()

                # 检测 MTOP 网关错误：格式1 - 顶层 list 如 ["FAIL_xxx::reason"]
                if isinstance(data, list) and len(data) > 0:
                    first = data[0]
                    if isinstance(first, str) and first.startswith("FAIL_"):
                        logger.error(f"MTOP 网关拒绝: {first}")
                        return None

                # 检测 MTOP 网关错误：格式2 - dict.ret 如 {"ret": ["FAIL_xxx::reason"]}
                if isinstance(data, dict):
                    ret = data.get("ret", [])
                    if isinstance(ret, list) and len(ret) > 0:
                        first_ret = ret[0]
                        if isinstance(first_ret, str) and first_ret.startswith("FAIL_"):
                            logger.error(f"MTOP 网关拒绝: {first_ret}")
                            return None

                return data
            except Exception as e:
                logger.error(f"MTOP 请求失败: {type(e).__name__}: {e}")
                logger.error(f"详细堆栈:\n{traceback.format_exc()}")
                return None

        if client is not None:
            return await _do_request(client)
        else:
            async with httpx.AsyncClient(timeout=15.0) as clt:
                return await _do_request(clt)

    # ----------------------------------------------------------------
    # 工具处理器：search_items
    # ----------------------------------------------------------------

    async def _handle_search_items(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        location: str | None = None,
        sort_by: str = "default",
        page: int = 1,
        page_size: int = 1,
    ) -> dict[str, Any]:
        """
        搜索闲鱼商品（MTOP API）

        参数:
            keyword:    搜索关键词
            min_price:  最低价（元）
            max_price:  最高价（元）
            location:   所在地
            sort_by:    排序方式
            page:       页码
            page_size:  每页条数
        """
        logger.info(f"搜索闲鱼: keyword={keyword}, page={page}, page_size={page_size}")

        # 构建 MTOP 请求体
        body: dict[str, Any] = {
            "pageNumber": page,
            "keyword": keyword,
            "rowsPerPage": page_size,
            "fromFilter": False,
            "sortValue": SORT_PARAMS.get(sort_by, "_default"),
            "searchReqFromPage": "pcSearch",
        }

        if min_price is not None:
            body["startPrice"] = str(min_price)
        if max_price is not None:
            body["endPrice"] = str(max_price)
        if location:
            body["localCity"] = location

        # --- 策略 A: MTOP API ---
        logger.info("尝试 MTOP API 搜索...")
        result = await self._call_mtop_api(
            url=MTOP_SEARCH,
            body=body,
            api_name="mtop.taobao.idlemtopsearch.pc.search",
        )

        if result:
            items = self._parse_mtop_search_result(result, page_size)
            if items is not None:
                logger.info(f"MTOP API 搜索成功: {len(items)} 条")
                return {
                    "items": items,
                    "total_count": result.get("data", {}).get("totalCount",
                               result.get("data", {}).get("total", len(items))),
                    "has_more": len(items) >= page_size,
                    "page": page,
                }

        logger.error("MTOP API 搜索失败")
        return {"items": [], "total_count": 0, "has_more": False, "page": page, "error": "MTOP API 调用失败"}

    def _parse_mtop_search_result(
        self, result: dict, page_size: int
    ) -> list[dict[str, Any]] | None:
        """解析 MTOP 搜索接口返回的 JSON —— 原样提取，不做二次加工"""
        data = result.get("data", {})
        if not data or not isinstance(data, dict):
            return None

        items_raw = (
            data.get("resultList")
            or data.get("itemsArray")
            or data.get("items")
            or []
        )

        if not items_raw:
            return []

        parsed = []
        for raw in items_raw[:page_size]:
            if not isinstance(raw, dict):
                continue

            try:
                main = raw["data"]["item"]["main"]
            except (KeyError, TypeError):
                continue

            args: dict[str, Any] = main.get("clickParam", {}).get("args", {})
            ex: dict[str, Any] = main.get("exContent", {}) if isinstance(main.get("exContent"), dict) else {}
            dp: dict[str, Any] = ex.get("detailParams", {}) if isinstance(ex, dict) else {}

            item_id = str(args.get("id") or args.get("itemId") or dp.get("itemId", ""))
            title = str(main.get("title", "") or dp.get("title", ""))
            dp_title = str(dp.get("title", ""))
            # 只有 detailParams.title 比 main.title 有更多信息时才保留
            description = dp_title if len(dp_title) > len(title) else ""

            # 价格
            price_str = args.get("displayPrice") or args.get("price") or dp.get("soldPrice") or "0"
            try:
                price = float(price_str)
            except (ValueError, TypeError):
                price = 0.0

            # 原价（可能没有）
            ori = main.get("oriPrice", "")
            original_price = 0.0
            if ori:
                m = re.search(r"[\d.]+", str(ori).replace("¥", ""))
                if m:
                    original_price = float(m.group())

            # 图片
            pic = str(main.get("picUrl", ""))
            images = [pic.replace("http://", "https://")] if pic else []

            # 地区
            location = str(ex.get("area", "") or args.get("p_city", ""))

            # 卖家
            seller_nick = str(main.get("userNickName", "") or dp.get("userNick", ""))
            seller_id = str(args.get("seller_id", ""))

            # 发布时间
            listed_time = str(args.get("publishTime", ""))

            # --- 直接搬运 MTOP 自带的标签，不做加工 ---
            # fishTags 在 main.exContent.fishTags（少数在 main.fishTags）
            tags: list[str] = []
            fish_tags = ex.get("fishTags") or main.get("fishTags") or {}
            for group in fish_tags.values():
                if not isinstance(group, dict):
                    continue
                for tl in group.get("tagList", []):
                    c = tl.get("data", {}).get("content", "")
                    if c:
                        tags.append(str(c))

            # 卖家身份 + 店铺数据
            seller_info: dict[str, str] = {}
            identity = str(main.get("userIdentityShow", ""))
            if identity:
                seller_info["identity"] = identity
            shop_label = main.get("userFishShopLabel") or ex.get("userFishShopLabel") or {}
            for tl in shop_label.get("tagList", []):
                c = tl.get("data", {}).get("content", "")
                if c:
                    seller_info["stat"] = c  # e.g. "781条评价" "好评率97%"

            parsed.append({
                "xianyu_item_id": item_id,
                "title": title,
                "description": description,
                "price": price,
                "original_price": original_price,
                "tags": tags,
                "images": images,
                "location": location,
                "seller_nickname": seller_nick,
                "seller_id": seller_id,
                "seller_info": seller_info,
                "listing_url": f"https://www.goofish.com/item/{item_id}",
                "listed_time": listed_time,
            })

        return parsed

    # ----------------------------------------------------------------
    # 工具处理器：get_item_detail
    # ----------------------------------------------------------------

    async def _handle_get_item_detail(self, item_id: str) -> dict[str, Any]:
        """获取闲鱼商品详情"""
        logger.info(f"获取商品详情: item_id={item_id}")

        # --- 策略 A: MTOP API ---
        logger.info("尝试 MTOP API 获取详情...")
        result = await self._call_mtop_api(
            url=MTOP_ITEM_DETAIL,
            body={"itemId": item_id},
            api_name="mtop.taobao.idle.item.pc.detail",
        )
        if result:
            detail = self._parse_mtop_detail_result(result, item_id)
            if detail and detail.get("title"):
                logger.info(f"MTOP API 详情获取成功: {detail['title'][:30]}")
                return detail

        logger.error("MTOP API 获取商品详情失败")
        return {"item_id": item_id, "title": "", "description": "", "price": 0.0,
                "images": [], "seller": {"id": "", "nickname": ""},
                "views": 0, "wants": 0, "listed_time": "",
                "error": "MTOP API 调用失败"}

    def _parse_mtop_detail_result(self, result: dict, item_id: str) -> dict[str, Any] | None:
        """解析 MTOP 商品详情接口返回"""
        data = result.get("data", {})
        if not data or not isinstance(data, dict):
            return None

        # 可能嵌套在 result / item 等字段中
        detail = data.get("result") or data.get("item") or data

        price_raw = detail.get("price", 0)
        try:
            price = float(price_raw) / 100
        except (ValueError, TypeError):
            price = float(price_raw) if price_raw else 0.0

        return {
            "item_id": item_id,
            "title": detail.get("title", ""),
            "description": detail.get("description", detail.get("desc", "")),
            "price": price,
            "original_price": float(detail.get("originalPrice", detail.get("originPrice", 0))) / 100,
            "images": detail.get("images", detail.get("imgs", [])),
            "seller": {
                "id": str(detail.get("sellerId", detail.get("userId", ""))),
                "nickname": detail.get("sellerNick", detail.get("nick", "")),
            },
            "views": int(detail.get("views", detail.get("viewCount", 0))),
            "wants": int(detail.get("wants", detail.get("wantCount", 0))),
            "listed_time": detail.get("gmtCreate", detail.get("publishTime", "")),
            "condition": detail.get("condition", "unknown"),
            "location": detail.get("location", detail.get("city", "")),
        }

    # ----------------------------------------------------------------
    # 工具处理器：get_seller_info
    # ----------------------------------------------------------------

    async def _handle_get_seller_info(self, seller_id: str) -> dict[str, Any]:
        """获取卖家信息"""
        logger.info(f"获取卖家信息: seller_id={seller_id}")

        # --- 策略 A: MTOP API ---
        logger.info("尝试 MTOP API 获取卖家信息...")
        result = await self._call_mtop_api(
            url=MTOP_SELLER_CREDIT,
            body={"userId": seller_id},
            api_name="mtop.taobao.idle.user.credit.query",
        )
        if result:
            info = self._parse_mtop_seller_result(result, seller_id)
            if info and info.get("nickname"):
                logger.info(f"MTOP API 卖家信息获取成功: {info['nickname']}")
                return info

        logger.error("MTOP API 获取卖家信息失败")
        return {"seller_id": seller_id, "nickname": "",
                "credit_score": 0, "ratings": {"good": 0, "neutral": 0, "bad": 0},
                "verified": False, "registered_days": 0,
                "error": "MTOP API 调用失败"}

    def _parse_mtop_seller_result(self, result: dict, seller_id: str) -> dict[str, Any] | None:
        """解析 MTOP 卖家信息接口返回"""
        data = result.get("data", {})
        if not data or not isinstance(data, dict):
            return None

        seller = data.get("result") or data.get("seller") or data.get("user") or data

        return {
            "seller_id": seller_id,
            "nickname": seller.get("nick", seller.get("nickname", "")),
            "credit_score": int(seller.get("creditScore", 0)),
            "ratings": {
                "good": int(seller.get("goodRatings", 0)),
                "neutral": int(seller.get("neutralRatings", 0)),
                "bad": int(seller.get("badRatings", 0)),
            },
            "verified": bool(seller.get("verified", False)),
            "registered_days": int(seller.get("registeredDays", seller.get("createDays", 0))),
        }

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

    import sys
    from src.config import settings

    async def main():
        cookie = sys.argv[2] if len(sys.argv) > 2 else settings.xianyu_cookie

        # ---- 排查代码（需时取消注释） ----
        # import os; from pathlib import Path
        # env_path = Path(os.getcwd()) / ".env"
        # logger.info(f"[排查] CWD={os.getcwd()}, .env存在={env_path.exists()}")
        # logger.info(f"[排查] settings加载的cookie前150字符: {cookie[:150]}")
        # if env_path.exists():
        #     raw = env_path.read_text(encoding="utf-8")
        #     for line in raw.splitlines():
        #         if "XIANYU_COOKIE" in line:
        #             logger.info(f"[排查] .env原始行前200字符: {line[:200]}")

        # ---- 测试 MCP 注册 ----
        server = XianyuMCPServer(cookie=cookie)


        # ---- 可选：实际搜索测试 ----
        keyword = sys.argv[1] if len(sys.argv) > 1 else "劳力士"
        print(f"{'=' * 60}")
        print(f"搜索关键词: {keyword}")
        print(f"Cookie 状态: {'已配置 (MTOP API)' if cookie else '未配置 (缺少 Cookie)'}")
        print(f"{'=' * 60}\n")

        result = await server._handle_search_items(keyword=keyword)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())
