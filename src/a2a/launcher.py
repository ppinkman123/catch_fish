"""
A2A 启动器 — 管理多个 Agent 服务进程

用法:
    # 启动全部 Agent 服务（A2A 分布式模式）
    python -m src.a2a.launcher

    # 启动单个服务
    python -m src.a2a.launcher --service finder
    python -m src.a2a.launcher --service workflow

    # 开发模式（单进程，走直接调用，无需启动外部服务）
    python -m src.a2a.launcher --dev

服务端口分配:
    Workflow:      8001
    Finder:        8002
    Encyclopedia:  8003
    Calculator:    8004
"""

import argparse
import multiprocessing
import os
import signal
import sys
import time

import uvicorn

from src.config import settings
from src.utils.logger import get_logger

logger = get_logger("a2a.launcher")

# 服务定义: (name, port, factory)
SERVICES = {
    "workflow": {
        "port": 8001,
        "env_key": "A2A_WORKFLOW_URL",
    },
    "finder": {
        "port": 8002,
        "env_key": "A2A_FINDER_URL",
    },
    "encyclopedia": {
        "port": 8003,
        "env_key": "A2A_ENCYCLOPEDIA_URL",
    },
    "calculator": {
        "port": 8004,
        "env_key": "A2A_CALCULATOR_URL",
    },
}

_processes: list[multiprocessing.Process] = []


def _run_worker(service_name: str, port: int):
    """在子进程中运行单个 Agent 服务"""
    # 设置进程名称
    multiprocessing.current_process().name = f"a2a-{service_name}"

    # 为子进程设置环境变量（确保 config 能读到正确的 URL）
    os.environ["A2A_ENABLED"] = "true"

    if service_name == "workflow":
        from src.a2a.agent_apps import create_workflow_app
        # Workflow 在 A2A 模式下需要自己的 A2A 客户端来调用子 Agent
        app = create_workflow_app(a2a_client=_create_internal_client())
    elif service_name == "finder":
        from src.a2a.agent_apps import create_finder_app
        app = create_finder_app()
    elif service_name == "encyclopedia":
        from src.a2a.agent_apps import create_encyclopedia_app
        app = create_encyclopedia_app()
    elif service_name == "calculator":
        from src.a2a.agent_apps import create_calculator_app
        app = create_calculator_app()
    else:
        raise ValueError(f"未知服务: {service_name}")

    logger.info(f"[{service_name}] 启动于端口 {port}")
    uvicorn.run(
        app,
        host=settings.api_host,
        port=port,
        log_level=settings.log_level.lower(),
    )


def _create_internal_client():
    """为 Workflow 服务创建内部 A2A 客户端，指向其他 Agent 服务"""
    from src.a2a.client import A2AClient
    client = A2AClient()
    client.register("finder", settings.a2a_finder_url)
    client.register("encyclopedia", settings.a2a_encyclopedia_url)
    client.register("calculator", settings.a2a_calculator_url)
    logger.info("Workflow 内部 A2A 客户端已注册: finder, encyclopedia, calculator")
    return client


def _signal_handler(signum, frame):
    """优雅关闭所有子进程"""
    logger.info(f"收到信号 {signum}，正在关闭所有 Agent 服务...")
    for p in _processes:
        if p.is_alive():
            p.terminate()
    for p in _processes:
        p.join(timeout=10)
        if p.is_alive():
            p.kill()
    logger.info("所有 Agent 服务已关闭")
    sys.exit(0)


def start_all():
    """启动全部 Agent 服务"""
    logger.info("=" * 50)
    logger.info("  catch_fish A2A 启动器")
    logger.info("  启动所有 Agent 服务...")
    logger.info("=" * 50)

    # 注册信号处理
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    for name, cfg in SERVICES.items():
        port = cfg["port"]
        p = multiprocessing.Process(
            target=_run_worker,
            args=(name, port),
            name=f"a2a-{name}",
            daemon=True,
        )
        p.start()
        _processes.append(p)
        logger.info(f"  [{name}] 端口 {port} — PID {p.pid}")
        time.sleep(0.5)  # 错开启动，避免端口冲突

    logger.info(f"\n全部 {len(_processes)} 个服务已启动")
    logger.info("按 Ctrl+C 停止所有服务\n")

    # 等待所有子进程
    try:
        for p in _processes:
            p.join()
    except KeyboardInterrupt:
        _signal_handler(signal.SIGINT, None)


def start_one(service_name: str):
    """启动单个 Agent 服务（前台运行）"""
    if service_name not in SERVICES:
        logger.error(f"未知服务: {service_name}，可选: {list(SERVICES.keys())}")
        sys.exit(1)

    cfg = SERVICES[service_name]
    logger.info(f"启动服务 [{service_name}] 于端口 {cfg['port']}")
    _run_worker(service_name, cfg["port"])


def start_dev():
    """开发模式：单进程运行 Gateway + 所有 Agent（直接调用模式，不通过 HTTP）"""
    os.environ["A2A_ENABLED"] = "false"

    from src.main import app
    logger.info("=" * 50)
    logger.info("  catch_fish 开发模式（单进程直接调用）")
    logger.info("  所有 Agent 在进程内运行，无需启动外部服务")
    logger.info("=" * 50)

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


def main():
    parser = argparse.ArgumentParser(
        description="catch_fish A2A 启动器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m src.a2a.launcher                  # 启动全部 Agent 服务
  python -m src.a2a.launcher --service finder # 仅启动 Finder
  python -m src.a2a.launcher --dev            # 开发模式（单进程）
        """,
    )
    parser.add_argument(
        "--service", "-s",
        type=str,
        choices=list(SERVICES.keys()),
        help="仅启动指定服务",
    )
    parser.add_argument(
        "--dev", "-d",
        action="store_true",
        help="开发模式：单进程运行（A2A_ENABLED=false）",
    )

    args = parser.parse_args()

    # 设置 multiprocessing 启动方法（Windows 兼容）
    if sys.platform == "win32":
        multiprocessing.set_start_method("spawn", force=True)

    if args.dev:
        start_dev()
    elif args.service:
        start_one(args.service)
    else:
        start_all()


if __name__ == "__main__":
    main()
