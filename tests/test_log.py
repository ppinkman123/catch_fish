"""
src.utils.logger 单元测试
"""

import io

import pytest
from loguru import logger as loguru_logger

from src.utils.logger import get_logger


@pytest.fixture(autouse=True)
def clean_logger():
    """每个测试前后清除 loguru handler，避免测试间相互干扰"""
    loguru_logger.remove()
    yield
    loguru_logger.remove()


class TestGetLogger:
    def test_returns_loguru_logger(self):
        """get_logger 返回的是 loguru 的 Logger 类型实例"""
        log = get_logger("test_module")
        assert isinstance(log, type(loguru_logger))

    def test_binds_name(self):
        """get_logger 能绑定模块名，调用 info/debug/warning/error 不抛异常"""
        log = get_logger("my_module")
        # 添加一个 sink 避免无 handler 时 loguru 发出警告
        loguru_logger.add(lambda _: None, level="DEBUG")
        log.debug("debug msg")
        log.info("info msg")
        log.warning("warning msg")
        log.error("error msg")

    def test_log_output_contains_message(self):
        """验证日志消息能正确输出到 sink"""
        sink = io.StringIO()
        loguru_logger.add(sink, format="{message}", level="DEBUG")

        log = get_logger("test_output")
        log.info("hello from test")

        output = sink.getvalue()
        assert "hello from test" in output

    def test_log_output_contains_level(self):
        """验证日志级别能正确输出到 sink"""
        sink = io.StringIO()
        loguru_logger.add(sink, format="{level}", level="DEBUG")

        log = get_logger("test_level")
        log.warning("warning msg")

        output = sink.getvalue()
        assert "WARNING" in output

    def test_log_output_contains_module_name(self):
        """验证模块名能出现在日志输出中"""
        sink = io.StringIO()
        loguru_logger.add(sink, format="{extra[name]}", level="DEBUG")

        log = get_logger("my_custom_module")
        log.info("test")

        output = sink.getvalue()
        assert "my_custom_module" in output

    def test_multiple_modules_use_different_names(self):
        """不同模块名各自绑定，互不干扰"""
        sink = io.StringIO()
        loguru_logger.add(sink, format="{extra[name]} | {message}", level="DEBUG")

        log_a = get_logger("module_a")
        log_b = get_logger("module_b")

        log_a.info("aaa")
        log_b.info("bbb")

        output = sink.getvalue()
        lines = output.strip().split("\n")
        assert "module_a | aaa" in lines[0]
        assert "module_b | bbb" in lines[1]


class TestLoggerLevel:
    def test_debug_below_info_not_output(self):
        """DEBUG 级别日志不应出现在仅 INFO 及以上的 sink 中"""
        sink = io.StringIO()
        loguru_logger.add(sink, format="{message}", level="INFO")

        log = get_logger("test_level")
        log.debug("debug msg")  # 不应该被输出
        log.info("info msg")    # 应该被输出

        output = sink.getvalue()
        assert "debug msg" not in output
        assert "info msg" in output