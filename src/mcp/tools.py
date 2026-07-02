"""
闲鱼 MCP 工具定义

MCP Tool 是对闲鱼平台能力的封装，供 Finder Agent 调用。
使用 MCP (Model Context Protocol) 标准协议。
"""

from typing import Any, Optional

from mcp.types import Tool
from pydantic import BaseModel, Field


# ============================================================
# 工具输入模型
# ============================================================

class SearchItemsInput(BaseModel):
    """搜索闲鱼商品"""
    keyword: str = Field(description="搜索关键词，如 'iPhone 15 Pro 256G'")
    min_price: Optional[float] = Field(None, description="最低价格筛选")
    max_price: Optional[float] = Field(None, description="最高价格筛选")
    location: Optional[str] = Field(None, description="地区筛选，如 '北京'")
    sort_by: str = Field(
        "default",
        description="排序方式: default / price_asc / price_desc / credit / newest"
    )
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


class GetItemDetailInput(BaseModel):
    """获取闲鱼商品详情"""
    item_id: str = Field(description="闲鱼商品 ID")


class GetSellerInfoInput(BaseModel):
    """获取卖家信息"""
    seller_id: str = Field(description="卖家 ID")


# ============================================================
# MCP Tool 注册表
# ============================================================

XIANYU_TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_items",
        "description": "在闲鱼平台搜索二手商品列表。支持按关键词、价格区间、地区等条件筛选。返回商品标题、价格、成色、卖家信用、链接等信息。",
        "input_schema": SearchItemsInput,
        "handler": "handle_search_items",
    },
    {
        "name": "get_item_detail",
        "description": "获取单个闲鱼商品的详细信息，包括完整描述、所有图片、卖家信息、浏览数和想要数。",
        "input_schema": GetItemDetailInput,
        "handler": "handle_get_item_detail",
    },
    {
        "name": "get_seller_info",
        "description": "获取卖家的信用评分、历史评价、实名认证状态等信息，用于评估交易风险。",
        "input_schema": GetSellerInfoInput,
        "handler": "handle_get_seller_info",
    },
]


def get_tool_definitions() -> list[Tool]:
    """获取所有 MCP 工具定义（标准 MCP Tool 格式）"""
    tools = []
    for t in XIANYU_TOOLS:
        schema = t["input_schema"]
        # 从 Pydantic 模型生成 JSON Schema
        input_schema = schema.model_json_schema()
        tools.append(Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=input_schema,
        ))
    return tools
