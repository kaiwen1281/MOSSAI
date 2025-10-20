"""
MOSS-AI 日志配置模块

配置结构化日志，支持：
1. 应用日志：logs/app/ 目录，按天轮转
2. 错误日志：logs/error/ 目录，按天轮转
3. 自动压缩：昨天的日志自动压缩为 .gz
4. 自动清理：超过7天的日志自动删除
"""

import sys
import logging
from pathlib import Path
from typing import Any
from functools import lru_cache

from loguru import logger as loguru_logger


def _get_settings():
    """延迟导入配置，避免循环依赖"""
    try:
        from app.core.config import settings
        return settings
    except ImportError:
        # 如果配置不可用，使用默认值
        class DefaultSettings:
            LOG_LEVEL = "INFO"
            DEBUG = False
        return DefaultSettings()


class InterceptHandler(logging.Handler):
    """拦截标准logging并重定向到Loguru"""
    
    def emit(self, record: logging.LogRecord) -> None:
        # 获取对应的Loguru级别
        try:
            level = loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 找到日志消息的调用者
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        loguru_logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_file_logging() -> None:
    """设置文件日志，支持按天轮转和自动压缩"""
    settings = _get_settings()
    
    # 获取项目根目录
    project_root = Path(__file__).parent.parent.parent  # app/core/logging.py -> project root
    
    # 创建应用日志目录
    app_log_dir = project_root / "logs" / "app"
    app_log_dir.mkdir(parents=True, exist_ok=True)
    
    # 应用日志文件路径（按日期命名）
    app_log_file = app_log_dir / "mossai_{time:YYYY-MM-DD}.log"
    
    # 日志格式
    format_str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # 添加文件处理器，按天轮转
    loguru_logger.add(
        str(app_log_file),
        format=format_str,
        level=getattr(settings, 'LOG_LEVEL', 'INFO'),
        rotation="00:00",    # 每天午夜轮转，生成新的日志文件
        retention=None,      # 不自动删除，由定时清理服务统一管理
        compression="gz",    # 轮转后压缩为 .gz 格式
        enqueue=True,        # 线程安全
        backtrace=True,      # 记录完整的traceback
        diagnose=True,       # 详细的诊断信息
    )


def setup_console_logging() -> None:
    """设置控制台日志"""
    settings = _get_settings()
    
    # 移除默认处理器
    loguru_logger.remove()
    
    # 人类可读的格式
    format_str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan> | "
        "<level>{message}</level>"
    )
    
    # 添加控制台处理器
    loguru_logger.add(
        sys.stdout,
        format=format_str,
        level=getattr(settings, 'LOG_LEVEL', 'INFO'),
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=getattr(settings, 'DEBUG', False),
    )


def setup_third_party_logging() -> None:
    """设置第三方库的日志级别"""
    # 拦截标准库日志
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # 设置特定库的日志级别（减少噪音）
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    
    # 在生产环境禁用访问日志
    settings = _get_settings()
    if not getattr(settings, 'DEBUG', False):
        logging.getLogger("uvicorn.access").disabled = True


@lru_cache()
def setup_logging() -> Any:
    """设置完整的日志配置（缓存）"""
    # 设置控制台日志
    setup_console_logging()
    
    # 设置文件日志
    setup_file_logging()
    
    # 设置错误日志（独立的错误日志）
    from app.core.error_logging import setup_error_logging
    setup_error_logging()
    
    # 设置第三方库日志
    setup_third_party_logging()
    
    logger = loguru_logger.bind()
    
    # 记录启动消息
    settings = _get_settings()
    logger.info(f"🚀 MOSS-AI 日志系统已配置 - Level: {getattr(settings, 'LOG_LEVEL', 'INFO')}")
    
    # 显示实际日志文件路径
    project_root = Path(__file__).parent.parent.parent
    actual_log_path = str(project_root / "logs" / "app" / "mossai_{time:YYYY-MM-DD}.log")
    logger.info(f"📁 App Log: {actual_log_path}")
    
    return logger


# 便捷函数
def get_logger(name: str = __name__) -> Any:
    """获取指定模块的logger实例"""
    return loguru_logger.bind(name=name)


# 导出主logger
mossai_logger = setup_logging()

