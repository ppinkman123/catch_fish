"""
测试 XianyuMCPServer._handle_search_items

用法:
    python -m tests.test_xianyu
"""

import asyncio
import sys
from pathlib import Path

# 将项目根目录加入 Python 搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp.xianyu_server import XianyuMCPServer


async def main():
    server = XianyuMCPServer()

    print("=" * 60)
    print("测试 1: 搜索商品（默认参数）")
    print("=" * 60)
    result = await server._handle_search_items(keyword="iPhone 15 Pro")
    print(f"总条数: {result['total_count']}")
    print(f"当前页码: {result['page']}")
    for item in result["items"]:
        print(f"  - {item['title']} | ¥{item['price']} | {item['location']}")
    print()

    print("=" * 60)
    print("测试 2: 搜索商品（带价格区间 + 地点筛选）")
    print("=" * 60)
    result = await server._handle_search_items(
        keyword="MacBook Pro",
        min_price=3000,
        max_price=10000,
        location="上海",
        sort_by="price_asc",
        page=1,
        page_size=10,
    )
    print(f"总条数: {result['total_count']}")
    print(f"当前页码: {result['page']}")
    for item in result["items"]:
        print(f"  - {item['title']} | ¥{item['price']} | {item['location']}")

    print()
    print("=" * 60)
    print("测试 3: 获取商品详情")
    print("=" * 60)
    detail = await server._handle_get_item_detail(item_id="xy_000001")
    print(f"标题: {detail['title']}")
    print(f"价格: ¥{detail['price']}")
    print()

    print("=" * 60)
    print("测试 4: 获取卖家信息")
    print("=" * 60)
    seller = await server._handle_get_seller_info(seller_id="seller_001")
    print(f"信用分: {seller['credit_score']}")
    print(f"好评数: {seller['ratings']['good']}")


if __name__ == "__main__":
    asyncio.run(main())