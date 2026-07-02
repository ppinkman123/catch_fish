"""
Finder Agent 单元测试
"""

import pytest

from src.agents.finder.agent import FinderAgent
from src.models.schemas import FinderResult


@pytest.mark.asyncio
async def test_finder_fallback_search():
    """测试 Finder Agent 在无 MCP 时的模拟搜索"""
    agent = FinderAgent(mcp_client=None)

    result = await agent.execute(
        product_name="iPhone 15 Pro 256G",
        budget_min=5000,
        budget_max=8000,
    )

    assert isinstance(result, FinderResult)
    assert result.search_keyword == "iPhone 15 Pro 256G"
    assert result.total_count >= 0  # 模拟数据可能为 0 或更多
    assert isinstance(result.items, list)


@pytest.mark.asyncio
async def test_finder_with_budget():
    """测试带预算参数的搜索"""
    agent = FinderAgent(mcp_client=None)

    result = await agent.execute(
        product_name="MacBook Pro M3",
        budget_min=8000,
        budget_max=12000,
        max_results=10,
    )

    assert isinstance(result, FinderResult)
    assert result.total_count >= 0


@pytest.mark.asyncio
async def test_finder_empty_keyword():
    """测试空关键词搜索"""
    agent = FinderAgent(mcp_client=None)

    result = await agent.execute(product_name="")

    assert isinstance(result, FinderResult)
