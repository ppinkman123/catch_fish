"""
数据库连接管理 — SQLAlchemy 异步引擎
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 延迟初始化，避免在未安装 aiomysql 时导入即报错
_engine = None
_sync_engine = None
_async_session_factory = None


class Base(DeclarativeBase):
    """SQLAlchemy ORM 基类"""
    pass


def _get_engine():
    """延迟创建异步引擎（首次调用时才真正连接数据库）"""
    global _engine, _sync_engine, _async_session_factory
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url_async,
            echo=settings.app_debug,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
        )
        _async_session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _engine


def _get_session_factory():
    """获取异步 Session 工厂"""
    _get_engine()  # 确保引擎已初始化
    return _async_session_factory


async def get_db() -> AsyncSession:
    """FastAPI 依赖注入：获取数据库会话"""
    factory = _get_session_factory()
    async with factory() as session:
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
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    global _engine, _sync_engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sync_engine = None
        _async_session_factory = None
