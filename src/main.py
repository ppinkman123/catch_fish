"""
catch_fish — 应用入口
"""

import uvicorn

from src.config import settings
from src.gateway.server import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )
