"""
MOSS-AI 错误日志专用配置

专门记录应用程序的错误和警告信息到独立的日志文件
日志文件存储在 logs/error/ 目录下，按天轮转
"""

from pathlib import Path
from functools import lru_cache

from loguru import logger as loguru_logger


class ErrorLogger:
    """错误日志专用记录器"""
    
    def __init__(self):
        self._setup_error_logger()
    
    def _setup_error_logger(self):
        """配置错误日志"""
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.parent
        
        # 创建错误日志目录
        error_log_dir = project_root / "logs" / "error"
        error_log_dir.mkdir(parents=True, exist_ok=True)
        
        # 错误日志文件路径（按日期命名）
        error_log_file = error_log_dir / "error_{time:YYYY-MM-DD}.log"
        
        # 添加错误日志文件处理器（只记录WARNING及以上级别）
        loguru_logger.add(
            str(error_log_file),
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            ),
            level="WARNING",   # 只记录WARNING、ERROR、CRITICAL
            rotation="00:00",  # 每天午夜轮转
            retention=None,    # 不自动删除，由清理服务统一管理
            compression="gz",  # 轮转后压缩
            enqueue=True,      # 线程安全
            backtrace=True,    # 记录完整的traceback
            diagnose=True,     # 详细的诊断信息
            filter=lambda record: record["level"].no >= 30,  # WARNING(30)及以上
        )


@lru_cache()
def setup_error_logging():
    """设置错误日志（单例）"""
    ErrorLogger()
    return True


# 在应用启动时自动初始化
_error_logging_initialized = False

def ensure_error_logging():
    """确保错误日志已初始化"""
    global _error_logging_initialized
    if not _error_logging_initialized:
        setup_error_logging()
        _error_logging_initialized = True

