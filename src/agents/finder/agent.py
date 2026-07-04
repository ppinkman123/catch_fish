"""
Finder Agent — 闲鱼商品搜索
调用闲鱼 MCP Server 搜索并整理二手商品信息
"""
# import sys
# from pathlib import Path

# # 将项目根目录加入 Python 搜索路径
# # __file__ = src/agents/base.py → 需要上三层才能到项目根目录
# # ✅ 正确：到项目根目录
# sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))  # → D:\code\catch_fish\


import json
from datetime import datetime

from src.agents.base import BaseAgent
from src.agents.finder.prompts import FINDER_ANALYZE_PROMPT, FINDER_SYSTEM_PROMPT
from src.models.schemas import FinderResult, XianyuItemOut


class FinderAgent(BaseAgent):
    """闲鱼商品搜索 Agent"""

    agent_id = "finder"
    agent_name = "商品搜索Agent"

    def __init__(self, mcp_client=None):
        """
        Args:
            mcp_client: 闲鱼 MCP 客户端（可选，测试时可不传）
        """
        super().__init__()
        self.mcp = mcp_client

    def system_prompt(self) -> str:
        return FINDER_SYSTEM_PROMPT

    async def execute(
        self,
        product_name: str,
        budget_min: float | None = None,
        budget_max: float | None = None,
        condition: str = "all",
        location: str | None = None,
        max_results: int = 20,
    ) -> FinderResult:
        """
        执行商品搜索

        Args:
            product_name: 商品名称（如 "iPhone 15 Pro 256G"）
            budget_min: 最低预算
            budget_max: 最高预算
            condition: 成色偏好
            location: 地区筛选
            max_results: 最大结果数

        Returns:
            FinderResult: 整理后的商品列表
        """
        self.logger.info(f"开始搜索: {product_name}, 预算={budget_min}-{budget_max}")

        # Step 1: 通过 MCP 搜索闲鱼
        raw_items = await self._search_xianyu(
            keyword=product_name,
            min_price=budget_min,
            max_price=budget_max,
            location=location,
            page_size=min(max_results, 50),
        )

        # Step 2: 用 LLM 整理和清洗数据
        if raw_items:
            items = await self._normalize_results(
                keyword=product_name,
                raw_results=raw_items,
                budget_min=budget_min or 0,
                budget_max=budget_max or float("inf"),
            )
        else:
            # 没有 MCP 客户端时，返回模拟数据结构
            items = await self._fallback_search(product_name)

        total_count = len(items)

        self.logger.info(f"搜索完成: 找到 {total_count} 件商品")

        return FinderResult(
            items=items,
            total_count=total_count,
            search_keyword=product_name,
            searched_at=datetime.now(),
        )

    async def _search_xianyu(
        self,
        keyword: str,
        min_price: float | None = None,
        max_price: float | None = None,
        location: str | None = None,
        page_size: int = 20,
    ) -> list[dict]:
        """调用闲鱼 MCP 搜索接口"""
        if self.mcp is None:
            self.logger.warning("MCP 客户端未配置，使用模拟数据")
            return []

        try:
            result = await self.mcp.call_tool(
                "search_items",
                arguments={
                    "keyword": keyword,
                    "min_price": min_price,
                    "max_price": max_price,
                    "location": location,
                    "page_size": page_size,
                    "sort_by": "credit",  # 按信用排序
                },
            )
            return result.get("items", [])
        except Exception as e:
            self.logger.error(f"闲鱼搜索失败: {e}")
            return []

    async def _normalize_results(
        self,
        keyword: str,
        raw_results: list[dict],
        budget_min: float,
        budget_max: float,
    ) -> list[XianyuItemOut]:
        """用 LLM 规范化原始搜索结果"""
        self.logger.info(f"MCP 原始搜索结果 ({len(raw_results)} 条)")

        # 截断过大的数据，避免超出 LLM token 限制
        truncated = self._truncate_raw_results(raw_results, max_items=5)
        if len(truncated) < len(raw_results):
            self.logger.warning(f"原始数据过多，截断 {len(raw_results)} → {len(truncated)} 条")

        prompt = FINDER_ANALYZE_PROMPT.format(
            keyword=keyword,
            raw_results=json.dumps(truncated, ensure_ascii=False, indent=2),
            budget_min=budget_min,
            budget_max=budget_max,
        )

        self.logger.debug(f"LLM 规范化 prompt 长度: {len(prompt)} 字符")

        try:
            data = await self.ask_llm_json(
                user_message=prompt,
                system_prompt=self.system_prompt(),
                max_tokens=8192,  # 规范化多条商品需要较大输出
            )
            items = []
            for item in data.get("items", []):
                items.append(XianyuItemOut(
                    xianyu_item_id=item.get("xianyu_item_id"),
                    title=item.get("title", ""),
                    price=float(item.get("price", 0)),
                    original_price=item.get("original_price"),
                    condition=item.get("condition"),
                    seller_nickname=item.get("seller_nickname"),
                    seller_credit=item.get("seller_credit"),
                    location=item.get("location"),
                    tags=item.get("tags", []),
                    images=item.get("images", []),
                    listing_url=item.get("listing_url"),
                    listed_time=item.get("listed_time"),
                ))
            return items
        except Exception as e:
            self.logger.error(f"LLM 整理结果失败: {e}")
            return []

    @staticmethod
    def _truncate_raw_results(raw_results: list[dict], max_items: int = 10) -> list[dict]:
        """截断原始搜索结果，对每条只保留关键字段，避免 prompt 过大"""
        key_fields = {
            "xianyu_item_id", "title", "description", "price", "original_price",
            "tags", "images", "location", "seller_nickname", "seller_info",
            "listing_url", "listed_time",
        }
        trimmed = []
        for item in raw_results[:max_items]:
            entry = {}
            for k, v in item.items():
                if k in key_fields:
                    # 截断过长的字符串字段
                    if isinstance(v, str) and len(v) > 500:
                        entry[k] = v[:500] + "..."
                    elif isinstance(v, list) and len(v) > 10:
                        entry[k] = v[:10]
                    else:
                        entry[k] = v
            trimmed.append(entry)
        return trimmed

    async def _fallback_search(self, product_name: str) -> list[XianyuItemOut]:
        """无 MCP 时的模拟搜索（开发调试用）"""
        self.logger.info(f"使用模拟数据: {product_name}")

        # 让 LLM 生成合理的模拟数据用于开发测试
        prompt = f"""请为"{product_name}"生成5条合理的闲鱼二手商品模拟数据（用于开发测试）。
价格应该符合当前市场行情，包含不同的成色和价格区间。

请输出JSON格式：
{{"items": [
  {{"title": "...", "price": 数字, "condition": "成色", "seller_credit": 700-850,
    "location": "城市", "listing_url": "https://example.com/item/1"}}
]}}
"""
        try:
            data = await self.ask_llm_json(prompt, self.system_prompt())
            items = []
            for item in data.get("items", []):
                items.append(XianyuItemOut(
                    title=item.get("title", ""),
                    price=float(item.get("price", 0)),
                    condition=item.get("condition"),
                    seller_nickname=item.get("seller_nickname"),
                    seller_credit=item.get("seller_credit"),
                    location=item.get("location"),
                    tags=item.get("tags", []),
                    listing_url=item.get("listing_url"),
                ))
            return items
        except Exception:
            return []


