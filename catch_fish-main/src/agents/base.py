"""
Agent 基类 — 所有子 Agent 的抽象父类
提供 LLM 调用、日志、错误处理等通用能力
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.utils.logger import get_logger


class BaseAgent(ABC):
    """Agent 基类"""

    agent_id: str = "base"
    agent_name: str = "基础Agent"

    def __init__(self):
        self.logger = get_logger(f"agent.{self.agent_id}")
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        """延迟初始化 Anthropic 客户端"""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(
                api_key=settings.anthropic_api_key,
                base_url=settings.anthropic_base_url,
            )
        return self._client

    def system_prompt(self) -> str:
        """子类重写，返回 System Prompt"""
        return "你是一个专业的AI助手。"

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """子类必须实现的执行入口"""
        ...

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=2, max=30),
    )
    async def ask_llm(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[str] = None,
        max_tokens: int = settings.anthropic_max_tokens,
    ) -> str:
        """
        调用 LLM (Claude) 并返回文本响应

        Args:
            user_message: 用户消息
            system_prompt: 系统提示词（覆盖默认）
            response_format: 可选的输出格式说明
            max_tokens: 最大 token 数

        Returns:
            LLM 文本响应
        """
        messages = [{"role": "user", "content": user_message}]

        if response_format:
            messages.append({
                "role": "user",
                "content": f"\n\n请严格按照以下JSON格式返回结果，不要添加其他内容:\n{response_format}"
            })

        self.logger.debug(f"[{self.agent_name}] 发送 LLM 请求, 消息长度={len(user_message)}")

        response = await self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system_prompt or self.system_prompt(),
            messages=messages,
        )

        text = response.content[0].text
        self.logger.debug(f"[{self.agent_name}] LLM 响应长度={len(text)}")
        return text

    async def ask_llm_json(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = settings.anthropic_max_tokens,
    ) -> dict[str, Any]:
        """
        调用 LLM 并解析 JSON 响应

        Args:
            user_message: 用户消息
            system_prompt: 系统提示词
            max_tokens: 最大 token

        Returns:
            解析后的 dict
        """
        text = await self.ask_llm(
            user_message=user_message,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        return self._parse_json(text)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """从 LLM 响应中提取 JSON"""
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 markdown 代码块中提取
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            text = text[start:end].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析 LLM 返回的 JSON: {e}\n原始内容: {text[:500]}")
