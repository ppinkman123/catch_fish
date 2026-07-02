"""
数据库连接管理 — SQLAlchemy 异步引擎
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

# 异步引擎
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.app_debug,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
)

# 同步引擎（用于 Alembic 迁移等场景）
sync_engine = None  # 按需创建

# 异步 Session 工厂
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy ORM 基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
