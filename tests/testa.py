"""
快速测试 src.utils.logger 的演示脚本
直接用 python tests/testa.py 运行
"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 搜索路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from loguru import logger
from src.utils.logger import get_logger




log = get_logger("ceshi")

print(f"logger 对象: {log}")
print(f"logger 类型: {type(log)}")

log.info("这是一条 INFO 日志")
log.warning("这是一条 WARNING 日志")