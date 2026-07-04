"""
Orchestrator Agent — 任务调度编排器

解析用户意图 → 拆解子任务 → 编排 DAG 执行顺序 → 协调各 Agent 协作
"""

from src.agents.base import BaseAgent
from src.models.schemas import ParsedIntent
from src.utils.logger import get_logger

logger = get_logger(__name__)


ORCHESTRATOR_SYSTEM_PROMPT = """你是一个二手商品搜索的调度专家，服务意识强。

## 你的能力
解析用户用自然语言描述的搜索需求，提取关键信息，拆解为可执行的子任务。

## 用户画像
目标用户会搜索各类商品，包括但不限于：
- 数码产品：手机、电脑、相机、耳机等
- 手表：劳力士、卡西欧、欧米茄等
- 服装鞋履：品牌衣裤、球鞋、配饰等
- 包袋：LV、Gucci、Chanel 等
- 运动装备：高尔夫、滑雪、骑行等

## 意图提取要点
1. **商品名称**：识别品牌 + 系列 + 具体型号
2. **规格参数**：容量/颜色/尺寸/版本（视品类灵活调整）
3. **预算区间**：用户有无明确预算
4. **成色偏好**：用户是否关心成色（全新/几乎全新/正常使用）
5. **地区偏好**：是否限定地区

## 输出格式
```json
{
  "product_name": "具体的商品名称+型号",
  "brand": "品牌",
  "model": "具体型号",
  "specs": {"容量": "256GB", "颜色": "黑色", "版本": "国行"},
  "budget_min": 数字或null,
  "budget_max": 数字或null,
  "condition_preference": "all / like_new / good / 不限定",
  "location": "城市或不限定"
}
```"""


class OrchestratorAgent(BaseAgent):
    """
    调度编排器 Agent

    工作流程:
    1. 接收用户查询 → 解析意图
    2. 生成 DAG 执行计划（并行/串行）
    3. 协调 Finder → Encyclopedia → Calculator 三个子 Agent
    4. 汇总结果 → 返回完整分析
    """

    agent_id = "orchestrator"
    agent_name = "调度编排器"

    def system_prompt(self) -> str:
        return ORCHESTRATOR_SYSTEM_PROMPT

    async def execute(self, user_query: str, **kwargs) -> ParsedIntent:
        """
        执行编排：解析用户意图

        Args:
            user_query: 用户原始查询
        """
        return await self.parse_intent(user_query)

    async def parse_intent(self, user_query: str) -> ParsedIntent:
        """
        解析用户搜索意图

        Args:
            user_query: 用户原始查询，如 "帮我看看 iPhone 15 Pro 256G 国行 深空黑 二手值得入手吗"

        Returns:
            ParsedIntent: 结构化的意图
        """
        self.logger.info(f"解析用户意图: {user_query[:80]}...")

        prompt = f'请分析以下用户查询，提取关键搜索信息：\n\n"{user_query}"'

        try:
            data = await self.ask_llm_json(
                user_message=prompt,
                system_prompt=self.system_prompt(),
            )

            intent = ParsedIntent(
                product_name=data.get("product_name", user_query),
                brand=data.get("brand"),
                model=data.get("model"),
                specs=data.get("specs", {}),
                budget_min=data.get("budget_min"),
                budget_max=data.get("budget_max"),
                condition_preference=data.get("condition_preference", "all"),
                location=data.get("location"),
            )
            self.logger.info(f"意图解析完成: {intent.product_name}")
            return intent

        except Exception as e:
            self.logger.error(f"意图解析失败: {e}，使用原始查询")
            return ParsedIntent(product_name=user_query)


if __name__ == '__main__':
    import asyncio
    import sys

    async def main():
        queries = sys.argv[1:] if len(sys.argv) > 1 else [
            "帮我看看 iPhone 15 Pro 256G 国行 深空黑 二手值得入手吗",
            "劳力士黑冰糖 预算2-3万",
            "Nike Air Force 1 42码 全新",
            "LV Neverfull 中号 二手大概多少钱",
        ]

        oa = OrchestratorAgent()

        for query in queries:
            print(f"{'=' * 50}")
            print(f"用户: {query}")
            print(f"{'=' * 50}")

            intent = await oa.parse_intent(query)

            print(f"  商品: {intent.product_name}")
            print(f"  品牌: {intent.brand or 'N/A'}  |  型号: {intent.model or 'N/A'}")
            if intent.specs:
                print(f"  规格: {intent.specs}")
            print(f"  预算: {intent.budget_min or '不限'} ~ {intent.budget_max or '不限'}")
            print(f"  成色: {intent.condition_preference or '不限'}")
            print(f"  地区: {intent.location or '不限'}")
            print()

    asyncio.run(main())