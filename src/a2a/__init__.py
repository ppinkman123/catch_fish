"""
A2A (Agent-to-Agent) — 将单体 Agent 拆分为独立服务

架构:
  server.py  — 把 BaseAgent 包成 FastAPI app，暴露 POST /execute + GET /agent-card
  client.py  — 异步 HTTP 客户端，调用远程 Agent 并自动序列化/反序列化 Pydantic 模型

用法:
  # 服务端：每个 Agent 一个进程
  from src.a2a import create_agent_app
  app = create_agent_app(FinderAgent(mcp_client=mcp))

  # 客户端：替代原来的直接调用
  from src.a2a import A2AClient
  client = A2AClient()
  client.register("finder", "http://localhost:8001")
  data = await client.call_agent("finder", product_name="劳力士")
  result = FinderResult(**data)
"""

from src.a2a.server import create_agent_app
from src.a2a.client import A2AClient, get_client

__all__ = ["create_agent_app", "A2AClient", "get_client"]
