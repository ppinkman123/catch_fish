"""
会话管理器 — 管理多轮对话的上下文和生命周期

支持:
- 内存存储（开发/测试）
- Redis 存储（生产，待接入）
- 自动过期清理
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from src.models.schemas import SearchResultResponse
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 会话默认有效期
SESSION_TTL = timedelta(hours=2)


@dataclass
class ConversationMessage:
    """单条对话消息"""
    role: str          # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)  # 可附加 agent 进度等

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_llm_format(self) -> dict:
        """转为 LLM API 接受的格式"""
        return {"role": self.role, "content": self.content}


@dataclass
class Session:
    """
    一个对话会话

    生命周期:
    1. 用户首次发起聊天 → 创建 session
    2. 每轮对话追加 messages
    3. 搜索完成后绑定 search_context
    4. 超时未活跃 → 自动清理
    """
    session_id: str
    messages: list[ConversationMessage] = field(default_factory=list)

    # 当前搜索上下文（用于追问时引用）
    search_context: Optional[SearchResultResponse] = None
    search_query: Optional[str] = None        # 最后一次搜索的原始 query

    # 元信息
    created_at: datetime = field(default_factory=datetime.now)
    last_active: datetime = field(default_factory=datetime.now)
    ttl: timedelta = SESSION_TTL

    def add_message(self, role: str, content: str, **metadata) -> ConversationMessage:
        """添加一条对话记录"""
        msg = ConversationMessage(role=role, content=content, metadata=metadata)
        self.messages.append(msg)
        self.last_active = datetime.now()
        return msg

    def bind_search_result(self, query: str, result: SearchResultResponse):
        """绑定搜索结果到会话，供后续追问使用"""
        self.search_query = query
        self.search_context = result
        logger.info(f"[{self.session_id}] 搜索结果已绑定: {query}")

    @property
    def has_search_context(self) -> bool:
        return self.search_context is not None

    @property
    def is_expired(self) -> bool:
        return datetime.now() - self.last_active > self.ttl

    @property
    def message_count(self) -> int:
        return len(self.messages)

    def get_history_for_llm(self, max_messages: int = 20) -> list[dict]:
        """获取最近 N 条消息，转为 LLM 格式"""
        recent = self.messages[-max_messages:]
        return [m.to_llm_format() for m in recent]

    def get_item_by_index(self, index: int):
        """通过序号获取搜索上下文中的商品（用户常说'第三个'）"""
        if not self.search_context or not self.search_context.xianyu_items:
            return None
        items = self.search_context.xianyu_items
        if 1 <= index <= len(items):
            return items[index - 1]
        return None

    def to_summary(self) -> dict:
        return {
            "session_id": self.session_id,
            "message_count": self.message_count,
            "has_search_context": self.has_search_context,
            "search_query": self.search_query,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
        }


class SessionManager:
    """
    会话管理器

    用法:
        manager = SessionManager()
        session = manager.create()
        session.add_message("user", "帮我看看 iPhone 15 Pro")
        ...
        manager.get(session_id)  # 恢复会话
    """

    def __init__(self):
        self._store: dict[str, Session] = {}

    def create(self, session_id: Optional[str] = None) -> Session:
        """创建新会话"""
        sid = session_id or str(uuid.uuid4())[:8]
        session = Session(session_id=sid)
        self._store[sid] = session
        logger.info(f"会话创建: {sid}")
        return session

    def get(self, session_id: str) -> Optional[Session]:
        """获取会话，自动检查过期"""
        session = self._store.get(session_id)
        if session is None:
            return None
        if session.is_expired:
            self.delete(session_id)
            return None
        return session

    def get_or_create(self, session_id: Optional[str] = None) -> Session:
        """获取已有会话，不存在则创建"""
        if session_id:
            existing = self.get(session_id)
            if existing:
                return existing
        return self.create(session_id)

    def delete(self, session_id: str):
        """删除会话"""
        if session_id in self._store:
            del self._store[session_id]
            logger.info(f"会话删除: {session_id}")

    def cleanup_expired(self) -> int:
        """清理所有过期会话，返回清理数量"""
        expired = [
            sid for sid, s in self._store.items() if s.is_expired
        ]
        for sid in expired:
            del self._store[sid]
        if expired:
            logger.info(f"清理过期会话: {len(expired)} 个")
        return len(expired)

    @property
    def active_count(self) -> int:
        return len(self._store)


# 全局单例
session_manager = SessionManager()
