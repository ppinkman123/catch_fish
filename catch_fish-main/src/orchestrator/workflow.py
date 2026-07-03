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

    def __init__(self):
        self.orchestrator = OrchestratorAgent()
        self.finder = FinderAgent()
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
