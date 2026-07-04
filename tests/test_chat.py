"""
Chat Agent 单元测试
测试策略：分层隔离
- 纯逻辑方法（_looks_like_search, _format_search_response）→ 直接测
- 依赖 LLM 的方法 → mock ask_llm / ask_llm_json
- 依赖 Workflow 的方法 → mock CatchFishWorkflow
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.chat.agent import ChatAgent, ChatIntent
from src.gateway.session import Session
from src.models.schemas import (
    SearchResultResponse,
    CalculatorResult,
    EncyclopediaResult,
    FinderResult,
    XianyuItemOut,
    Recommendation,
    MarketSummary,
    ChannelPrice,
)


# ============================================================
# 测试数据工厂
# ============================================================

def make_xianyu_item(
    title="iPhone 15 Pro 256G 深空黑",
    price=6200.0,
    condition="like_new",
    seller_credit=750,
    location="北京",
    listing_url="https://example.com/item1",
    **kwargs,
) -> XianyuItemOut:
    defaults = {
        "title": title,
        "price": price,
        "condition": condition,
        "seller_credit": seller_credit,
        "location": location,
        "listing_url": listing_url,
        "original_price": 8999.0,
    }
    defaults.update(kwargs)
    return XianyuItemOut(**defaults)


def make_search_result(items=None) -> SearchResultResponse:
    """构造一个完整的搜索结果，用于测试 _format_search_response"""
    if items is None:
        items = [
            make_xianyu_item(title="iPhone 15 Pro 256G 深空黑", price=6200),
            make_xianyu_item(title="iPhone 15 Pro 256G 白色", price=6500),
            make_xianyu_item(title="iPhone 15 Pro 128G 黑色", price=5500),
        ]

    return SearchResultResponse(
        search_id="test_mock_001",
        query="iPhone 15 Pro",
        completed_at=datetime.now(),
        xianyu_items=items,
        product_info=EncyclopediaResult(
            product_name="iPhone 15 Pro",
            brand="Apple",
            model="A2848",
            specs={"芯片": "A17 Pro", "内存": "8GB", "存储": "256GB"},
            lowest_new_price=7899,
            new_prices=[
                ChannelPrice(channel="jd", price=7999, in_stock=True),
                ChannelPrice(channel="tmall", price=7899, in_stock=True),
            ],
        ),
        analysis=CalculatorResult(
            market_summary=MarketSummary(
                total_listings=86,
                avg_used_price=6200,
                price_range={"min": 5000, "max": 7500},
                recommendation="buy_used",
            ),
            best_deal=Recommendation(
                title="iPhone 15 Pro 256G 深空黑",
                price=6200,
                new_price=7999,
                discount_rate=0.225,
                score=88,
                reason="折扣力度大，成色好，卖家信用高",
            ),
            recommendations=[
                Recommendation(
                    title="iPhone 15 Pro 256G 深空黑",
                    price=6200,
                    new_price=7999,
                    discount_rate=0.225,
                    score=88,
                    reason="折扣力度大，成色好",
                ),
                Recommendation(
                    title="iPhone 15 Pro 256G 白色",
                    price=6500,
                    new_price=7999,
                    discount_rate=0.187,
                    score=82,
                    reason="成色极佳",
                ),
            ],
            verdict="综合来看，第一个商品性价比最高，推荐入手。",
        ),
    )


# ============================================================
# 纯逻辑测试（无需 Mock LLM）
# ============================================================

class TestLooksLikeSearch:
    """关键词路由 —— 不依赖 LLM，直接测"""

    @pytest.mark.parametrize("message", [
        "帮我搜一下 iPhone 15",
        "找一台 MacBook Pro",
        "看看有没有便宜的 iPad",
        "查一下二手显卡",
        "有没有好用的机械键盘",
        "这个多少钱",
        "值得买吗",
        "划算不划算",
        "二手相机推荐",
        "帮我看看性价比",
        "想入手一个",
        "买哪个好",
    ])
    async def test_positive(self, message):
        agent = ChatAgent()
        assert await agent._looks_like_search(message) is True

    @pytest.mark.parametrize("message", [
        "你好",
        "今天天气不错",
        "谢谢你的帮助",
        "什么是性价比",
        "闲鱼交易要注意什么",
        "第三个怎么样",  # 追问不算搜索
        "1和3哪个好",     # 对比不算搜索
        "再详细说说",
    ])
    async def test_negative(self, message):
        agent = ChatAgent()
        assert await agent._looks_like_search(message) is False


class TestFormatSearchResponse:
    """格式化回复 —— 不依赖 LLM，直接测"""

    async def test_basic_format(self):
        agent = ChatAgent()
        result = make_search_result()
        text = await agent._format_search_response(result)

        assert "iPhone 15 Pro" in text
        assert "6200" in text
        assert "88" in text or "88/100" in text
        assert "推荐" in text or "最推荐" in text

    async def test_empty_items(self):
        agent = ChatAgent()
        result = make_search_result(items=[])
        text = await agent._format_search_response(result)

        assert "抱歉" in text or "没有找到" in text


class TestFormatHistory:
    """对话历史格式化"""

    async def test_format(self):
        agent = ChatAgent()
        session = Session(session_id="test_001")
        session.add_message("user", "帮我搜 iPhone")
        session.add_message("assistant", "好的，正在搜索...")

        text = agent._format_history(session)
        assert "用户" in text
        assert "iPhone" in text


# ============================================================
# 需要 Mock LLM 的测试
# ============================================================

class TestRouteIntentFirstMessage:
    """首条消息路由 —— 走关键词判断，不需要 Mock LLM"""

    async def test_first_message_search(self):
        agent = ChatAgent()
        session = Session(session_id="test_002")

        intent, data = await agent._route_intent(session, "帮我搜一下 iPhone")

        assert intent == ChatIntent.NEW_SEARCH
        assert data["confidence"] > 0.8

    async def test_first_message_greeting(self):
        agent = ChatAgent()
        session = Session(session_id="test_003")

        intent, data = await agent._route_intent(session, "你好")

        assert intent == ChatIntent.GENERAL_CHAT


class TestRouteIntentWithContext:
    """有搜索上下文时的路由 —— 需要 Mock LLM"""

    @pytest.fixture
    def session_with_context(self):
        session = Session(session_id="test_004")
        session.add_message("user", "帮我搜 iPhone 15 Pro")
        session.add_message("assistant", "找到了 3 个商品...")
        session.bind_search_result("iPhone 15 Pro", make_search_result())
        session.add_message("user", "第三个怎么样")
        return session

    async def test_llm_route_follow_up(self, session_with_context):
        agent = ChatAgent()
        # Mock LLM 返回 follow_up 意图
        agent.ask_llm_json = AsyncMock(return_value={
            "intent": "follow_up",
            "target_item_index": 3,
            "confidence": 0.9,
            "reasoning": "用户询问第三个商品",
        })

        intent, data = await agent._route_intent(session_with_context, "第三个怎么样")

        assert intent == ChatIntent.FOLLOW_UP
        assert data["target_item_index"] == 3

    async def test_llm_route_compare(self, session_with_context):
        agent = ChatAgent()
        agent.ask_llm_json = AsyncMock(return_value={
            "intent": "compare",
            "target_item_indices": [1, 3],
            "confidence": 0.85,
            "reasoning": "用户想对比第1和第3个",
        })

        intent, data = await agent._route_intent(session_with_context, "1和3哪个好")

        assert intent == ChatIntent.COMPARE
        assert data["target_item_indices"] == [1, 3]

    async def test_llm_route_fallback(self, session_with_context):
        """LLM 调用失败时回退到 general_chat"""
        agent = ChatAgent()
        agent.ask_llm_json = AsyncMock(side_effect=Exception("API 挂了"))

        intent, data = await agent._route_intent(session_with_context, "第三个怎么样")

        assert intent == ChatIntent.GENERAL_CHAT


class TestHandleMessage:
    """端到端流程测试 —— Mock 所有外部依赖"""

    @pytest.fixture
    def session(self):
        return Session(session_id="test_005")

    async def test_new_search_flow(self, session):
        """模拟新搜索的完整流程"""
        agent = ChatAgent()

        # Mock 1: 路由 → new_search
        agent._route_intent = AsyncMock(return_value=(
            ChatIntent.NEW_SEARCH,
            {"target_product": "iPhone 15 Pro", "confidence": 0.9},
        ))

        # Mock 2: 工作流执行
        mock_result = make_search_result()
        agent._workflow = MagicMock()
        agent._workflow.execute = AsyncMock(return_value=mock_result)

        response = await agent.handle_message(session, "帮我搜 iPhone 15 Pro")

        assert "iPhone" in response
        assert len(session.messages) == 2  # user + assistant
        assert session.has_search_context is True

    async def test_general_chat_flow(self, session):
        """模拟闲聊流程"""
        agent = ChatAgent()

        agent._route_intent = AsyncMock(return_value=(
            ChatIntent.GENERAL_CHAT,
            {"confidence": 0.8},
        ))
        # Mock LLM 回复
        agent.ask_llm = AsyncMock(return_value="你好！我是二手数码购物助手，有什么可以帮你的？")

        response = await agent.handle_message(session, "你好")

        assert "你好" in response or "二手" in response


# ============================================================
# 手动 Debug 入口（直接运行本文件时使用）
# ============================================================

if __name__ == "__main__":
    import asyncio

    async def debug_session():
        """模拟一个完整的对话流程，需要配置 DEEPSEEK_API_KEY"""
        from src.gateway.session import SessionManager

        manager = SessionManager()
        session = manager.create()
        agent = ChatAgent()

        print("=" * 60)
        print("Chat Agent 手动调试")
        print("=" * 60)

        # 轮次 1: 搜索
        print("\n[用户] 帮我看看 iPhone 15 Pro 二手多少钱")
        # 只测路由，不触发真实搜索
        intent, data = await agent._route_intent(session, "帮我看看 iPhone 15 Pro 二手多少钱")
        print(f"[路由] intent={intent.value}, data={data}")

        # 轮次 2: 追问（需手动绑定搜索上下文后测试）
        session.add_message("user", "帮我看看 iPhone 15 Pro")
        session.add_message("assistant", "找到了几个商品...")
        session.bind_search_result("iPhone 15 Pro", make_search_result())
        session.add_message("user", "第三个怎么样")

        intent, data = await agent._route_intent(session, "第三个怎么样")
        print(f"\n[用户] 第三个怎么样")
        print(f"[路由] intent={intent.value}, data={data}")

        # 测试格式化
        print("\n[测试 _format_search_response]")
        text = await agent._format_search_response(make_search_result())
        print(text[:500])

        print("\n✅ 调试完成")

    asyncio.run(debug_session())
