"""
catch_fish 全局配置管理
基于 pydantic-settings，自动从 .env 文件和环境变量加载
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "catch_fish"
    app_env: str = "development"
    app_debug: bool = True
    log_level: str = "INFO"

    # ---- 服务 ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ---- LLM: DeepSeek (主) ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_tokens: int = 4096

    # ---- LLM: OpenAI (备用) ----
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    # ---- 数据库 ----
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "catch_fish"
    mysql_password: str = ""
    mysql_database: str = "catch_fish"
    database_url: str = "mysql+pymysql://catch_fish:dev@localhost:3306/catch_fish"
    database_url_async: str = "mysql+aiomysql://catch_fish:dev@localhost:3306/catch_fish"

    # ---- Redis ----
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_url: str = "redis://localhost:6379/0"

    # ---- 闲鱼 ----
    xianyu_cookie: str = ""
    xianyu_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )

    # ---- 请求控制 ----
    request_timeout: int = 30
    max_retries: int = 3
    max_search_results: int = 50
    rate_limit_per_minute: int = 20

    # ---- 代理 ----
    scraper_proxy: Optional[str] = None

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 单例
settings = Settings()
