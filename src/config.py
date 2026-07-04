"""
catch_fish 全局配置管理
手动加载 .env 文件 + 环境变量，不依赖任何第三方库
"""

import os
from pathlib import Path
from typing import Optional


def _load_dotenv(env_file: Path) -> dict[str, str]:
    """手动解析 .env 文件，返回键值对字典"""
    values: dict[str, str] = {}
    if not env_file.is_file():
        return values
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            values[key] = value
    return values


class Settings:
    """应用配置 — 优先级: 环境变量 > .env > 默认值"""

    # 项目根目录（config.py 在 src/ 下，上两层到项目根）
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    ENV_FILE: Path = PROJECT_ROOT / ".env"

    def __init__(self):
        self._env = _load_dotenv(self.ENV_FILE)

    def _get(self, key: str, default: str = "") -> str:
        """读取配置: .env > 环境变量 > 默认值"""
        return self._env.get(key) or os.environ.get(key) or default

    def _get_int(self, key: str, default: int = 0) -> int:
        val = self._get(key, str(default))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def _get_bool(self, key: str, default: bool = True) -> bool:
        val = self._get(key, str(default).lower())
        return val.lower() in ("true", "1", "yes")

    # ---- 应用 ----
    @property
    def app_name(self) -> str:        return self._get("APP_NAME", "catch_fish")
    @property
    def app_env(self) -> str:         return self._get("APP_ENV", "development")
    @property
    def app_debug(self) -> bool:      return self._get_bool("APP_DEBUG", True)
    @property
    def log_level(self) -> str:       return self._get("LOG_LEVEL", "INFO")

    # ---- 服务 ----
    @property
    def api_host(self) -> str:        return self._get("API_HOST", "0.0.0.0")
    @property
    def api_port(self) -> int:        return self._get_int("API_PORT", 8000)

    # ---- LLM: DeepSeek (主) ----
    @property
    def deepseek_api_key(self) -> str:    return self._get("DEEPSEEK_API_KEY", "")
    @property
    def deepseek_base_url(self) -> str:   return self._get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    @property
    def deepseek_model(self) -> str:      return self._get("DEEPSEEK_MODEL", "deepseek-chat")
    @property
    def deepseek_max_tokens(self) -> int: return self._get_int("DEEPSEEK_MAX_TOKENS", 4096)

    # ---- LLM: OpenAI (备用) ----
    @property
    def openai_api_key(self) -> str:  return self._get("OPENAI_API_KEY", "")
    @property
    def openai_base_url(self) -> str: return self._get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    @property
    def openai_model(self) -> str:    return self._get("OPENAI_MODEL", "gpt-4o")

    # ---- 数据库 ----
    @property
    def mysql_host(self) -> str:     return self._get("MYSQL_HOST", "localhost")
    @property
    def mysql_port(self) -> int:     return self._get_int("MYSQL_PORT", 3306)
    @property
    def mysql_user(self) -> str:     return self._get("MYSQL_USER", "catch_fish")
    @property
    def mysql_password(self) -> str: return self._get("MYSQL_PASSWORD", "")
    @property
    def mysql_database(self) -> str: return self._get("MYSQL_DATABASE", "catch_fish")

    @property
    def database_url(self) -> str:
        return self._get(
            "DATABASE_URL",
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}",
        )

    @property
    def database_url_async(self) -> str:
        return self._get(
            "DATABASE_URL_ASYNC",
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}",
        )

    # ---- Redis ----
    @property
    def redis_host(self) -> str:     return self._get("REDIS_HOST", "localhost")
    @property
    def redis_port(self) -> int:     return self._get_int("REDIS_PORT", 6379)
    @property
    def redis_password(self) -> str: return self._get("REDIS_PASSWORD", "")
    @property
    def redis_db(self) -> int:       return self._get_int("REDIS_DB", 0)

    @property
    def redis_url(self) -> str:
        return self._get("REDIS_URL", f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}")

    # ---- 闲鱼 ----
    @property
    def xianyu_cookie(self) -> str:  return self._get("XIANYU_COOKIE", "")

    @property
    def xianyu_user_agent(self) -> str:
        return self._get(
            "XIANYU_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        )

    # ---- 请求控制 ----
    @property
    def request_timeout(self) -> int:      return self._get_int("REQUEST_TIMEOUT", 30)
    @property
    def max_retries(self) -> int:          return self._get_int("MAX_RETRIES", 3)
    @property
    def max_search_results(self) -> int:   return self._get_int("MAX_SEARCH_RESULTS", 50)
    @property
    def rate_limit_per_minute(self) -> int: return self._get_int("RATE_LIMIT_PER_MINUTE", 20)

    # ---- 代理 ----
    @property
    def scraper_proxy(self) -> Optional[str]:
        val = self._get("SCRAPER_PROXY", "")
        return val if val else None

    # ---- 环境判断 ----
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


# 单例
settings = Settings()
