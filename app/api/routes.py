"""API route handlers"""
import logging
import asyncio
import uuid
from typing import Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import ValidationError

from app.models.schemas import (
    TaskResponse,
    TaskStatusResponse,
    TaskStatus,
    FrameLevel,
    VideoAnalysisRequest,
    BatchTaskStatusRequest,
    BatchTaskStatusResponse,
    ImageAnalysisRequest,
    SingleImageTaggingResult,
)
from app.services.ice_client import ice_service
from app.services.oss_client import oss_service
from app.services.doubao_client import doubao_service
from app.core.config import settings

logger = logging.getLogger(__name__)


# ===== 错误分类映射 =====

def classify_error(exception: Exception) -> tuple[str, str]:
    """
    分类异常，返回 (error_type, error_message)
    
    根据异常类型和消息内容，判断错误类型：
    - 临时性错误：可以重试的错误（网络、超时、服务不可用等）
    - 永久性错误：无法通过重试解决的错误（格式、内容、参数等）
    
    Returns:
        (error_type: str, error_message: str)
    """
    error_str = str(exception).lower()
    error_type_name = type(exception).__name__
    
    # AI服务相关错误
    if "timeout" in error_str or "timed out" in error_str:
        return ("ai_timeout", str(exception))
    
    if "rate limit" in error_str or "限流" in error_str or "429" in error_str:
        return ("rate_limit_exceeded", str(exception))
    
    if "service unavailable" in error_str or "503" in error_str or "502" in error_str:
        return ("ai_service_unavailable", str(exception))
    
    if "connection" in error_str or "网络" in error_str:
        return ("network_error", str(exception))
    
    # 内容相关错误
    if "sensitive" in error_str or "敏感" in error_str:
        return ("sensitive_content", str(exception))
    
    if "complex" in error_str or "复杂" in error_str:
        return ("content_too_complex", str(exception))
    
    # 视频相关错误
    if "format" in error_str and ("video" in error_str or "视频" in error_str):
        return ("video_format_unsupported", str(exception))
    
    if "corrupt" in error_str or "损坏" in error_str:
        if "video" in error_str or "视频" in error_str:
            return ("video_corrupted", str(exception))
        elif "image" in error_str or "图片" in error_str:
            return ("image_corrupted", str(exception))
    
    if "too short" in error_str or "过短" in error_str:
        return ("video_too_short", str(exception))
    
    if "too long" in error_str or "过长" in error_str:
        return ("video_too_long", str(exception))
    
    # 抽帧相关错误
    if "frame" in error_str and "extract" in error_str:
        if "timeout" in error_str:
            return ("frame_extraction_timeout", str(exception))
        return ("frame_extraction_failed", str(exception))
    
    if "未提取到任何帧" in error_str or "抽帧失败" in error_str:
        return ("frame_extraction_failed", str(exception))
    
    # 图片相关错误
    if "format" in error_str and ("image" in error_str or "图片" in error_str):
        return ("image_format_unsupported", str(exception))
    
    if "resolution" in error_str and "low" in error_str:
        return ("image_resolution_too_low", str(exception))
    
    if "thumbnail" in error_str or "缩略图" in error_str:
        return ("thumbnail_generation_failed", str(exception))
    
    # 媒资相关错误
    if "media" in error_str or "媒资" in error_str:
        if "not found" in error_str or "未找到" in error_str:
            return ("media_not_found", str(exception))
        return ("ice_media_not_ready", str(exception))
    
    # 参数相关错误
    if "parameter" in error_str or "参数" in error_str or isinstance(exception, (ValueError, ValidationError)):
        return ("invalid_parameters", str(exception))
    
    # 默认为AI服务错误（临时性，可重试）
    return ("ai_service_error", str(exception))


