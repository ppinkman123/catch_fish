"""
Chat API 路由 — SSE 流式多轮对话

POST /api/v1/chat   — 多轮对话入口（SSE 流式返回）
GET  /api/v1/chat/{session_id}/history  — 获取会话历史
GET  /api/v1/chat/{session_id}/summary  — 会话摘要
DELETE /api/v1/chat/{session_id}         — 结束会话

SSE 事件类型:
  - session:  会话信息（含 session_id、是否新会话）
  - progress: Agent 执行进度（stage + detail）
  - message:  AI 回复文本
  - result:   搜索结果 JSON（仅新搜索时）
  - error:    错误信息
  - done:     流结束标记
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from src.agents.chat.agent import ChatAgent
from src.gateway.session import Session, session_manager
from src.models.schemas import ChatRequest
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# 全局 Chat Agent
chat_agent = ChatAgent()


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    """
    多轮对话入口 — SSE 流式响应

    用法示例（curl）:
      curl -X POST http://localhost:8000/api/v1/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "iPhone 15 Pro 二手值得买吗"}'

      curl -X POST http://localhost:8000/api/v1/chat \
        -H "Content-Type: application/json" \
        -d '{"message": "第三个怎么样", "session_id": "abc123"}'
    """
    session = session_manager.get_or_create(request.session_id)

    async def event_generator():
        # ---- 1. 发送会话信息 ----
        yield {
            "event": "session",
            "data": json.dumps({
                "session_id": session.session_id,
                "is_new": session.message_count == 0,
            }, ensure_ascii=False),
        }

        # 记录用户消息
        session.add_message("user", request.message)

        # ---- 2. 用 Queue 桥接进度回调 ----
        progress_queue: asyncio.Queue = asyncio.Queue()

        async def push_progress(stage: str, detail: str):
            """Agent 内部调用，将进度推入队列"""
            await progress_queue.put({"stage": stage, "detail": detail})

        # ---- 3. 并行: 处理消息 + 推送进度 ----
        reply: str = ""
        error_msg: str | None = None

        async def run_agent():
            nonlocal reply, error_msg
            try:
                reply = await chat_agent.handle_message(
                    session=session,
                    user_message=request.message,
                    on_progress=push_progress,
                )
            except Exception as e:
                logger.error(f"Agent 处理失败: {e}")
                error_msg = str(e)[:500]

        agent_task = asyncio.create_task(run_agent())

        # 消费进度队列，推送到 SSE
        while not agent_task.done():
            try:
                progress = await asyncio.wait_for(progress_queue.get(), timeout=0.3)
                yield {
                    "event": "progress",
                    "data": json.dumps(progress, ensure_ascii=False),
                }
            except asyncio.TimeoutError:
                # 检查客户端连接
                if await http_request.is_disconnected():
                    agent_task.cancel()
                    return
                continue

        # 确保 agent 任务完成
        await agent_task

        # ---- 4. 发送结果 ----
        if error_msg:
            yield {
                "event": "error",
                "data": json.dumps({"error": error_msg}, ensure_ascii=False),
            }
        else:
            yield {
                "event": "message",
                "data": json.dumps({
                    "reply": reply,
                    "session_id": session.session_id,
                }, ensure_ascii=False),
            }

            # 如果触发了新搜索，推送结构化结果
            if session.has_search_context:
                result = session.search_context
                try:
                    result_json = result.model_dump_json()
                except (AttributeError, TypeError):
                    result_json = json.dumps(str(result), ensure_ascii=False)
                yield {
                    "event": "result",
                    "data": result_json,
                }

        # ---- 5. 结束标记 ----
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_generator())


@router.get("/chat/{session_id}/history")
async def get_chat_history(session_id: str):
    """获取完整会话历史"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")

    return {
        "session_id": session_id,
        "messages": [m.to_dict() for m in session.messages],
        "search_context": _serialize_context(session),
    }


@router.get("/chat/{session_id}/summary")
async def get_session_summary(session_id: str):
    """获取会话摘要"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    return session.to_summary()


@router.delete("/chat/{session_id}")
async def end_session(session_id: str):
    """结束并清理会话"""
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    session_manager.delete(session_id)
    return {"status": "deleted", "session_id": session_id}


@router.get("/chat/sessions")
async def list_active_sessions():
    """列出所有活跃会话（管理用）"""
    session_manager.cleanup_expired()
    return {
        "active_count": session_manager.active_count,
        "sessions": [
            s.to_summary()
            for sid, s in session_manager._store.items()
        ],
    }


def _serialize_context(session: Session) -> dict | None:
    """安全序列化搜索上下文"""
    ctx = session.search_context
    if ctx is None:
        return None
    try:
        return ctx.model_dump()
    except (AttributeError, TypeError):
        return {"error": "无法序列化"}
