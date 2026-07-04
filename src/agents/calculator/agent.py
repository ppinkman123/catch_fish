"""
Calculator Agent — 性价比计算引擎
综合规则引擎 + LLM 判断，输出购买建议
"""

from src.agents.base import BaseAgent
from src.agents.calculator.prompts import (
    CALCULATOR_ANALYZE_PROMPT,
    CALCULATOR_SYSTEM_PROMPT,
)
from src.agents.calculator.scoring import (
    calc_comprehensive_score,
    normalize_condition,
)
from src.models.schemas import (
    CalculatorResult,
    ChannelPrice,
    EncyclopediaResult,
    FinderResult,
    MarketSummary,
    Recommendation,
)


class CalculatorAgent(BaseAgent):
    """性价比分析计算 Agent"""

    agent_id = "calculator"
    agent_name = "性价比计算Agent"

    def system_prompt(self) -> str:
        return CALCULATOR_SYSTEM_PROMPT

    async def execute(
        self,
        finder_result: FinderResult,
        encyclopedia_result: EncyclopediaResult,
    ) -> CalculatorResult:
        """
        执行性价比分析

        Args:
            finder_result: 闲鱼搜索的二手商品列表
            encyclopedia_result: 新品基准信息

        Returns:
            CalculatorResult: 性价比分析报告
        """
        self.logger.info(
            f"开始性价比分析: {encyclopedia_result.product_name}, "
            f"二手商品={len(finder_result.items)}件, "
            f"新品最低价={encyclopedia_result.lowest_new_price}"
        )

        new_price = encyclopedia_result.lowest_new_price or 0
        if new_price == 0:
            self.logger.warning("新品价格缺失，使用估算值")
            new_price = self._estimate_new_price(finder_result)

        # Step 1: 规则引擎预评分（对每个二手商品）
        rule_scores = []
        for item in finder_result.items:
            condition = item.condition or "good"
            score_data = calc_comprehensive_score(
                used_price=item.price,
                new_price=new_price,
                condition=normalize_condition(condition),
                seller_credit=item.seller_credit,
                total_listings=finder_result.total_count,
                release_date=encyclopedia_result.release_date,
            )
            rule_scores.append({
                "item": item,
                "score_data": score_data,
            })

        # Step 2: 按规则引擎分数排序
        rule_scores.sort(key=lambda x: x["score_data"]["score"], reverse=True)

        # Step 3: 用 LLM 做最终的深度分析
        if finder_result.items:
            llm_analysis = await self._llm_analyze(
                product_name=encyclopedia_result.product_name,
                new_price=new_price,
                encyclopedia_result=encyclopedia_result,
                finder_result=finder_result,
                rule_scores=rule_scores,
            )
        else:
            llm_analysis = self._empty_analysis(encyclopedia_result)

        # Step 4: 构建最佳推荐
        best_deal = None
        if rule_scores:
            best = rule_scores[0]
            best_deal = Recommendation(
                title=best["item"].title,
                price=best["item"].price,
                new_price=new_price,
                discount_rate=best["score_data"]["discount_rate"],
                score=best["score_data"]["score"],
                reason=f"综合评分{best['score_data']['score']}分",
                listing_url=best["item"].listing_url,
                condition=best["item"].condition,
            )

        # Step 5: 构建推荐列表（评分 ≥ 60 的前 5 个）
        recommendations = []
        for rs in rule_scores[:5]:
            if rs["score_data"]["score"] >= 60:
                recommendations.append(Recommendation(
                    title=rs["item"].title,
                    price=rs["item"].price,
                    new_price=new_price,
                    discount_rate=rs["score_data"]["discount_rate"],
                    score=rs["score_data"]["score"],
                    reason=rs["score_data"]["verdict_short"],
                    listing_url=rs["item"].listing_url,
                    condition=rs["item"].condition,
                ))

        # 市场总结
        prices = [item.price for item in finder_result.items]
        avg_price = sum(prices) / len(prices) if prices else 0

        rec = self._determine_recommendation(rule_scores, new_price)

        market_summary = MarketSummary(
            avg_used_price=round(avg_price, 2),
            price_range={"min": min(prices) if prices else 0, "max": max(prices) if prices else 0},
            total_listings=finder_result.total_count,
            recommendation=rec,
        )

        # 新品基线
        baseline = ChannelPrice(
            channel=encyclopedia_result.new_prices[0].channel if encyclopedia_result.new_prices else "unknown",
            price=new_price,
        )

        self.logger.info(
            f"性价比分析完成: 最佳={best_deal.score if best_deal else 'N/A'}分, "
            f"建议={rec}"
        )

        return CalculatorResult(
            best_deal=best_deal,
            recommendations=recommendations,
            new_product_baseline=baseline,
            market_summary=market_summary,
            verdict=llm_analysis.get("verdict", "分析完成"),
        )

    async def _llm_analyze(
        self,
        product_name: str,
        new_price: float,
        encyclopedia_result: EncyclopediaResult,
        finder_result: FinderResult,
        rule_scores: list[dict],
    ) -> dict:
        """用 LLM 进行深度分析"""

        # 提取各渠道价格
        jd_price = "未知"
        tmall_price = "未知"
        official_price = "未知"
        pdd_price = "未知"
        for p in encyclopedia_result.new_prices:
            if p.channel == "jd":
                jd_price = str(p.price)
            elif p.channel == "tmall":
                tmall_price = str(p.price)
            elif p.channel == "official":
                official_price = str(p.price)
            elif p.channel == "pdd":
                pdd_price = str(p.price)

        # 推断品类（从商品名称和规格推断）
        category = self._guess_category(product_name, encyclopedia_result)

        # 构建二手商品摘要（取 TOP 10）
        items_text = ""
        for i, rs in enumerate(rule_scores[:10], 1):
            item = rs["item"]
            sd = rs["score_data"]
            items_text += (
                f"{i}. {item.title} | 价格:¥{item.price} | "
                f"成色:{item.condition or '未知'} | "
                f"卖家:{item.seller_nickname or '未知'} | "
                f"折扣率:{sd['discount_rate']:.0%} | "
                f"规则评分:{sd['score']}/100\n"
            )

        prompt = CALCULATOR_ANALYZE_PROMPT.format(
            product_name=product_name,
            category=category,
            jd_price=jd_price,
            tmall_price=tmall_price,
            pdd_price=pdd_price,
            official_price=official_price,
            new_price=new_price,
            release_date=encyclopedia_result.release_date or "未知",
            origin=encyclopedia_result.origin or "未知",
            warranty=encyclopedia_result.warranty or "标准保修",
            used_items=items_text or "（暂无可用二手商品数据）",
        )

        try:
            return await self.ask_llm_json(
                user_message=prompt,
                system_prompt=self.system_prompt(),
            )
        except Exception as e:
            self.logger.error(f"LLM 分析失败: {e}")
            return {"verdict": "分析服务暂时不可用，请参考规则引擎评分结果。"}

    @staticmethod
    def _guess_category(product_name: str, encyclopedia: EncyclopediaResult) -> str:
        """根据商品名称和规格推断品类"""
        name_lower = product_name.lower()
        specs_keys = " ".join(encyclopedia.specs.keys()).lower()

        watch_keywords = ["表", "watch", "rolex", "劳力士", "卡西欧", "欧米茄", "浪琴", "天梭", "seiko"]
        clothing_keywords = ["衣", "服", "裤", "裙", "鞋", "t恤", "卫衣", "夹克", "衬衫", "nike", "adidas"]
        bag_keywords = ["包", "bag", "lv", "gucci", "chanel", "hermes", "爱马仕", "香奈儿"]
        digital_keywords = ["手机", "iphone", "ipad", "macbook", "电脑", "笔记本", "显卡", "cpu",
                           "耳机", "相机", "镜头", "平板", "手表智能", "apple watch"]

        if any(w in name_lower or w in specs_keys for w in watch_keywords):
            return "手表"
        elif any(w in name_lower for w in clothing_keywords):
            return "服装/鞋履"
        elif any(w in name_lower for w in bag_keywords):
            return "包袋"
        elif any(w in name_lower or w in specs_keys for w in digital_keywords):
            return "数码产品"
        else:
            return "通用商品"

    def _empty_analysis(self, encyclopedia_result: EncyclopediaResult) -> dict:
        """无二手商品时的分析"""
        return {
            "verdict": f"当前闲鱼暂无相关二手商品。建议关注新品渠道，"
                       f"{encyclopedia_result.product_name} "
                       f"目前最低全新价为 ¥{encyclopedia_result.lowest_new_price or '未知'}。",
        }

    def _determine_recommendation(
        self, rule_scores: list[dict], new_price: float
    ) -> str:
        """根据评分数据决定整体建议"""
        if not rule_scores:
            return "buy_new"

        high_score = [r for r in rule_scores if r["score_data"]["score"] >= 75]
        if len(high_score) >= 2:
            return "buy_used"
        elif any(r["score_data"]["score"] >= 60 for r in rule_scores):
            return "consider"
        else:
            return "buy_new"

    @staticmethod
    def _estimate_new_price(finder_result: FinderResult) -> float:
        """当新品价格缺失时，用二手价格反推估算"""
        if not finder_result.items:
            return 0
        prices = [item.price for item in finder_result.items]
        avg = sum(prices) / len(prices)
        # 假设二手均价约为新品的 70%
        return round(avg / 0.7, 2)


