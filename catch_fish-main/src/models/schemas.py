"""
Pydantic 数据模型 — API 请求/响应、Agent 间通信
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 通用
# ============================================================

class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = "ok"
    version: str = "0.1.0"
    service: str = "catch_fish"


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    detail: Optional[str] = None
    search_id: Optional[str] = None


# ============================================================
# 搜索请求 / 响应
# ============================================================

class SearchRequest(BaseModel):
    """用户发起搜索请求"""
    query: str = Field(..., description="自然语言搜索，如 'iPhone 15 Pro 256G 黑色 二手值得买吗'")
    budget_min: Optional[float] = Field(None, ge=0, description="最低预算")
    budget_max: Optional[float] = Field(None, ge=0, description="最高预算")
    condition: Optional[str] = Field("all", description="成色偏好: all / like_new / good / acceptable")
    location: Optional[str] = Field(None, description="地区筛选")


class SearchAcceptedResponse(BaseModel):
    """搜索请求已接受"""
    search_id: str
    status: str = "accepted"
    estimated_seconds: int = 30


class TaskProgress(BaseModel):
    """单个子任务进度"""
    status: str = "pending"  # pending / running / done / failed
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None


class SearchStatusResponse(BaseModel):
    """搜索任务状态"""
    search_id: str
    status: str  # orchestrating / searching / fetching_info / calculating / completed / failed
    progress: dict[str, TaskProgress] = Field(default_factory=dict)
    created_at: datetime


# ============================================================
# Orchestrator 意图解析
# ============================================================

class ParsedIntent(BaseModel):
    """Orchestrator 解析的用户意图"""
    product_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    specs: dict[str, str] = Field(default_factory=dict)
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    condition_preference: Optional[str] = None
    location: Optional[str] = None


# ============================================================
# Finder Agent（商品搜索）
# ============================================================

class XianyuItemOut(BaseModel):
    """闲鱼商品"""
    xianyu_item_id: Optional[str] = None
    title: str
    price: float
    original_price: Optional[float] = None
    condition: Optional[str] = None
    seller_credit: Optional[int] = None
    location: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    listing_url: Optional[str] = None
    listed_time: Optional[datetime] = None


class FinderResult(BaseModel):
    """Finder Agent 输出"""
    items: list[XianyuItemOut]
    total_count: int
    search_keyword: str
    searched_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# Encyclopedia Agent（商品百科）
# ============================================================

class ChannelPrice(BaseModel):
    """单个渠道的价格"""
    channel: str         # official / jd / tmall / pdd
    price: float
    url: Optional[str] = None
    in_stock: bool = True


class EncyclopediaResult(BaseModel):
    """Encyclopedia Agent 输出"""
    product_name: str
    brand: Optional[str] = None
    model: Optional[str] = None
    specs: dict[str, str] = Field(default_factory=dict)
    new_prices: list[ChannelPrice] = Field(default_factory=list)
    lowest_new_price: Optional[float] = None
    release_date: Optional[str] = None
    rating: Optional[float] = None
    warranty: Optional[str] = None
    source_urls: list[str] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=datetime.now)


# ============================================================
# Calculator Agent（性价比分析）
# ============================================================

class Recommendation(BaseModel):
    """单个推荐"""
    title: str
    price: float
    new_price: float
    discount_rate: float = Field(..., description="折扣率，如 0.65 表示便宜 35%")
    score: int = Field(..., ge=0, le=100, description="性价比评分")
    reason: str
    listing_url: Optional[str] = None
    condition: Optional[str] = None


class MarketSummary(BaseModel):
    """市场总结"""
    avg_used_price: float
    price_range: dict[str, float]  # {"min": 100, "max": 500}
    total_listings: int
    recommendation: str  # "buy_used" / "buy_new" / "consider"


class CalculatorResult(BaseModel):
    """Calculator Agent 输出"""
    best_deal: Optional[Recommendation] = None
    recommendations: list[Recommendation] = Field(default_factory=list)
    new_product_baseline: Optional[ChannelPrice] = None
    market_summary: MarketSummary
    verdict: str  # AI 生成的综合结论文案


# ============================================================
# 最终结果（给用户）
# ============================================================

class SearchResultResponse(BaseModel):
    """完整的搜索结果"""
    search_id: str
    query: str
    product_info: EncyclopediaResult
    xianyu_items: list[XianyuItemOut]
    analysis: CalculatorResult
    completed_at: datetime


# ============================================================
# 多轮对话 (Chat)
# ============================================================

class ChatRequest(BaseModel):
    """用户发送对话消息"""
    message: str = Field(..., description="用户消息", min_length=1)
    session_id: Optional[str] = Field(None, description="会话ID，新会话可不传")


class ChatResponse(BaseModel):
    """对话响应（非流式）"""
    session_id: str
    reply: str
    intent: Optional[str] = None
    search_result: Optional[SearchResultResponse] = None


class SessionInfo(BaseModel):
    """会话摘要信息"""
    session_id: str
    message_count: int
    has_search_context: bool
    search_query: Optional[str] = None
    created_at: str
    last_active: str


class SSEProgressEvent(BaseModel):
    """SSE 进度事件"""
    event: str          # "progress" | "message" | "result" | "error" | "done"
    stage: Optional[str] = None    # orchestrating / searching / calculating / completed
    detail: Optional[str] = None   # 进度描述
    data: Optional[dict] = None    # 附加数据