if __name__ == '__main__':
    import asyncio
    import sys

    from src.config import settings
    from src.mcp.xianyu_server import XianyuMCPServer

    async def main():
        keyword = sys.argv[1] if len(sys.argv) > 1 else "iPhone 15"

        # ---- 有 Cookie → 真实搜索；无 Cookie → 模拟数据 ----
        cookie = settings.xianyu_cookie
        if cookie:
            mcp = XianyuMCPServer(cookie=cookie)
            print(f"[INFO] Cookie 已配置，使用真实闲鱼搜索")
        else:
            mcp = None
            print(f"[INFO] Cookie 未配置，使用 LLM 模拟数据")

        fa = FinderAgent(mcp_client=mcp)

        print(f"{'=' * 60}")
        print(f"FinderAgent 测试 — 搜索: {keyword}")
        print(f"MCP 客户端: {'已连接' if mcp else '模拟模式'}")
        print(f"{'=' * 60}\n")

        result = await fa.execute(product_name=keyword, max_results=1)

        print(f"\n搜索结果: 共 {result.total_count} 件商品\n")
        for i, item in enumerate(result.items, 1):
            print(f"  [{i}] {item.title}")
            print(f"      价格: ¥{item.price}  |  原价: ¥{item.original_price or 'N/A'}")
            print(f"      成色: {item.condition or '未知'}  |  信誉: {item.seller_credit or 'N/A'}")
            print(f"      卖家: {item.seller_nickname or '未知'}  |  位置: {item.location or '未知'}")
            if item.tags:
                print(f"      标签: {', '.join(item.tags)}")
            print()

    asyncio.run(main())