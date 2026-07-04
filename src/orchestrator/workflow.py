"""
Orchestrator 工作流引擎

定义 Agent 之间的 DAG 执行流程：
    Finder (并行) ──┐
                      ├──→ Calculator → 汇总结果
    Encyclopedia ────┘
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.agents.calculator.agent import CalculatorAgent
from src.agents.encyclopedia.agent import EncyclopediaAgent
from src.agents.finder.agent import FinderAgent
from src.models.schemas import (
    CalculatorResult,
    EncyclopediaResult,
    FinderResult,
    ParsedIntent,
    SearchResultResponse,
)
from src.orchestrator.agent import OrchestratorAgent
from src.utils.logger import get_logger

logger = get_logger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class TaskState:
    """单个子任务状态"""
    name: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    result: object = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }


@dataclass
class WorkflowContext:
    """工作流上下文，贯穿整个搜索生命周期"""
    search_id: str
    query: str
    intent: ParsedIntent | None = None
    tasks: dict[str, TaskState] = field(default_factory=dict)
    finder_result: FinderResult | None = None
    encyclopedia_result: EncyclopediaResult | None = None
    calculator_result: CalculatorResult | None = None
    status: str = "pending"
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def get_progress(self) -> dict:
        """获取当前进度"""
        return {
            task_id: state.to_dict()
            for task_id, state in self.tasks.items()
        }


class CatchFishWorkflow:
    """
    catch_fish 核心工作流

    DAG:
        Orchestrator (解析意图)
              │
        ┌─────┴─────┐
        ▼           ▼
      Finder    Encyclopedia
        │           │
        └─────┬─────┘
              ▼
         Calculator
              │
              ▼
        最终结果

    其中 Finder 和 Encyclopedia 可以并行执行（无数据依赖）
    Calculator 依赖前两者全部完成
    """

    def __init__(self, mcp_client=None):
        """
        Args:
            mcp_client: 闲鱼 MCP 客户端（可选，不传则 Finder 使用 LLM 模拟数据）
        """
        self.orchestrator = OrchestratorAgent()
        self.finder = FinderAgent(mcp_client=mcp_client)
        self.encyclopedia = EncyclopediaAgent()
        self.calculator = CalculatorAgent()

    async def execute(self, search_id: str, user_query: str) -> SearchResultResponse:
        """
        执行完整的搜索→分析工作流

        Args:
            search_id: 搜索 ID
            user_query: 用户原始查询

        Returns:
            SearchResultResponse: 完整的性价比分析结果

        Raises:
            Exception: 任意步骤失败时抛出
        """
        ctx = WorkflowContext(search_id=search_id, query=user_query)
        ctx.status = "orchestrating"
        logger.info(f"[{search_id}] 工作流启动: {user_query[:60]}...")

        try:
            # Step 1: 解析意图
            intent = await self._step_parse_intent(ctx)
            ctx.intent = intent

            # Step 2: 并行执行 Finder + Encyclopedia
            ctx.status = "searching"
            ctx.tasks["finder"] = TaskState(name="finder", status=TaskStatus.RUNNING)
            ctx.tasks["encyclopedia"] = TaskState(name="encyclopedia", status=TaskStatus.RUNNING)

            finder_task = self._step_find(ctx, intent)
            encyclopedia_task = self._step_research(ctx, intent)

            finder_result, encyclopedia_result = await asyncio.gather(
                finder_task, encyclopedia_task
            )

            ctx.finder_result = finder_result
            ctx.tasks["finder"].result = finder_result
            ctx.tasks["finder"].status = TaskStatus.DONE
            ctx.tasks["finder"].finished_at = datetime.now()

            ctx.encyclopedia_result = encyclopedia_result
            ctx.tasks["encyclopedia"].result = encyclopedia_result
            ctx.tasks["encyclopedia"].status = TaskStatus.DONE
            ctx.tasks["encyclopedia"].finished_at = datetime.now()

            # Step 3: 计算性价比
            ctx.status = "calculating"
            ctx.tasks["calculator"] = TaskState(name="calculator", status=TaskStatus.RUNNING)
            calculator_result = await self._step_calculate(ctx)
            ctx.calculator_result = calculator_result
            ctx.tasks["calculator"].result = calculator_result
            ctx.tasks["calculator"].status = TaskStatus.DONE
            ctx.tasks["calculator"].finished_at = datetime.now()

            ctx.status = "completed"
            logger.info(f"[{search_id}] 工作流完成")

            return SearchResultResponse(
                search_id=search_id,
                query=user_query,
                product_info=encyclopedia_result,
                xianyu_items=finder_result.items,
                analysis=calculator_result,
                completed_at=datetime.now(),
            )

        except Exception as e:
            ctx.status = "failed"
            ctx.error = str(e)
            logger.error(f"[{search_id}] 工作流失败: {e}")
            raise

    async def _step_parse_intent(self, ctx: WorkflowContext) -> ParsedIntent:
        """Step 1: 解析意图"""
        ctx.tasks["orchestrator"] = TaskState(
            name="orchestrator",
            status=TaskStatus.RUNNING,
            started_at=datetime.now(),
        )

        intent = await self.orchestrator.parse_intent(ctx.query)

        ctx.tasks["orchestrator"].result = intent
        ctx.tasks["orchestrator"].status = TaskStatus.DONE
        ctx.tasks["orchestrator"].finished_at = datetime.now()
        return intent

    async def _step_find(self, ctx: WorkflowContext, intent: ParsedIntent) -> FinderResult:
        """Step 2a: 搜索闲鱼商品"""
        ctx.tasks["finder"].started_at = datetime.now()
        try:
            return await self.finder.execute(
                product_name=intent.product_name,
                budget_min=intent.budget_min,
                budget_max=intent.budget_max,
                condition=intent.condition_preference or "all",
                location=intent.location,
            )
        except Exception as e:
            ctx.tasks["finder"].status = TaskStatus.FAILED
            ctx.tasks["finder"].error = str(e)
            raise

    async def _step_research(self, ctx: WorkflowContext, intent: ParsedIntent) -> EncyclopediaResult:
        """Step 2b: 采集商品百科"""
        ctx.tasks["encyclopedia"].started_at = datetime.now()
        try:
            return await self.encyclopedia.execute(
                product_name=intent.product_name,
                brand=intent.brand,
                model=intent.model,
                specs=intent.specs,
            )
        except Exception as e:
            ctx.tasks["encyclopedia"].status = TaskStatus.FAILED
            ctx.tasks["encyclopedia"].error = str(e)
            raise

    async def _step_calculate(self, ctx: WorkflowContext) -> CalculatorResult:
        """Step 3: 计算性价比"""
        ctx.tasks["calculator"].started_at = datetime.now()
        try:
            return await self.calculator.execute(
                finder_result=ctx.finder_result,
                encyclopedia_result=ctx.encyclopedia_result,
            )
        except Exception as e:
            ctx.tasks["calculator"].status = TaskStatus.FAILED
            ctx.tasks["calculator"].error = str(e)
            raise

if __name__ == '__main__':
    import asyncio
    import sys
    import time

    async def main():
        from src.config import settings
        from src.mcp.xianyu_server import XianyuMCPServer

        query = sys.argv[1] if len(sys.argv) > 1 else "帮我看看 iPhone 15 Pro 256G 二手值得入手吗"

        # ---- 有 Cookie → 真实搜索；无 Cookie → 模拟数据 ----
        cookie = settings.xianyu_cookie
        if cookie:
            mcp = XianyuMCPServer(cookie=cookie)
            print(f"[INFO] Cookie 已配置，使用真实闲鱼搜索")
        else:
            mcp = None
            print(f"[INFO] Cookie 未配置，Finder 使用 LLM 模拟数据")

        print(f"{'=' * 60}")
        print(f"CatchFishWorkflow 全链路测试")
        print(f"查询: {query}")
        print(f"{'=' * 60}\n")

        wf = CatchFishWorkflow(mcp_client=mcp)
        search_id = f"test_{int(time.time())}"

        t0 = time.time()
        try:
            result = await wf.execute(search_id=search_id, user_query=query)
            elapsed = time.time() - t0

            print(f"\n{'=' * 60}")
            print(f"✅ 工作流执行成功 ({elapsed:.1f}s)")
            print(f"{'=' * 60}")
            print(f"  search_id: {result.search_id}")
            print(f"  查询: {result.query}")

            # --- 商品百科 ---
            pi = result.product_info
            print(f"\n📚 商品百科:")
            print(f"  商品: {pi.product_name}")
            print(f"  品牌: {pi.brand or 'N/A'}  |  型号: {pi.model or 'N/A'}")
            print(f"  产地: {pi.origin or 'N/A'}  |  上市: {pi.release_date or 'N/A'}")
            print(f"  评分: {pi.rating or 'N/A'}  |  保修: {pi.warranty or 'N/A'}")
            print(f"  最低全新价: ¥{pi.lowest_new_price or 'N/A'}")
            if pi.specs:
                print(f"  规格: {pi.specs}")
            if pi.new_prices:
                print(f"  渠道价格:")
                for p in pi.new_prices:
                    print(f"    [{p.channel}] ¥{p.price}  {'缺货' if not p.in_stock else '有货'}")

            # --- 闲鱼商品 ---
            print(f"\n🐟 闲鱼二手 ({len(result.xianyu_items)} 件):")
            for i, item in enumerate(result.xianyu_items, 1):
                print(f"  [{i}] {item.title}")
                print(f"      价格: ¥{item.price}  |  成色: {item.condition or '未知'}  |  信誉: {item.seller_credit or 'N/A'}")
                print(f"      卖家: {item.seller_nickname or 'N/A'}  |  位置: {item.location or 'N/A'}")

            # --- 分析结果 ---
            ana = result.analysis
            print(f"\n📊 性价比分析:")
            print(f"  市场均价: ¥{ana.market_summary.avg_used_price}")
            print(f"  价格区间: ¥{ana.market_summary.price_range.get('min', 0)} ~ ¥{ana.market_summary.price_range.get('max', 0)}")
            print(f"  在售数量: {ana.market_summary.total_listings}")
            print(f"  整体建议: {ana.market_summary.recommendation}")

            if ana.best_deal:
                print(f"\n⭐ 最佳推荐:")
                print(f"  {ana.best_deal.title}")
                print(f"  价格: ¥{ana.best_deal.price}  |  新品: ¥{ana.best_deal.new_price}")
                print(f"  折扣率: {ana.best_deal.discount_rate:.0%}  |  评分: {ana.best_deal.score}/100")
                print(f"  理由: {ana.best_deal.reason}")

            if ana.recommendations:
                print(f"\n📋 推荐列表 (≥60分):")
                for i, rec in enumerate(ana.recommendations, 1):
                    print(f"  [{i}] {rec.title}")
                    print(f"      ¥{rec.price} | 折扣{rec.discount_rate:.0%} | 评分{rec.score}/100")

            print(f"\n📝 AI 综合结论:")
            print(f"  {ana.verdict}")
            print(f"\n{'=' * 60}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"\n❌ 工作流失败 ({elapsed:.1f}s): {e}")
            import traceback
            traceback.print_exc()

    asyncio.run(main())