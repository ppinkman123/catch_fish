"""
A2A Agent App 工厂函数

为每个 Agent 创建独立的 FastAPI 应用，通过 create_agent_app() 包装。
每个函数返回一个可直接用 uvicorn 启动的 FastAPI app。

用法:
    from src.a2a.agent_apps import create_finder_app
    app = create_finder_app()
    # uvicorn app:app --port 8002
"""

from fastapi import FastAPI

from src.a2a.server import create_agent_app
from src.agents.calculator.agent import CalculatorAgent
from src.agents.encyclopedia.agent import EncyclopediaAgent
from src.agents.finder.agent import FinderAgent
from src.config import settings
from src.utils.logger import get_logger

logger = get_logger("a2a.agent_apps")


def _get_mcp_client():
    """创建闲鱼 MCP 客户端（如果 Cookie 已配置）"""
    if settings.xianyu_cookie:
        try:
            from src.mcp.xianyu_server import XianyuMCPServer
            client = XianyuMCPServer(cookie=settings.xianyu_cookie)
            logger.info("闲鱼 MCP 客户端已创建，使用真实搜索")
            return client
        except Exception as e:
            logger.warning(f"闲鱼 MCP 客户端初始化失败: {e}，回退到模拟数据")
    else:
        logger.info("XIANYU_COOKIE 未配置，Finder 将使用模拟数据")
    return None


def create_finder_app(mcp_client=None) -> FastAPI:
    """创建 Finder Agent 的 FastAPI 应用

    Args:
        mcp_client: 闲鱼 MCP 客户端（可选，不传则自动从配置创建）

    Returns:
        FastAPI app，监听 POST /execute + GET /agent-card
    """
    if mcp_client is None:
        mcp_client = _get_mcp_client()

    agent = FinderAgent(mcp_client=mcp_client)
    app = create_agent_app(agent)
    logger.info(f"Finder Agent app 已创建")
    return app


def create_encyclopedia_app() -> FastAPI:
    """创建 Encyclopedia Agent 的 FastAPI 应用

    Returns:
        FastAPI app，监听 POST /execute + GET /agent-card
    """
    agent = EncyclopediaAgent()
    app = create_agent_app(agent)
    logger.info(f"Encyclopedia Agent app 已创建")
    return app


def create_calculator_app() -> FastAPI:
    """创建 Calculator Agent 的 FastAPI 应用

    Returns:
        FastAPI app，监听 POST /execute + GET /agent-card
    """
    agent = CalculatorAgent()
    app = create_agent_app(agent)
    logger.info(f"Calculator Agent app 已创建")
    return app


def create_workflow_app(a2a_client=None) -> FastAPI:
    """创建 Workflow Agent 的 FastAPI 应用

    Args:
        a2a_client: A2A 客户端（可选，不传则 Workflow 内部走直接调用模式）

    Returns:
        FastAPI app，监听 POST /execute + GET /agent-card
    """
    from src.orchestrator.agent import WorkflowAgent

    agent = WorkflowAgent(a2a_client=a2a_client)
    app = create_agent_app(agent)
    logger.info(f"Workflow Agent app 已创建")
    return app
