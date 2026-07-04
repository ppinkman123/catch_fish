"""
Chat Agent — 多轮对话入口 + 意图路由

作为用户对话的唯一入口，负责:
1. 分析用户意图（新搜索 / 追问 / 对比 / 闲聊）
2. 协调子 Agent 执行任务
3. 结合上下文生成自然回复
"""

from enum import Enum
from typing import Optional

from src.agents.base import BaseAgent
from src.agents.chat.prompts import (
    CHAT_SYSTEM_PROMPT,
    COMPARE_PROMPT,
    FOLLOW_UP_PROMPT,
    GENERAL_CHAT_PROMPT,
    GREETING_PROMPT,
    INTENT_ROUTING_PROMPT,
)
from src.config import settings
from src.gateway.session import Session
from src.models.schemas import SearchResultResponse
from src.orchestrator.workflow import CatchFishWorkflow
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ChatIntent(str, Enum):
    NEW_SEARCH = "new_search"
    FOLLOW_UP = "follow_up"
    COMPARE = "compare"
    DETAIL = "detail"
    GENERAL_CHAT = "general_chat"


class ChatAgent(BaseAgent):
    """
    对话 Agent — 多轮交互入口

    每轮对话流程:
    1. 分析用户意图（结合上下文）
    2. 根据意图路由到不同的处理逻辑
    3. 生成自然回复
    """

    agent_id = "chat"
    agent_name = "对话Agent"

    def __init__(self):
        super().__init__()
        mcp_client = None
        if settings.xianyu_cookie:
            try:
                from src.mcp.xianyu_server import XianyuMCPServer
                mcp_client = XianyuMCPServer(cookie=settings.xianyu_cookie)
                logger.info("已配置闲鱼 MCP 客户端，使用真实搜索")
            except Exception as e:
                logger.warning(f"闲鱼 MCP 客户端初始化失败: {e}，回退到模拟数据")
        else:
            logger.info("XIANYU_COOKIE 未配置，Finder 将使用模拟数据")
        self._workflow = CatchFishWorkflow(mcp_client=mcp_client)

    def system_prompt(self) -> str:
        return CHAT_SYSTEM_PROMPT

    async def execute(self, **kwargs) -> str:
        """
        实现 BaseAgent 抽象方法。
        ChatAgent 的主要入口是 handle_message()，此方法为兼容性适配。
        """
        session = kwargs.get("session")
        user_message = kwargs.get("user_message", "")
        on_progress = kwargs.get("on_progress")
        if session is None:
            from src.gateway.session import Session
            session = Session(session_id=kwargs.get("session_id", "default"))
        return await self.handle_message(session, user_message, on_progress)

    async def handle_message(
        self,
        session: Session,
        user_message: str,
        on_progress=None,
    ) -> str:
        """
        处理用户消息的主入口

        Args:
            session: 当前会话
            user_message: 用户消息
            on_progress: 可选回调，用于 SSE 推送进度 on_progress(stage, detail)

        Returns:
            str: Assistant 回复文本
        """
        logger.info(f"[{session.session_id}] 收到消息: {user_message[:60]}...")

        # Step 1: 路由意图
        intent, route_data = await self._route_intent(session, user_message)
        logger.info(f"[{session.session_id}] 意图={intent.value}, 置信度={route_data.get('confidence', 0)}")

        # Step 2: 根据意图分发处理
        if intent == ChatIntent.NEW_SEARCH:
            response = await self._handle_new_search(
                session, user_message, route_data, on_progress
            )
        elif intent == ChatIntent.FOLLOW_UP:
            response = await self._handle_follow_up(session, user_message, route_data)
        elif intent == ChatIntent.COMPARE:
            response = await self._handle_compare(session, user_message, route_data)
        elif intent == ChatIntent.DETAIL:
            response = await self._handle_detail(session, user_message, route_data)
        else:
            response = await self._handle_general_chat(session, user_message)

        # Step 3: 记录对话
        session.add_message("assistant", response)

        return response

    # ============================================================
    # 意图路由
    # ============================================================

    async def _route_intent(self, session: Session, user_message: str) -> tuple[ChatIntent, dict]:
        """根据上下文和用户消息判断意图"""
        # 首次消息 → 可能是问候或搜索
        if session.message_count <= 1:
            # 判断是否是搜索请求
            if await self._looks_like_search(user_message):
                return ChatIntent.NEW_SEARCH, {"confidence": 0.9}
            else:
                return ChatIntent.GENERAL_CHAT, {"confidence": 0.8}

        # 无搜索上下文 → 可能是新搜索或闲聊
        if not session.has_search_context:
            if await self._looks_like_search(user_message):
                return ChatIntent.NEW_SEARCH, {"confidence": 0.85}
            return ChatIntent.GENERAL_CHAT, {"confidence": 0.7}

        # 有搜索上下文 → 用 LLM 精确判断
        return await self._llm_route_intent(session, user_message)

    async def _looks_like_search(self, message: str) -> bool:
        """快速判断消息是否像搜索请求（无需 LLM）"""
        search_keywords = [
            "搜", "找", "看看", "查", "有没有", "多少钱",
            "值得买", "划算", "二手", "闲鱼", "入手",
            "买", "推荐", "性价比",
        ]
        return any(kw in message for kw in search_keywords)

    async def _llm_route_intent(self, session: Session, user_message: str) -> tuple[ChatIntent, dict]:
        """用 LLM 精确分析意图"""
        # 构建对话历史摘要
        history_text = ""
        for m in session.messages[-6:]:  # 最近 6 条
            history_text += f"{m.role}: {m.content[:100]}\n"

        # 搜索上下文摘要
        ctx_text = "无"
        if session.search_context:
            items = session.search_context.xianyu_items
            ctx_text = f"有 {len(items)} 个搜索结果:\n"
            for i, item in enumerate(items[:5], 1):
                ctx_text += f"  [{i}] {item.title} - ¥{item.price}\n"

        prompt = INTENT_ROUTING_PROMPT.format(
            conversation_history=history_text,
            search_context=ctx_text,
            user_message=user_message,
        )

        try:
            data = await self.ask_llm_json(prompt)
            intent_str = data.get("intent", "general_chat")
            intent = ChatIntent(intent_str)
            return intent, data
        except Exception as e:
            logger.warning(f"意图路由失败: {e}，退回 general_chat")
            return ChatIntent.GENERAL_CHAT, {"confidence": 0.5}

    # ============================================================
    # 处理: 新搜索
    # ============================================================

    async def _handle_new_search(
        self,
        session: Session,
        user_message: str,
        route_data: dict,
        on_progress=None,
    ) -> str:
        """触发完整搜索流程"""
        product_name = route_data.get("target_product", user_message)

        if on_progress:
            await on_progress("orchestrating", f"正在分析你的需求: {product_name}")

        # 执行完整工作流
        try:
            if on_progress:
                await on_progress("searching", "正在闲鱼搜索二手商品...")

            result = await self._workflow.execute(
                search_id=session.session_id,
                user_query=user_message,
            )

            # 绑定到会话
            session.bind_search_result(user_message, result)

            if on_progress:
                await on_progress("completed", "分析完成")

            # 生成自然语言回复
            return await self._format_search_response(result)

        except Exception as e:
            logger.error(f"搜索失败: {e}")
            return f"抱歉，搜索过程中出了点问题：{str(e)[:200]}。请稍后再试。"

    async def _format_search_response(self, result: SearchResultResponse) -> str:
        """将结构化结果转为用户友好的回复"""
        items = result.xianyu_items
        analysis = result.analysis
        product = result.product_info

        if not items:
            return f"抱歉，目前在闲鱼上没有找到 {product.product_name} 的相关二手商品。\n\n建议你尝试：\n- 简化搜索关键词\n- 扩大预算范围\n- 或者等几天再看看"

        # 构建回复
        lines = [
            f"## 🔍 {product.product_name} 闲鱼二手分析",
            "",
            f"📊 **市场概况**：在售 {analysis.market_summary.total_listings} 件，",
            f"二手均价 ¥{analysis.market_summary.avg_used_price:,.0f}，",
            f"全新最低 ¥{analysis.new_product_baseline.price if analysis.new_product_baseline else '未知':,}",
            "",
            "### 🏆 最推荐",
        ]

        if analysis.best_deal:
            bd = analysis.best_deal
            lines.extend([
                f"- **{bd.title}**",
                f"- 💰 二手价: ¥{bd.price:,.0f} | 新品价: ¥{bd.new_price:,.0f}",
                f"- 📉 折扣率: {bd.discount_rate:.0%}（省了 ¥{bd.new_price - bd.price:,.0f}）",
                f"- ⭐ 性价比评分: {bd.score}/100",
                f"- 📝 {bd.reason}",
            ])

        lines.extend(["", "### 📋 其他推荐"])

        for i, rec in enumerate(analysis.recommendations[:5], 1):
            if analysis.best_deal and rec.title == analysis.best_deal.title:
                continue
            lines.append(f"{i}. **{rec.title[:60]}** — ¥{rec.price:,.0f} | 评分 {rec.score}/100 | {rec.verdict_reason if hasattr(rec, 'verdict_reason') else rec.reason}")

        lines.extend(["", f"### 💡 结论", "", analysis.verdict, "", "---", "想深入了解哪个商品？直接告诉我序号就行 👇"])

        return "\n".join(lines)

    # ============================================================
    # 处理: 追问
    # ============================================================

    async def _handle_follow_up(
        self,
        session: Session,
        user_message: str,
        route_data: dict,
    ) -> str:
        """基于上下文回答追问"""
        target_index = route_data.get("target_item_index", 1)
        item = session.get_item_by_index(target_index)

        # 构建商品摘要
        items_text = ""
        for i, item_ in enumerate(session.search_context.xianyu_items[:10], 1):
            items_text += f"[{i}] {item_.title} - ¥{item_.price} - {item_.condition or '未知成色'}\n"

        prompt = FOLLOW_UP_PROMPT.format(
            conversation_history=self._format_history(session),
            items_summary=items_text,
            user_message=user_message,
            target_index=target_index,
        )

        return await self.ask_llm(prompt, self.system_prompt())

    # ============================================================
    # 处理: 对比
    # ============================================================

    async def _handle_compare(
        self,
        session: Session,
        user_message: str,
        route_data: dict,
    ) -> str:
        """对比多个商品"""
        indices = route_data.get("target_item_indices", [1, 2])

        items_text = ""
        for i, item_ in enumerate(session.search_context.xianyu_items[:10], 1):
            marker = " ←" if i in indices else ""
            items_text += f"[{i}] {item_.title} - ¥{item_.price} - {item_.condition or '未知成色'}{marker}\n"

        prompt = COMPARE_PROMPT.format(
            conversation_history=self._format_history(session),
            items_summary=items_text,
            target_indices=indices,
        )

        return await self.ask_llm(prompt, self.system_prompt())

    # ============================================================
    # 处理: 查看详情
    # ============================================================

    async def _handle_detail(
        self,
        session: Session,
        user_message: str,
        route_data: dict,
    ) -> str:
        """查看某个商品的详细信息"""
        target_index = route_data.get("target_item_index", 1)
        item = session.get_item_by_index(target_index)

        if item is None:
            return f"抱歉，没有找到第 {target_index} 个商品。要不要重新搜索？"

        # 如果有分析结果，从中找到该商品的评分
        score_info = ""
        if session.search_context and session.search_context.analysis:
            for rec in session.search_context.analysis.recommendations:
                if rec.title == item.title:
                    score_info = f"\n性价比评分: {rec.score}/100\n折扣率: {rec.discount_rate:.0%}\n评价: {rec.reason}"
                    break

        detail_prompt = f"""用户想了解第 {target_index} 个商品的详细信息。

商品信息:
- 标题: {item.title}
- 价格: ¥{item.price}
- 成色: {item.condition or '未知'}
- 卖家信用: {item.seller_credit or '未知'}
- 发货地: {item.location or '未知'}
- 链接: {item.listing_url or '未知'}
{score_info}

请用自然对话的语气回复用户，重点分析这个商品值不值得买，有什么风险要注意。"""

        return await self.ask_llm(detail_prompt, self.system_prompt())

    # ============================================================
    # 处理: 闲聊
    # ============================================================

    async def _handle_general_chat(self, session: Session, user_message: str) -> str:
        """普通闲聊或咨询"""
        if session.message_count <= 1:
            # 首次对话且不是搜索 → 打招呼
            return await self.ask_llm(GREETING_PROMPT, self.system_prompt(), max_tokens=300)

        prompt = GENERAL_CHAT_PROMPT.format(
            conversation_history=self._format_history(session),
            user_message=user_message,
        )
        return await self.ask_llm(prompt, self.system_prompt())

    # ============================================================
    # 工具方法
    # ============================================================

    def _format_history(self, session: Session, max_messages: int = 10) -> str:
        """格式化对话历史为文本"""
        lines = []
        for m in session.messages[-max_messages:]:
            role_name = "用户" if m.role == "user" else "助手"
            lines.append(f"{role_name}: {m.content[:200]}")
        return "\n".join(lines)