# Concurrency control manager
class ConcurrencyManager:
    """并发控制管理器 - 分别控制抽帧和分析的并发数"""
    
    def __init__(self):
        # 抽帧任务：最多5个并发（IO密集型）
        self.extraction_semaphore = asyncio.Semaphore(5)
        # AI分析任务：最多3个并发（计算/API密集型）
        self.analysis_semaphore = asyncio.Semaphore(3)
        
        # 统计信息
        self.extraction_active = 0
        self.analysis_active = 0
    
    async def acquire_extraction(self):
        """获取抽帧槽位"""
        await self.extraction_semaphore.acquire()
        self.extraction_active += 1
        logger.debug(f"Extraction acquired: {self.extraction_active}/5 active")
    
    def release_extraction(self):
        """释放抽帧槽位"""
        self.extraction_semaphore.release()
        self.extraction_active -= 1
        logger.debug(f"Extraction released: {self.extraction_active}/5 active")
    
    async def acquire_analysis(self):
        """获取分析槽位"""
        await self.analysis_semaphore.acquire()
        self.analysis_active += 1
        logger.debug(f"Analysis acquired: {self.analysis_active}/3 active")
    
    def release_analysis(self):
        """释放分析槽位"""
        self.analysis_semaphore.release()
        self.analysis_active -= 1
        logger.debug(f"Analysis released: {self.analysis_active}/3 active")
    
    def get_stats(self):
        """获取并发统计"""
        return {
            "extraction": {
                "active": self.extraction_active,
                "max": 5
            },
            "analysis": {
                "active": self.analysis_active,
                "max": 3
            }
        }


# Global concurrency manager instance
concurrency_manager = ConcurrencyManager()

# Create router
router = APIRouter()

# In-memory task storage (in production, use Redis or database)
tasks_storage: Dict[str, Dict] = {}


@router.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "MOSS-AI",
        "version": settings.app_version,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# TASK MANAGEMENT API
# ============================================================================

