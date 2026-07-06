"""
Encyclopedia Agent — 商品百科信息采集
纯 LLM 方案：依靠模型训练数据提供新品规格、价格、口碑，无需爬虫
"""

from datetime import datetime

from src.agents.base import BaseAgent
from src.agents.encyclopedia.prompts import (
    ENCYCLOPEDIA_RESEARCH_PROMPT,
    ENCYCLOPEDIA_SYSTEM_PROMPT,
)
from src.models.schemas import ChannelPrice, EncyclopediaResult


class EncyclopediaAgent(BaseAgent):
    """商品百科信息采集 Agent（纯 LLM，无爬虫）"""

    agent_id = "encyclopedia"
    agent_name = "商品百科Agent"

    def system_prompt(self) -> str:
        return ENCYCLOPEDIA_SYSTEM_PROMPT

    async def execute(
        self,
        product_name: str,
        brand: str | None = None,
        model: str | None = None,
        specs: dict[str, str] | None = None,
    ) -> EncyclopediaResult:
        """
        执行商品百科信息采集

        Args:
            product_name: 商品名称
            brand: 品牌
            model: 型号
            specs: 规格参数

        Returns:
            EncyclopediaResult: 新品基准信息
        """
        self.logger.info(f"开始采集商品信息: {product_name}, 品牌={brand}, 型号={model}")

        # LLM 直接输出所有信息（价格、规格、上市时间、产地等）
        research_data = await self._research(
            product_name=product_name,
            brand=brand or "",
            model=model or "",
            specs=specs or {},
        )

        lowest = self._find_lowest(research_data.get("new_prices", []))

        self.logger.info(f"商品信息采集完成: {product_name}, 最低新品价={lowest}")

        return EncyclopediaResult(
            product_name=research_data.get("product_name", product_name),
            brand=research_data.get("brand", brand),
            model=research_data.get("model", model),
            specs=research_data.get("specs", specs or {}),
            origin=research_data.get("origin"),
            new_prices=[
                ChannelPrice(
                    channel=p.get("channel", "unknown"),
                    price=float(p.get("price") or 0),
                    url=p.get("url"),
                    in_stock=p.get("in_stock", True),
                )
                for p in research_data.get("new_prices", [])
            ],
            lowest_new_price=lowest,
            release_date=research_data.get("release_date"),
            rating=research_data.get("rating"),
            warranty=research_data.get("warranty"),
            source_urls=research_data.get("source_urls", []),
            fetched_at=datetime.now(),
        )

    async def _research(
        self,
        product_name: str,
        brand: str,
        model: str,
        specs: dict[str, str],
    ) -> dict:
        """LLM 直接输出商品研究结果"""
        prompt = ENCYCLOPEDIA_RESEARCH_PROMPT.format(
            product_name=product_name,
            brand=brand,
            model=model,
            specs=specs,
        )

        try:
            return await self.ask_llm_json(
                user_message=prompt,
                system_prompt=self.system_prompt(),
            )
        except Exception as e:
            self.logger.error(f"LLM 研究失败: {e}")
            return {
                "product_name": product_name,
                "brand": brand,
                "model": model,
                "specs": specs,
                "new_prices": [],
            }

    @staticmethod
    def _find_lowest(prices: list[dict]) -> float | None:
        """找出最低在售价格"""
        valid = [
            p.get("price") for p in prices
            if p.get("price") is not None
            and float(p.get("price")) > 0
            and p.get("in_stock", True)
        ]
        return min(valid) if valid else None


if __name__ == '__main__':
    import asyncio
    import sys

    async def main():
        keyword = sys.argv[1] if len(sys.argv) > 1 else "iPhone 15"

        ea = EncyclopediaAgent()

        print(f"{'=' * 60}")
        print(f"EncyclopediaAgent 测试 — 商品: {keyword}")
        print(f"{'=' * 60}\n")

        result = await ea.execute(product_name=keyword)

        print(f"商品: {result.product_name}")
        print(f"品牌: {result.brand or '未知'}  |  型号: {result.model or '未知'}")
        print(f"产地: {result.origin or '未知'}  |  上市: {result.release_date or '未知'}")
        print(f"评分: {result.rating or 'N/A'}  |  保修: {result.warranty or '未知'}")
        print(f"最低全新价: ¥{result.lowest_new_price or 'N/A'}")
        print(f"\n规格参数:")
        for k, v in result.specs.items():
            print(f"  {k}: {v}")
        print(f"\n各渠道价格:")
        for p in result.new_prices:
            print(f"  [{p.channel}] ¥{p.price}  {'缺货' if not p.in_stock else '有货'}  {p.url or ''}")
        print(f"\n参考链接:")
        for url in result.source_urls:
            print(f"  {url}")

    asyncio.run(main())