"""
Encyclopedia Agent — 商品百科信息采集
从多个数据源获取新品规格、价格、口碑信息
"""

from datetime import datetime

from src.agents.base import BaseAgent
from src.agents.encyclopedia.prompts import (
    ENCYCLOPEDIA_RESEARCH_PROMPT,
    ENCYCLOPEDIA_SYSTEM_PROMPT,
)
from src.agents.encyclopedia.scrapers import SCRAPERS
from src.models.schemas import ChannelPrice, EncyclopediaResult


class EncyclopediaAgent(BaseAgent):
    """商品百科信息采集 Agent"""

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

        # Step 1: 并行抓取各渠道价格
        prices = await self._fetch_prices(product_name)

        # Step 2: 用 LLM 整合和完善信息
        research_data = await self._research(
            product_name=product_name,
            brand=brand or "",
            model=model or "",
            specs=specs or {},
            scraped_prices=prices,
        )

        # Step 3: 计算最低全新价
        lowest = self._find_lowest(research_data.get("new_prices", []))

        self.logger.info(f"商品信息采集完成: {product_name}, 最低新品价={lowest}")

        return EncyclopediaResult(
            product_name=research_data.get("product_name", product_name),
            brand=research_data.get("brand", brand),
            model=research_data.get("model", model),
            specs=research_data.get("specs", specs or {}),
            new_prices=[
                ChannelPrice(
                    channel=p.get("channel", "unknown"),
                    price=p.get("price", 0),
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

    async def _fetch_prices(self, product_name: str) -> list[dict]:
        """从各渠道抓取价格"""
        results = []
        for name, scraper in SCRAPERS.items():
            try:
                data = await scraper.search(product_name)
                if data:
                    results.append(data)
                self.logger.debug(f"{name} 抓取完成: price={data.get('price')}")
            except Exception as e:
                self.logger.warning(f"{name} 抓取失败: {e}")
        return results

    async def _research(
        self,
        product_name: str,
        brand: str,
        model: str,
        specs: dict[str, str],
        scraped_prices: list[dict],
    ) -> dict:
        """用 LLM 进行深度商品研究"""
        prompt = ENCYCLOPEDIA_RESEARCH_PROMPT.format(
            product_name=product_name,
            brand=brand,
            model=model,
            specs=specs,
        )

        if scraped_prices:
            prompt += f"\n\n## 实时抓取数据（供参考）\n{scraped_prices}"

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
                "new_prices": scraped_prices,
                "lowest_new_price": None,
            }

    @staticmethod
    def _find_lowest(prices: list[dict]) -> float | None:
        """找出最低在售价格"""
        valid = [p.get("price") for p in prices if p.get("price") and p.get("in_stock", True)]
        return min(valid) if valid else None
