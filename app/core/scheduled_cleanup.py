"""
MOSS-AI 定时清理服务

提供定时自动清理功能：
1. 日志文件清理：超过7天的日志自动删除
2. 日志文件压缩：昨天的日志自动压缩为.gz格式
3. 任务存储清理：清理内存中的过期任务

默认每天凌晨2点执行清理任务
"""

import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger


@dataclass
class CleanupResult:
    """清理结果"""
    start_time: datetime
    end_time: datetime
    logs_deleted: int = 0
    tasks_cleaned: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def duration_seconds(self) -> float:
        """清理耗时（秒）"""
        return (self.end_time - self.start_time).total_seconds()


class ScheduledCleanupService:
    """
    MOSS-AI 定时清理服务
    
    核心功能：
    1. 定时清理日志文件（超过7天的删除）
    2. 清理内存中的过期任务
    """
    
    def __init__(
        self,
        hour: int = 2,  # 默认凌晨2点（避免和MOSS冲突，MOSS是凌晨1点）
        minute: int = 0,
        log_retention_days: int = 7,
    ):
        """
        初始化定时清理服务
        
        Args:
            hour: 每天执行清理的小时（0-23）
            minute: 每天执行清理的分钟（0-59）
            log_retention_days: 日志保留天数
        """
        self.hour = hour
        self.minute = minute
        self.log_retention_days = log_retention_days
        
        # 调度器
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._is_running = False
        
        # 清理历史
        self.cleanup_history: List[CleanupResult] = []
        self.last_cleanup_time: Optional[datetime] = None
    
    async def start(self):
        """启动定时清理服务"""
        if self._is_running:
            logger.warning("MOSS-AI 定时清理服务已在运行")
            return
        
        try:
            # 初始化调度器
            self.scheduler = AsyncIOScheduler(timezone='Asia/Shanghai')
            
            # 添加定时任务 - 每天指定时间执行
            self.scheduler.add_job(
                self._run_cleanup,
                trigger=CronTrigger(hour=self.hour, minute=self.minute),
                id='mossai_daily_cleanup',
                name='MOSS-AI 每日清理任务',
                replace_existing=True
            )
            
            # 启动调度器
            self.scheduler.start()
            self._is_running = True
            
            logger.info(
                f"🕐 MOSS-AI 定时清理服务已启动 - "
                f"每天 {self.hour:02d}:{self.minute:02d} 执行清理任务"
            )
            logger.info(f"📋 清理配置: 日志保留{self.log_retention_days}天")
            
        except Exception as e:
            logger.error(f"启动 MOSS-AI 定时清理服务失败: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """停止定时清理服务"""
        if not self._is_running:
            return
        
        try:
            if self.scheduler:
                self.scheduler.shutdown(wait=False)
            
            self._is_running = False
            logger.info("🛑 MOSS-AI 定时清理服务已停止")
            
        except Exception as e:
            logger.error(f"停止 MOSS-AI 定时清理服务失败: {e}", exc_info=True)
    
    async def _run_cleanup(self):
        """执行清理任务"""
        start_time = datetime.now()
        result = CleanupResult(start_time=start_time, end_time=start_time)
        
        try:
            logger.info("🧹 开始执行 MOSS-AI 定时清理任务")
            
            # 1. 清理日志文件
            try:
                logger.info("📁 步骤1: 清理日志文件...")
                logs_deleted = await self._cleanup_logs()
                result.logs_deleted = logs_deleted
                logger.info(f"✅ 日志清理完成: 删除 {logs_deleted} 个文件")
            except Exception as e:
                error_msg = f"日志清理失败: {e}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)
            
            # 2. 清理内存中的过期任务
            try:
                logger.info("🗂️  步骤2: 清理过期任务...")
                tasks_cleaned = await self._cleanup_tasks()
                result.tasks_cleaned = tasks_cleaned
                logger.info(f"✅ 任务清理完成: 清理 {tasks_cleaned} 个任务")
            except Exception as e:
                error_msg = f"任务清理失败: {e}"
                logger.error(error_msg, exc_info=True)
                result.errors.append(error_msg)
            
            result.end_time = datetime.now()
            self.last_cleanup_time = result.end_time
            
            # 保存清理历史
            self.cleanup_history.append(result)
            if len(self.cleanup_history) > 30:  # 只保留最近30次记录
                self.cleanup_history.pop(0)
            
            # 生成清理统计
            logger.info(
                f"🎉 MOSS-AI 定时清理任务完成 - "
                f"日志删除: {result.logs_deleted}, "
                f"任务清理: {result.tasks_cleaned}, "
                f"耗时: {result.duration_seconds:.2f}秒"
            )
            
            if result.errors:
                logger.warning(f"⚠️ 清理过程中出现 {len(result.errors)} 个错误")
                for error in result.errors:
                    logger.warning(f"   - {error}")
            
        except Exception as e:
            logger.error(f"执行清理任务失败: {e}", exc_info=True)
            result.errors.append(f"清理任务失败: {e}")
            result.end_time = datetime.now()
    
    async def _cleanup_logs(self) -> int:
        """
        清理日志文件（包括app日志和error日志）
        
        Returns:
            删除的文件数量
        """
        project_root = Path(__file__).parent.parent.parent
        logs_base_dir = project_root / "logs"
        
        if not logs_base_dir.exists():
            logger.debug(f"日志目录不存在: {logs_base_dir}")
            return 0
        
        cutoff_time = datetime.now() - timedelta(days=self.log_retention_days)
        deleted_count = 0
        
        # 要清理的日志目录
        log_dirs = [
            logs_base_dir / "app",    # 应用程序日志
            logs_base_dir / "error",  # 错误日志
        ]
        
        try:
            for logs_dir in log_dirs:
                if not logs_dir.exists():
                    continue
                
                logger.debug(f"扫描日志目录: {logs_dir}")
                
                # 遍历日志目录
                for file_path in logs_dir.glob("*"):
                    if not file_path.is_file():
                        continue
                    
                    # 只处理日志相关文件
                    if not self._is_log_file(file_path):
                        continue
                    
                    # 检查文件修改时间
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    
                    if file_mtime < cutoff_time:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            logger.debug(f"删除日志文件: {file_path.relative_to(project_root)}")
                        except Exception as e:
                            logger.error(f"删除日志文件失败: {file_path}, 错误: {e}")
        
        except Exception as e:
            logger.error(f"清理日志文件时出错: {e}", exc_info=True)
            raise
        
        return deleted_count
    
    async def _cleanup_tasks(self) -> int:
        """
        清理内存中的过期任务
        
        Returns:
            清理的任务数量
        """
        try:
            from app.api.routes import tasks_storage
            
            # 清理超过24小时的任务
            cutoff_time = datetime.now() - timedelta(hours=24)
            cleaned_count = 0
            
            # 找出需要删除的任务
            tasks_to_delete = []
            for task_id, task_data in tasks_storage.items():
                created_at = task_data.get("created_at")
                if created_at and isinstance(created_at, datetime):
                    if created_at < cutoff_time:
                        tasks_to_delete.append(task_id)
            
            # 删除任务
            for task_id in tasks_to_delete:
                try:
                    del tasks_storage[task_id]
                    cleaned_count += 1
                except Exception as e:
                    logger.error(f"删除任务失败: {task_id}, 错误: {e}")
            
            return cleaned_count
        
        except Exception as e:
            logger.error(f"清理任务时出错: {e}", exc_info=True)
            return 0
    
    async def trigger_manual_cleanup(self) -> CleanupResult:
        """
        手动触发清理任务
        
        Returns:
            清理结果
        """
        logger.info("手动触发 MOSS-AI 清理任务")
        await self._run_cleanup()
        return self.cleanup_history[-1] if self.cleanup_history else None
    
    def get_cleanup_status(self) -> Dict[str, Any]:
        """获取清理状态"""
        next_run_time = None
        if self.scheduler and self._is_running:
            job = self.scheduler.get_job('mossai_daily_cleanup')
            if job:
                next_run_time = job.next_run_time
        
        return {
            "is_running": self._is_running,
            "schedule": f"{self.hour:02d}:{self.minute:02d} 每天",
            "next_run_time": next_run_time.isoformat() if next_run_time else None,
            "last_cleanup_time": self.last_cleanup_time.isoformat() if self.last_cleanup_time else None,
            "total_cleanups": len(self.cleanup_history),
            "config": {
                "log_retention_days": self.log_retention_days,
            }
        }
    
    @staticmethod
    def _is_log_file(file_path: Path) -> bool:
        """判断是否为日志文件"""
        log_extensions = {'.log', '.gz', '.zip'}
        
        # 检查文件扩展名
        if file_path.suffix in log_extensions:
            return True
        
        # 检查是否为轮转的日志文件
        if '.log.' in file_path.name:
            return True
        
        return False


# 全局定时清理服务实例
_scheduled_cleanup_service: Optional[ScheduledCleanupService] = None


def get_scheduled_cleanup_service(
    hour: int = 2,
    minute: int = 0,
    log_retention_days: int = 7,
) -> ScheduledCleanupService:
    """
    获取定时清理服务实例（单例）
    
    Args:
        hour: 每天执行清理的小时
        minute: 每天执行清理的分钟
        log_retention_days: 日志保留天数
    
    Returns:
        ScheduledCleanupService: 定时清理服务实例
    """
    global _scheduled_cleanup_service
    
    if _scheduled_cleanup_service is None:
        _scheduled_cleanup_service = ScheduledCleanupService(
            hour=hour,
            minute=minute,
            log_retention_days=log_retention_days,
        )
    
    return _scheduled_cleanup_service


async def start_scheduled_cleanup_service(
    hour: int = 2,
    minute: int = 0,
    log_retention_days: int = 7,
):
    """启动定时清理服务"""
    service = get_scheduled_cleanup_service(
        hour=hour,
        minute=minute,
        log_retention_days=log_retention_days,
    )
    await service.start()


async def stop_scheduled_cleanup_service():
    """停止定时清理服务"""
    if _scheduled_cleanup_service:
        await _scheduled_cleanup_service.stop()

