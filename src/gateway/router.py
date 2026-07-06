"""
A2A Gateway API 路由

提供以下接口：
- POST /api/v1/search          发起搜索
- GET  /api/v1/search/{id}/status  查询状态
- GET  /api/v1/search/{id}/result  获取结果
- GET  /health                     健康检查
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.gateway.middleware import rate_limiter
from src.models.database import get_db
from src.models.orm import SearchLog
from src.models.schemas import (
    ErrorResponse,
    HealthResponse,
    SearchAcceptedResponse,
    SearchRequest,
    SearchResultResponse,
    SearchStatusResponse,
    TaskProgress,
)
from src.config import settings
from src.orchestrator.workflow import CatchFishWorkflow
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["catch_fish"])

# MCP 客户端（有 Cookie 则使用真实闲鱼搜索）
_mcp_client = None
if settings.xianyu_cookie:
    try:
        from src.mcp.xianyu_server import XianyuMCPServer
        _mcp_client = XianyuMCPServer(cookie=settings.xianyu_cookie)
        logger.info("已配置闲鱼 MCP 客户端，使用真实搜索")
    except Exception as e:
        logger.warning(f"闲鱼 MCP 客户端初始化失败: {e}，回退到模拟数据")
else:
    logger.info("XIANYU_COOKIE 未配置，Finder 将使用模拟数据")

# A2A 客户端（A2A 模式下初始化）
_a2a_client = None
if settings.a2a_enabled:
    try:
        from src.a2a.client import A2AClient
        _a2a_client = A2AClient()
        _a2a_client.register("finder", settings.a2a_finder_url)
        _a2a_client.register("encyclopedia", settings.a2a_encyclopedia_url)
        _a2a_client.register("calculator", settings.a2a_calculator_url)
        logger.info(
            f"A2A 模式已启用 — Finder: {settings.a2a_finder_url}, "
            f"Encyclopedia: {settings.a2a_encyclopedia_url}, "
            f"Calculator: {settings.a2a_calculator_url}"
        )
    except Exception as e:
        logger.warning(f"A2A 客户端初始化失败: {e}，回退到直接调用模式")

workflow_engine = CatchFishWorkflow(mcp_client=_mcp_client, a2a_client=_a2a_client)

# 内存结果缓存（生产环境应使用 Redis）
_results_cache: dict[str, SearchResultResponse] = {}
_workflows: dict[str, CatchFishWorkflow] = {}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    return HealthResponse()


@router.post("/search", response_model=SearchAcceptedResponse, status_code=202)
async def create_search(
    request_body: SearchRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    """
    发起一次闲鱼商品搜索 + 性价比分析

    请求被接受后立即返回 search_id，实际任务在后台异步执行。
    客户端通过 GET /search/{search_id}/status 轮询进度，
    完成后通过 GET /search/{search_id}/result 获取结果。
    """
    # 简易限流
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    search_id = str(uuid.uuid4())[:8]  # 短 ID，方便日志追踪

    logger.info(f"收到搜索请求: id={search_id}, query={request_body.query[:60]}...")

    # 记录搜索日志到数据库
    # 后台任务中执行
    background_tasks.add_task(
        _execute_search,
        search_id=search_id,
        query=request_body.query,
    )

    return SearchAcceptedResponse(
        search_id=search_id,
        estimated_seconds=30,
    )


@router.get("/search/{search_id}/status", response_model=SearchStatusResponse)
async def get_search_status(search_id: str):
    """
    查询搜索任务进度

    状态流转: pending → orchestrating → searching → calculating → completed / failed
    """
    # 检查缓存结果（已完成）
    if search_id in _results_cache:
        return SearchStatusResponse(
            search_id=search_id,
            status="completed",
            progress={
                "orchestrator": TaskProgress(status="done"),
                "finder": TaskProgress(status="done"),
                "encyclopedia": TaskProgress(status="done"),
                "calculator": TaskProgress(status="done"),
            },
        )

    # TODO: 从 Redis/DB 获取进行中任务的状态
    return SearchStatusResponse(
        search_id=search_id,
        status="pending",
        progress={},
    )


@router.get("/search/{search_id}/result", response_model=SearchResultResponse)
async def get_search_result(search_id: str):
    """
    获取完整分析结果

    如果任务尚未完成，返回 404。
    """
    if search_id not in _results_cache:
        raise HTTPException(
            status_code=404,
            detail=f"搜索结果不存在或尚未完成: {search_id}",
        )

    return _results_cache[search_id]


async def _execute_search(search_id: str, query: str):
    """后台执行搜索工作流"""
    try:
        result = await workflow_engine.execute(search_id=search_id, user_query=query)
        _results_cache[search_id] = result
        logger.info(f"[{search_id}] 搜索完成并缓存结果")
    except Exception as e:
        logger.error(f"[{search_id}] 搜索执行失败: {e}")
        # 缓存错误结果
        _results_cache[search_id] = None