@router.get(
    "/api/task/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Task Management"]
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get task status by task_id
    
    - **task_id**: Task ID returned from submission
    """
    try:
        if task_id not in tasks_storage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )
        
        task_data = tasks_storage[task_id]
        
        return TaskStatusResponse(
            task_id=task_id,
            moss_id=task_data.get("moss_id", ""),
            brand_name=task_data.get("brand_name", ""),
            media_id=task_data.get("media_id", ""),
            frame_level=task_data.get("frame_level", ""),
            status=task_data["status"],
            message=task_data.get("message", ""),
            progress=task_data.get("progress"),
            result=task_data.get("result"),
            error_detail=task_data.get("error_detail"),
            created_at=task_data["created_at"],
            updated_at=task_data["updated_at"],
            completed_at=task_data.get("completed_at")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task status for {task_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}"
        )


@router.delete(
    "/api/task/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Task Management"]
)
async def delete_task(task_id: str):
    """
    Delete task from storage (MOSS should call this after getting results)
    
    - **task_id**: Task ID to delete
    """
    try:
        if task_id not in tasks_storage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )
        
        del tasks_storage[task_id]
        logger.info(f"Task {task_id} deleted by client")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete task: {str(e)}"
        )


# ============================================================================
# NEW UNIFIED VIDEO ANALYSIS API
# ============================================================================

@router.post(
    "/api/analyze-video",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Video Analysis"]
)
async def analyze_video(
    request: VideoAnalysisRequest,
    background_tasks: BackgroundTasks
) -> TaskResponse:
    """
    短视频素材打标接口 - 抽帧 + AI打标分析（立即返回task_id）
    
    必需参数：
    - **moss_id**: MOSS系统视频ID
    - **brand_name**: 品牌方名称
    - **media_id**: 阿里云ICE媒资ID
    - **frame_level**: 抽帧等级 (low/medium/high)
    
    工作流程：
    1. 立即返回 task_id
    2. 后台执行：获取媒资信息 → 抽帧 → 短视频素材打标分析
    3. MOSS 轮询查询状态：GET /api/task/{task_id}
    4. 完成后 MOSS 获取结果并调用 DELETE /api/task/{task_id}
    
    打标内容包括：
    - 核心主体、动作事件、场景设置
    - 视觉风格、色彩基调、主导情感
    - 氛围标签、网络热梗标签、关键词
    """
    try:
        # Generate unique task ID
        task_id = f"video_analysis_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
        
        # Store task info
        tasks_storage[task_id] = {
            "task_id": task_id,
            "type": "video_analysis",
            "moss_id": request.moss_id,
            "brand_name": request.brand_name,
            "media_id": request.media_id,
            "frame_level": request.frame_level.value,
            "status": TaskStatus.PENDING,
            "message": "任务已提交，等待处理",
            "progress": 0,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        
        # Submit background task
        background_tasks.add_task(
            process_video_analysis_task,
            task_id,
            request
        )
        
        logger.info(
            f"Video analysis task {task_id} submitted: "
            f"moss_id={request.moss_id}, media_id={request.media_id}, "
            f"frame_level={request.frame_level.value}"
        )
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="任务已提交，请使用 task_id 查询处理状态",
            created_at=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error submitting video analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交任务失败: {str(e)}"
        )


async def process_video_analysis_task(
    task_id: str,
    request: VideoAnalysisRequest
):
    """
    处理视频分析任务（带精细并发控制）
    完整流程：获取媒资信息 → 抽帧（并发控制） → AI分析（并发控制）
    """
    task_data = tasks_storage.get(task_id)
    if not task_data:
        logger.error(f"Task {task_id} not found in storage")
        return
    
    try:
        # ========== 阶段1: 抽帧（受抽帧并发限制） ==========
        await concurrency_manager.acquire_extraction()
        try:
            task_data["status"] = TaskStatus.PROCESSING
            task_data["message"] = "正在获取视频信息..."
            task_data["progress"] = 10
            task_data["updated_at"] = datetime.now()
            
            # 获取媒资信息
            logger.info(f"[{task_id}] Getting media info for {request.media_id}")
            media_info = ice_service.get_media_info(request.media_id)
            
            if not media_info:
                raise ValueError(f"无法获取媒资信息: {request.media_id}")
            
            # 解析视频OSS路径
            file_url = media_info.get("file_url")
            if not file_url:
                raise ValueError(f"媒资中未找到文件URL: {request.media_id}")
            
            # 解析OSS路径
            if file_url.startswith("oss://"):
                video_oss_path = file_url.split("/", 3)[3] if "/" in file_url else file_url
            elif "aliyuncs.com/" in file_url:
                path_with_params = file_url.split(".aliyuncs.com/", 1)[1]
                video_oss_path = path_with_params.split("?")[0]
            else:
                video_oss_path = file_url.split("?")[0]
            
            video_oss_path = unquote(video_oss_path)
            
            task_data["message"] = f"正在抽帧（等级：{request.frame_level.value}）..."
            task_data["progress"] = 30
            task_data["updated_at"] = datetime.now()
            
            # 抽帧
            logger.info(
                f"[{task_id}] Extracting frames: "
                f"duration={media_info['duration']}s, level={request.frame_level.value}"
            )
            frames = oss_service.extract_frames_by_oss(
                video_oss_path=video_oss_path,
                video_duration=media_info["duration"],
                frame_level=request.frame_level
            )
            
            if not frames or len(frames) == 0:
                raise ValueError("抽帧失败：未提取到任何帧")
            
            task_data["frames"] = [f.url for f in frames]
            task_data["media_info"] = media_info
            task_data["progress"] = 50
            task_data["updated_at"] = datetime.now()
            
        finally:
            concurrency_manager.release_extraction()
        
        # ========== 阶段2: AI分析（受分析并发限制） ==========
        await concurrency_manager.acquire_analysis()
        try:
            task_data["message"] = f"抽帧完成（{len(frames)}帧），开始AI分析..."
            task_data["progress"] = 60
            task_data["updated_at"] = datetime.now()
            
            # 短视频素材打标分析
            logger.info(f"[{task_id}] Analyzing {len(frames)} frames for short video tagging")
            context = {
                "duration": media_info.get("duration", 0),
                "resolution": media_info.get("resolution"),
                "frame_count": len(frames),
            }
            
            # 使用新的短视频打标分析功能
            tagging_result = await doubao_service.analyze_short_video_frames(
                frame_urls=task_data["frames"],
                context=context
            )
            
            # 构建完整结果
            task_data["status"] = TaskStatus.COMPLETED
            task_data["message"] = "短视频素材打标完成"
            task_data["progress"] = 100
            
            # 确保所有列表字段都不为None，始终返回空列表而不是null
            def ensure_list(value):
                """确保值是列表，如果是None则返回空列表"""
                if value is None:
                    return []
                if isinstance(value, list):
                    return value
                return []
            
            # 构建安全的tagging数据，确保所有列表字段都不为None
            safe_atmosphere_tags = ensure_list(tagging_result.atmosphere_tags)
            safe_viral_meme_tags = ensure_list(tagging_result.viral_meme_tags)
            safe_keywords = ensure_list(tagging_result.keywords)
            
            task_data["result"] = {
                "moss_id": request.moss_id,
                "brand_name": request.brand_name,
                "media_id": request.media_id,
                "frame_level": request.frame_level.value,
                "tagging": {
                    "main_subject": tagging_result.main_subject or "",
                    "action_or_event": tagging_result.action_or_event or "",
                    "scene_setting": tagging_result.scene_setting or "",
                    "visual_style": tagging_result.visual_style or "",
                    "color_palette": tagging_result.color_palette or "",
                    "emotion_dominant": tagging_result.emotion_dominant or "",
                    "atmosphere_tags": safe_atmosphere_tags,
                    "viral_meme_tags": safe_viral_meme_tags,
                    "keywords": safe_keywords
                },
                "metadata": {
                    "frame_count": len(frames),
                    "video_duration": media_info.get("duration"),
                    "video_resolution": media_info.get("resolution"),
                    "model_used": settings.doubao_model,
                    "analysis_type": "short_video_tagging"
                }
            }
            task_data["completed_at"] = datetime.now()
            task_data["updated_at"] = datetime.now()
            
            logger.info(f"[{task_id}] Video analysis completed successfully")
            
        finally:
            concurrency_manager.release_analysis()
            
    except Exception as e:
        logger.error(f"[{task_id}] Error in video analysis: {str(e)}", exc_info=True)
        
        # 分类错误
        error_type, error_message = classify_error(e)
        
        # 记录失败信息
        task_data = tasks_storage.get(task_id, {})
        task_data["status"] = TaskStatus.FAILED
        task_data["message"] = f"任务失败: {error_message}"
        task_data["error_detail"] = {
            "error_type": error_type,
            "error_message": error_message,
        }
        task_data["updated_at"] = datetime.now()
        task_data["failed_at"] = datetime.now()
        
        logger.info(f"[{task_id}] Classified error - type: {error_type}, message: {error_message}")
        
        # 确保释放所有资源
        try:
            concurrency_manager.release_extraction()
        except:
            pass
        try:
            concurrency_manager.release_analysis()
        except:
            pass


@router.post(
    "/api/tasks/batch-status",
    response_model=BatchTaskStatusResponse,
    tags=["Task Management"]
)
async def get_batch_task_status(
    request: BatchTaskStatusRequest
) -> BatchTaskStatusResponse:
    """
    批量查询任务状态
    
    - **task_ids**: 任务ID列表（最多50个）
    
    返回所有任务的状态，未找到的任务返回 null
    """
    results = {}
    not_found = []
    found_count = 0
    
    for task_id in request.task_ids:
        if task_id in tasks_storage:
            task_data = tasks_storage[task_id]
            results[task_id] = TaskStatusResponse(
                task_id=task_id,
                moss_id=task_data.get("moss_id", ""),
                brand_name=task_data.get("brand_name", ""),
                media_id=task_data.get("media_id", ""),
                frame_level=task_data.get("frame_level", ""),
                status=task_data["status"],
                message=task_data.get("message", ""),
                progress=task_data.get("progress"),
                result=task_data.get("result"),
                error_detail=task_data.get("error_detail"),
                created_at=task_data["created_at"],
                updated_at=task_data["updated_at"],
                completed_at=task_data.get("completed_at")
            )
            found_count += 1
        else:
            results[task_id] = None
            not_found.append(task_id)
    
    return BatchTaskStatusResponse(
        results=results,
        total=len(request.task_ids),
        found=found_count,
        not_found=not_found
    )


@router.get(
    "/api/system/concurrency",
    tags=["System"]
)
async def get_concurrency_stats():
    """
    获取当前并发情况统计
    
    返回抽帧和分析任务的并发使用情况
    """
    # 获取任务统计
    task_stats = {
        "pending": sum(1 for t in tasks_storage.values() if t["status"] == TaskStatus.PENDING),
        "processing": sum(1 for t in tasks_storage.values() if t["status"] == TaskStatus.PROCESSING),
        "completed": sum(1 for t in tasks_storage.values() if t["status"] == TaskStatus.COMPLETED),
        "failed": sum(1 for t in tasks_storage.values() if t["status"] == TaskStatus.FAILED),
        "retry": sum(1 for t in tasks_storage.values() if t["status"] == TaskStatus.RETRY),
    }
    
    return {
        "concurrency": concurrency_manager.get_stats(),
        "tasks": {
            "total": len(tasks_storage),
            "by_status": task_stats
        },
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# MEMORY CLEANUP MECHANISM
# ============================================================================

async def cleanup_old_tasks():
    """
    智能内存清理机制（混合策略）
    
    清理规则：
    - COMPLETED/FAILED: 创建后48小时清理（给MOSS充足时间获取结果）
    - PENDING: 超过1小时标记为失败
    - PROCESSING: 超过2小时无更新标记为失败
    """
    while True:
        try:
            await asyncio.sleep(1800)  # 每30分钟执行一次
            
            now = datetime.now()
            to_delete = []
            
            for task_id, task in list(tasks_storage.items()):
                try:
                    status = task.get("status")
                    created_at = task.get("created_at")
                    updated_at = task.get("updated_at")
                    
                    if not created_at or not updated_at:
                        continue
                    
                    age = now - created_at
                    idle_time = now - updated_at
                    
                    # 终态任务：创建后48小时清理
                    if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        if age > timedelta(hours=48):
                            to_delete.append(task_id)
                            logger.warning(
                                f"Cleanup: {status} task {task_id} after 48h "
                                f"(MOSS should have deleted it)"
                            )
                    
                    # 待处理任务：超过1小时标记失败
                    elif status == TaskStatus.PENDING:
                        if age > timedelta(hours=1):
                            task["status"] = TaskStatus.FAILED
                            task["message"] = "任务超时：等待处理超过1小时"
                            task["error_detail"] = {
                                "error_type": "TimeoutError",
                                "error_message": "Task stuck in PENDING state"
                            }
                            task["updated_at"] = now
                            logger.warning(f"Task {task_id} timeout: PENDING > 1h")
                    
                    # 处理中任务：超过2小时无更新标记失败
                    elif status == TaskStatus.PROCESSING:
                        if idle_time > timedelta(hours=2):
                            task["status"] = TaskStatus.FAILED
                            task["message"] = "任务超时：处理超过2小时无响应"
                            task["error_detail"] = {
                                "error_type": "TimeoutError",
                                "error_message": "Task processing timeout"
                            }
                            task["updated_at"] = now
                            logger.warning(f"Task {task_id} timeout: PROCESSING > 2h")
                
                except Exception as e:
                    logger.error(f"Error checking task {task_id} for cleanup: {e}")
            
            # 执行删除
            for task_id in to_delete:
                try:
                    del tasks_storage[task_id]
                except:
                    pass
            
            if to_delete:
                logger.info(f"Cleaned up {len(to_delete)} expired tasks")
            
            # 内存使用监控
            task_count = len(tasks_storage)
            if task_count > 500:
                logger.warning(f"High memory usage: {task_count} tasks in storage")
        
        except Exception as e:
            logger.error(f"Error in cleanup task: {e}")


# ============================================================================
# IMAGE ANALYSIS API
# ============================================================================

@router.post(
    "/api/analyze-image",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Image Analysis"]
)
async def analyze_image(
    request: ImageAnalysisRequest,
    background_tasks: BackgroundTasks
) -> TaskResponse:
    """
    单张图片打标接口 - 生成缩略图 + AI打标分析（立即返回task_id）
    
    必需参数：
    - **moss_id**: MOSS系统图片ID
    - **brand_name**: 品牌方名称
    - **media_id**: 阿里云ICE媒资ID
    
    工作流程：
    1. 立即返回 task_id
    2. 后台执行：获取媒资信息 → 生成缩略图 → 图片打标分析
    3. MOSS 轮询查询状态：GET /api/task/{task_id}
    """
    try:
        # 生成唯一任务ID
        import secrets
        task_id = f"image_analysis_{int(datetime.now().timestamp())}_{secrets.token_hex(4)}"
        
        # 初始化任务数据
        task_data = {
            "task_id": task_id,
            "moss_id": request.moss_id,
            "brand_name": request.brand_name,
            "media_id": request.media_id,
            "status": TaskStatus.PENDING,
            "message": "任务已提交，等待处理",
            "progress": 0,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "result": None,
            "error_detail": None
        }
        
        # 存储任务
        tasks_storage[task_id] = task_data
        
        # 提交后台任务
        background_tasks.add_task(
            process_image_analysis_task,
            task_id,
            request
        )
        
        logger.info(
            f"Image analysis task {task_id} submitted: "
            f"moss_id={request.moss_id}, media_id={request.media_id}"
        )
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="任务已提交，请使用 task_id 查询处理状态",
            created_at=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error submitting image analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提交图片分析任务失败: {str(e)}"
        )


async def process_image_analysis_task(
    task_id: str,
    request: ImageAnalysisRequest
):
    """
    处理图片分析任务
    完整流程：获取媒资信息 → 生成缩略图 → AI分析
    """
    task_data = tasks_storage.get(task_id)
    if not task_data:
        logger.error(f"Task {task_id} not found in storage")
        return
    
    try:
        # ========== 阶段1: 获取媒资信息 ==========
        task_data["status"] = TaskStatus.PROCESSING
        task_data["message"] = "正在获取图片信息..."
        task_data["progress"] = 10
        task_data["updated_at"] = datetime.now()
        
        logger.info(f"[{task_id}] Getting media info for: {request.media_id}")
        media_info = ice_service.get_media_info(request.media_id)
        
        if not media_info:
            raise ValueError("无法获取媒资信息")
        
        image_oss_path = media_info.get("file_url")
        if not image_oss_path:
            raise ValueError("媒资文件URL为空")
        
        # 直接使用原图的签名URL（不要解码，否则会破坏签名导致403）
        image_url = image_oss_path
        
        # ========== 阶段2: 准备图片URL ==========
        task_data["message"] = "正在准备图片URL..."
        task_data["progress"] = 30
        task_data["updated_at"] = datetime.now()
        logger.info(f"[{task_id}] Using original image url for analysis")
        
        # ========== 阶段3: AI图片打标分析 ==========  
        task_data["message"] = "正在进行AI图片打标分析..."
        task_data["progress"] = 60
        task_data["updated_at"] = datetime.now()
        
        logger.info(f"[{task_id}] Analyzing image for tagging")
        
        # 使用原图URL进行图片打标分析（不再生成缩略图）
        tagging_result = await doubao_service.analyze_single_image_tagging(image_url=image_url)
        
        # 确保所有列表字段都不为None，始终返回空列表而不是null
        def ensure_list(value):
            """确保值是列表，如果是None则返回空列表"""
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return []
        
        # 构建安全的tagging数据
        safe_atmosphere_tags = ensure_list(tagging_result.atmosphere_tags)
        safe_viral_meme_tags = ensure_list(tagging_result.viral_meme_tags)
        safe_keywords = ensure_list(tagging_result.keywords)
        
        # 构建完整结果（已确保所有字段非 None，列表为 []）
        task_data["status"] = TaskStatus.COMPLETED
        task_data["message"] = "图片打标分析完成"
        task_data["progress"] = 100
        task_data["result"] = {
            "moss_id": request.moss_id,
            "brand_name": request.brand_name,
            "media_id": request.media_id,
            "tagging": {
                "main_subject": tagging_result.main_subject or "",
                "subject_state": tagging_result.subject_state or "",
                "scene_setting": tagging_result.scene_setting or "",
                "composition_style": tagging_result.composition_style or "",
                "color_lighting": tagging_result.color_lighting or "",
                "emotion_dominant": tagging_result.emotion_dominant or "",
                "atmosphere_tags": safe_atmosphere_tags,
                "viral_meme_tags": safe_viral_meme_tags,
                "keywords": safe_keywords
            },
            "metadata": {
                "image_resolution": media_info.get("resolution"),
                "model_used": settings.doubao_model,
                "analysis_type": "single_image_tagging",
                "thumbnail_url": image_url
            }
        }
        task_data["completed_at"] = datetime.now()
        task_data["updated_at"] = datetime.now()
        
        logger.info(f"[{task_id}] Image analysis completed successfully")
        
    except Exception as e:
        logger.error(f"[{task_id}] Error in image analysis: {str(e)}", exc_info=True)
        
        # 分类错误
        error_type, error_message = classify_error(e)
        
        task_data["status"] = TaskStatus.FAILED
        task_data["message"] = f"图片分析失败: {error_message}"
        task_data["progress"] = 0
        task_data["error_detail"] = {
            "error_type": error_type,
            "error_message": error_message
        }
        task_data["updated_at"] = datetime.now()
        task_data["failed_at"] = datetime.now()
        
        logger.info(f"[{task_id}] Classified error - type: {error_type}, message: {error_message}")


# Export cleanup function for use in main.py
__all__ = ['router', 'cleanup_old_tasks']

