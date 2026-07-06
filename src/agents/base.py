"""
Agent 基类 — 所有子 Agent 的抽象父类
提供 LLM 调用、日志、错误处理等通用能力
"""
import sys
from pathlib import Path

# 将项目根目录加入 Python 搜索路径
# __file__ = src/agents/base.py → 需要上三层才能到项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from abc import ABC, abstractmethod
from typing import Any, Optional

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from src.config import settings
from src.utils.logger import get_logger


class BaseAgent(ABC):
    """Agent 基类"""

    agent_id: str = "base"
    agent_name: str = "基础Agent"

    def __init__(self):
        self.logger = get_logger(f"agent.{self.agent_id}")
        self._client: Optional[AsyncOpenAI] = None

    @property
    def client(self) -> AsyncOpenAI:
        """延迟初始化 DeepSeek / OpenAI 客户端"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
            )
        return self._client
    
    @abstractmethod
    def system_prompt(self) -> str:
        """子类重写，返回 System Prompt"""

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
        max_tokens: int = settings.deepseek_max_tokens,
    ) -> str:
        """
        调用 LLM (DeepSeek) 并返回文本响应

        Args:
            user_message: 用户消息
            system_prompt: 系统提示词（覆盖默认）
            response_format: 可选的输出格式说明
            max_tokens: 最大 token 数

        Returns:
            LLM 文本响应
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        else:
            messages.append({"role": "system", "content": self.system_prompt()})

        messages.append({"role": "user", "content": user_message})

        if response_format:
            messages.append({
                "role": "user",
                "content": f"\n\n请严格按照以下JSON格式返回结果，不要添加其他内容:\n{response_format}"
            })

        self.logger.debug(f"[{self.agent_name}] 发送 LLM 请求, 消息长度={len(user_message)}")

        response = await self.client.chat.completions.create(
            model=settings.deepseek_model,
            max_tokens=max_tokens,
            messages=messages,
        )

        text = response.choices[0].message.content or ""
        self.logger.debug(f"[{self.agent_name}] LLM 响应长度={len(text)}")
        return text

    async def ask_llm_json(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = settings.deepseek_max_tokens,
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
        for marker in ("```json", "```"):
            if marker in text:
                start = text.index(marker) + len(marker)
                try:
                    end = text.index("```", start)
                except ValueError:
                    # 没有结尾代码块，直接从 marker 后取到末尾
                    end = len(text)
                text = text[start:end].strip()
                break

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"无法解析 LLM 返回的 JSON: {e}\n原始内容: {text[:500]}")


if __name__ == '__main__':
    import asyncio
    class ChatAgent(BaseAgent):
        agent_id = "chat"
        agent_name = "chatAgent"
        
        _client = AsyncOpenAI(
                        api_key='sk-bf009dc3988f40cba473ddaa8d3a4500',
                        base_url="https://api.deepseek.com",
                    )
  
        
        def system_prompt(self):
            return '你是用来闲聊的'
        
        async def execute(self, **kwargs):
            await asyncio.sleep(1)
            return {'app':'咸鱼'}
        
    ca = ChatAgent()
    # print(ca.clinet)
    print(ca._client)