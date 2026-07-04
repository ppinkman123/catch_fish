"""
A2A Server — 将任意 BaseAgent 包装为独立 FastAPI 应用

每个 Agent 启动时调用 create_agent_app(agent) 即可得到一个完整的 HTTP 服务。
Agent 自身的 execute() 逻辑完全不用改。
"""

import inspect
from typing import Any, get_type_hints

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agents.base import BaseAgent
from src.utils.logger import get_logger

logger = get_logger("a2a.server")


def _build_input_schema(agent: BaseAgent) -> dict[str, dict]:
    """从 agent.execute 的签名自动推断输入参数 schema"""
    sig = inspect.signature(agent.execute)
    hints = get_type_hints(agent.execute)

    schema = {}
    for name, param in sig.parameters.items():
        # 跳过 self / **kwargs
        if name in ("self", "kwargs") or param.kind == param.VAR_KEYWORD:
            continue

        annotation = hints.get(name)
        has_default = param.default is not inspect.Parameter.empty

        # 判断是否为 Pydantic 模型
        is_pydantic = (
            annotation is not None
            and isinstance(annotation, type)
            and issubclass(annotation, BaseModel)
        )

        schema[name] = {
            "type": annotation.__name__ if is_pydantic else str(annotation or "Any"),
            "required": not has_default,
            "default": param.default if has_default else None,
            "is_pydantic_model": is_pydantic,
        }

    return schema


def _parse_params(
    params: dict[str, Any],
    input_schema: dict[str, dict],
    hints: dict[str, Any],
) -> dict[str, Any]:
    """将 JSON dict 参数还原为正确的 Python 类型（含 Pydantic 模型）"""
    parsed = {}

    for name, meta in input_schema.items():
        if name not in params:
            if meta["required"]:
                raise HTTPException(
                    status_code=422,
                    detail=f"缺少必填参数: {name}",
                )
            continue

        value = params[name]
        annotation = hints.get(name)

        # 还原 Pydantic 模型
        if meta["is_pydantic_model"] and isinstance(value, dict):
            parsed[name] = annotation(**value)
        # 还原 list[XxxModel]
        elif (
            annotation is not None
            and hasattr(annotation, "__origin__")
            and annotation.__origin__ is list
            and isinstance(value, list)
        ):
            item_type = annotation.__args__[0]
            if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                parsed[name] = [item_type(**v) if isinstance(v, dict) else v for v in value]
            else:
                parsed[name] = value
        else:
            parsed[name] = value

    return parsed


def create_agent_app(agent: BaseAgent) -> FastAPI:
    """将 BaseAgent 实例包装为独立的 FastAPI 应用

    暴露两个端点:
      POST /execute      — 调用 agent.execute(**params)，返回 JSON
      GET  /agent-card   — 返回 Agent 元信息（名称、输入/输出 schema）

    Args:
        agent: 任意 BaseAgent 子类实例

    Returns:
        FastAPI app

    Example:
        from src.agents.finder.agent import FinderAgent
        from src.a2a import create_agent_app

        agent = FinderAgent(mcp_client=...)
        app = create_agent_app(agent)

        # 启动:
        # uvicorn app:app --port 8001
    """
    app = FastAPI(
        title=f"A2A Agent: {agent.agent_name}",
        description=agent.__doc__ or "",
        version="0.1.0",
    )

    # 预计算 schema（启动时做一次，不在每次请求时重复）
    input_schema = _build_input_schema(agent)
    hints = get_type_hints(agent.execute)
    return_type = hints.get("return")

    output_type_name = (
        return_type.__name__
        if return_type and isinstance(return_type, type)
        else str(return_type or "Any")
    )

    @app.post("/execute")
    async def execute(body: dict[str, Any]):
        """执行 Agent

        Request:
            {"params": {"product_name": "劳力士", ...}}

        Response:
            Agent.execute() 的返回值（Pydantic model → JSON）
        """
        params = body.get("params", {})

        parsed_params = _parse_params(params, input_schema, hints)

        logger.info(
            f"[{agent.agent_id}] 收到请求: "
            f"{', '.join(f'{k}={type(v).__name__}' for k, v in parsed_params.items())}"
        )

        try:
            result = await agent.execute(**parsed_params)
        except Exception as e:
            logger.error(f"[{agent.agent_id}] 执行失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

        # 序列化返回值
        if isinstance(result, BaseModel):
            return result.model_dump(mode="json")
        return result

    @app.get("/agent-card")
    async def agent_card():
        """返回 Agent 元信息（符合 Google A2A AgentCard 规范的基本结构）"""
        return {
            "name": agent.agent_id,
            "display_name": agent.agent_name,
            "description": agent.__doc__ or "",
            "endpoint": "/execute",
            "input_schema": {
                name: {
                    "type": meta["type"],
                    "required": meta["required"],
                    "default": meta["default"],
                }
                for name, meta in input_schema.items()
            },
            "output_type": output_type_name,
        }

    return app
