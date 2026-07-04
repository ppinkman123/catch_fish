"""
SQLAlchemy ORM 模型定义
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.database import Base


class SearchLog(Base):
    """搜索记录表"""

    __tablename__ = "search_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False, comment="用户原始查询")
    parsed_intent: Mapped[dict | None] = mapped_column(JSON, comment="Orchestrator 解析后的意图")
    status: Mapped[str] = mapped_column(
        Enum("pending", "processing", "completed", "failed", name="search_status"),
        default="pending",
    )
    error_message: Mapped[str | None] = mapped_column(Text, comment="错误信息")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), comment="更新时间"
    )

    # 关联
    xianyu_items: Mapped[list["XianyuItem"]] = relationship(back_populates="search", lazy="selectin")
    analysis: Mapped["AnalysisResult | None"] = relationship(back_populates="search", uselist=False)

    __table_args__ = (
        Index("idx_session_created", "session_id", "created_at"),
        {"comment": "搜索记录表"},
    )


class XianyuItem(Base):
    """闲鱼商品快照表"""

    __tablename__ = "xianyu_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("search_log.id", ondelete="CASCADE"), nullable=False
    )
    xianyu_item_id: Mapped[str | None] = mapped_column(String(64), comment="闲鱼商品ID")
    title: Mapped[str | None] = mapped_column(String(500), comment="商品标题")
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), comment="售价")
    original_price: Mapped[float | None] = mapped_column(Numeric(10, 2), comment="原价")
    condition: Mapped[str | None] = mapped_column(String(50), comment="成色")
    seller_credit: Mapped[int | None] = mapped_column(Integer, comment="卖家信用分")
    location: Mapped[str | None] = mapped_column(String(100), comment="发货地")
    images: Mapped[list | None] = mapped_column(JSON, comment="图片URL列表")
    listing_url: Mapped[str | None] = mapped_column(String(500), comment="商品链接")
    listed_time: Mapped[datetime | None] = mapped_column(DateTime, comment="发布时间")
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="快照时间"
    )

    # 关联
    search: Mapped["SearchLog"] = relationship(back_populates="xianyu_items")

    __table_args__ = (
        Index("idx_search_price", "search_id", "price"),
        {"comment": "闲鱼商品快照表"},
    )


class ProductCache(Base):
    """商品百科缓存表"""

    __tablename__ = "product_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_name: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    brand: Mapped[str | None] = mapped_column(String(100), comment="品牌")
    model: Mapped[str | None] = mapped_column(String(100), comment="型号")
    specs: Mapped[dict | None] = mapped_column(JSON, comment="规格参数")
    new_prices: Mapped[dict | None] = mapped_column(JSON, comment="各渠道新品价格")
    release_date: Mapped[datetime | None] = mapped_column(DateTime, comment="上市时间")
    rating: Mapped[float | None] = mapped_column(Float, comment="评分")
    warranty: Mapped[str | None] = mapped_column(String(500), comment="保修说明")
    source_urls: Mapped[list | None] = mapped_column(JSON, comment="数据来源URL")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="抓取时间"
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, comment="缓存过期时间")

    __table_args__ = (
        Index("idx_expires", "expires_at"),
        {"comment": "商品百科缓存表"},
    )


class AnalysisResult(Base):
    """性价比分析结果表"""

    __tablename__ = "analysis_result"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    search_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("search_log.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    best_deal_item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("xianyu_items.id", ondelete="SET NULL"), comment="最佳选择"
    )
    new_price_baseline: Mapped[float | None] = mapped_column(
        Numeric(10, 2), comment="新品基准价格"
    )
    avg_used_price: Mapped[float | None] = mapped_column(
        Numeric(10, 2), comment="二手均价"
    )
    total_listings: Mapped[int | None] = mapped_column(Integer, comment="二手在售数量")
    recommendations: Mapped[list | None] = mapped_column(JSON, comment="推荐列表")
    market_summary: Mapped[dict | None] = mapped_column(JSON, comment="市场总结")
    verdict_text: Mapped[str | None] = mapped_column(Text, comment="AI 分析结论")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), comment="创建时间"
    )

    # 关联
    search: Mapped["SearchLog"] = relationship(back_populates="analysis")
    best_deal: Mapped["XianyuItem | None"] = relationship(foreign_keys=[best_deal_item_id])

    __table_args__ = (
        Index("idx_search_result", "search_id"),
        {"comment": "性价比分析结果表"},
    )
