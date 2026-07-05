"""
catch_fish — 应用入口

用法:
    # A2A 分布式模式（需先启动 Agent 服务）
    python -m src.main

    # 单进程模式（所有 Agent 在进程内直接调用）
    python -m src.main --standalone

    # 开发模式（热重载）
    python -m src.main --standalone --reload
"""

import argparse
import os
import sys

import uvicorn

from src.config import settings
from src.gateway.server import create_app


def main():
    parser = argparse.ArgumentParser(
        description="catch_fish — 闲鱼商品获取与性价比分析系统",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="单进程模式：所有 Agent 在进程内直接调用（不依赖外部 A2A 服务）",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="启用热重载（开发用）",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=settings.api_host,
        help=f"监听地址（默认: {settings.api_host}）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.api_port,
        help=f"监听端口（默认: {settings.api_port}）",
    )

    args = parser.parse_args()

    # 单进程模式：禁用 A2A
    if args.standalone:
        os.environ["A2A_ENABLED"] = "false"
        print("[INFO] 单进程直接调用模式（A2A 已禁用）")
    else:
        print(f"[INFO] A2A 分布式模式")
        print(f"  Workflow:      {settings.a2a_workflow_url}")
        print(f"  Finder:        {settings.a2a_finder_url}")
        print(f"  Encyclopedia:  {settings.a2a_encyclopedia_url}")
        print(f"  Calculator:    {settings.a2a_calculator_url}")
        print(f"  请确保以上 Agent 服务已启动（python -m src.a2a.launcher）")

    app = create_app()

    uvicorn.run(
        app if not args.reload else "src.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=settings.log_level.lower(),
    )


# 模块级 app（供 uvicorn 以字符串形式引用，如 --reload 模式）
app = create_app()

if __name__ == "__main__":
    main()
