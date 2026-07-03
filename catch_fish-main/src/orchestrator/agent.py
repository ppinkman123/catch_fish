"""
Orchestrator Agent — 任务调度编排器

解析用户意图 → 拆解子任务 → 编排 DAG 执行顺序 → 协调各 Agent 协作
"""

from src.agents.base import BaseAgent
from src.models.schemas import ParsedIntent
from src.utils.logger import get_logger

logger = get_logger(__name__)


ORCHESTRATOR_SYSTEM_PROMPT = """你是一个二手数码商品搜索的调度专家，服务于数码爱好者用户。

## 你的能力
解析用户用自然语言描述的搜索需求，提取关键信息，拆解为可执行的子任务。

## 用户画像
目标用户是数码爱好者，他们对数码产品的型号、规格非常了解，经常会搜索：
- 手机：iPhone、华为、小米、三星等旗舰机型
- 电脑：MacBook、ThinkPad、ROG 等
- 相机：Sony A7、Canon R系列、DJI 无人机等
- 智能穿戴：Apple Watch、AirPods 等
- 游戏设备：Switch、PS5、Steam Deck 等

## 意图提取要点
1. **商品名称**：识别品牌 + 系列 + 具体型号
2. **规格参数**：容量/内存/颜色/版本（国行/港版/美版）
3. **预算区间**：用户有无明确预算
4. **成色偏好**：用户是否关心成色（全新未拆/99新/正常使用）
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