if __name__ == '__main__':
    import asyncio
    import sys

    from src.config import settings
    from src.agents.finder.agent import FinderAgent
    from src.agents.encyclopedia.agent import EncyclopediaAgent
    from src.mcp.xianyu_server import XianyuMCPServer

    async def main():
        keyword = sys.argv[1] if len(sys.argv) > 1 else "劳力士黑冰糖"

        # ---- 创建上游 Agent ----
        cookie = settings.xianyu_cookie
        if cookie:
            mcp = XianyuMCPServer(cookie=cookie)
            print(f"[INFO] Cookie 已配置，使用真实闲鱼搜索")
        else:
            mcp = None
            print(f"[INFO] Cookie 未配置，Finder 使用 LLM 模拟数据")

        finder = FinderAgent(mcp_client=mcp)
        encyclopedia = EncyclopediaAgent()
        calculator = CalculatorAgent()

        print(f"{'=' * 60}")
        print(f"CalculatorAgent 全链路测试 — 商品: {keyword}")
        print(f"{'=' * 60}\n")

        # ---- 并行跑 Finder + Encyclopedia ----
        print("[1/2] 并行执行 Finder + Encyclopedia...\n")
        finder_result, enc_result = await asyncio.gather(
            finder.execute(product_name=keyword, max_results=2),
            encyclopedia.execute(product_name=keyword),
        )

        print(f"   Finder: {finder_result.total_count} 件二手商品")
        print(f"   Encyclopedia: {enc_result.product_name}, 最低全新价 ¥{enc_result.lowest_new_price or 'N/A'}\n")

        # ---- 跑 Calculator ----
        print("[2/2] 性价比分析中...\n")
        result = await calculator.execute(
            finder_result=finder_result,
            encyclopedia_result=enc_result,
        )

        # ---- 输出 ----
        print(f"{'=' * 60}")
        print(f"📊 分析结果: {enc_result.product_name}")
        print(f"   品类: {calculator._guess_category(keyword, enc_result)}")
        print(f"   产地: {enc_result.origin or '未知'}  |  上市: {enc_result.release_date or '未知'}")
        print(f"   最低全新价: ¥{enc_result.lowest_new_price or 'N/A'}")
        print()

        print("🏷️ 新品渠道价格:")
        for p in enc_result.new_prices:
            print(f"   [{p.channel}] ¥{p.price}  {'缺货' if not p.in_stock else '有货'}")

        print(f"\n📈 市场概况:")
        print(f"   二手均价: ¥{result.market_summary.avg_used_price}")
        print(f"   价格区间: ¥{result.market_summary.price_range['min']} ~ ¥{result.market_summary.price_range['max']}")
        print(f"   在售数量: {result.market_summary.total_listings}")
        print(f"   整体建议: {result.market_summary.recommendation}")

        if result.best_deal:
            print(f"\n⭐ 最佳推荐:")
            print(f"   商品: {result.best_deal.title}")
            print(f"   价格: ¥{result.best_deal.price}  |  新品: ¥{result.best_deal.new_price}")
            print(f"   折扣率: {result.best_deal.discount_rate:.0%}  |  评分: {result.best_deal.score}/100")
            print(f"   理由: {result.best_deal.reason}")

        if result.recommendations:
            print(f"\n📋 推荐列表 (≥60分):")
            for i, rec in enumerate(result.recommendations, 1):
                print(f"   [{i}] {rec.title}")
                print(f"       ¥{rec.price} | 折扣{rec.discount_rate:.0%} | 评分{rec.score}/100")

        print(f"\n📝 AI 结论:")
        print(f"   {result.verdict}")
        print(f"\n{'=' * 60}")

    asyncio.run(main())