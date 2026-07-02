"""
A2A Gateway — FastAPI 应用工厂
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.gateway.chat_router import router as chat_router
from src.gateway.middleware import setup_middleware
from src.gateway.router import router
from src.models.database import close_db, init_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info("=" * 50)
    logger.info("  catch_fish — 闲鱼商品获取与性价比分析系统")
    logger.info("  A2A Gateway 启动中...")
    logger.info("=" * 50)

    # 初始化数据库（可选，Docker 环境下 MySQL 可能未就绪）
    try:
        await init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化失败（可能是 MySQL 未就绪）: {e}")

    yield

    # 关闭
    await close_db()
    logger.info("catch_fish 已关闭")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title="catch_fish - A2A Gateway",
        description="闲鱼商品获取与性价比分析系统 — Agent-to-Agent 网关",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # 注册中间件
    setup_middleware(app)

    # 注册路由
    app.include_router(router)
    app.include_router(chat_router)

    return app
