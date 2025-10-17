"""API route handlers"""
import logging
import asyncio
from typing import Dict, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, status
from pydantic import ValidationError

from app.models.schemas import (
    ExtractFramesRequest,
    ExtractFramesResponse,
    AnalyzeFramesRequest,
    AnalyzeMediaRequest,
    AnalyzeResponse,
    TaskResponse,
    TaskStatusResponse,
    TaskStatus,
    MediaType,
    FrameLevel,
    FrameIndexData,
    FrameInfo,
    ErrorResponse
)
from app.services.ice_client import ice_service
from app.services.oss_client import oss_service
from app.services.doubao_client import doubao_service
from app.utils.media_converter import media_converter
from app.core.config import settings

logger = logging.getLogger(__name__)

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


@router.post(
    "/api/extract-frames",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Frame Extraction"]
)
async def extract_frames(
    request: ExtractFramesRequest,
    background_tasks: BackgroundTasks
) -> TaskResponse:
    """
    使用OSS实时处理抽帧（立即返回）
    
    - **media_id**: 阿里云ICE媒资ID
    - **moss_id**: MOSS系统视频ID
    - **brand_name**: 品牌方名称
    - **frame_level**: 抽帧等级 (low/medium/high)
    """
    try:
        # Generate task ID
        task_id = f"extract_{datetime.now().timestamp()}"
        
        # Store task info
        tasks_storage[task_id] = {
            "task_id": task_id,
            "type": "extract_frames",
            "status": TaskStatus.PENDING,
            "request": request.model_dump(),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        
        # Schedule background extraction (using OSS)
        background_tasks.add_task(perform_oss_extraction, task_id, request)
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="Frame extraction task submitted (using OSS real-time processing)",
            created_at=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error submitting frame extraction: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit frame extraction task: {str(e)}"
        )


async def perform_oss_extraction(task_id: str, request: ExtractFramesRequest):
    """Background task to perform OSS-based frame extraction"""
    try:
        task_data = tasks_storage[task_id]
        task_data["status"] = TaskStatus.PROCESSING
        task_data["message"] = "Fetching media info..."
        task_data["updated_at"] = datetime.now()
        
        # 1. Get media info from ICE (for video duration and OSS path)
        logger.info(f"Getting media info for {request.media_id}")
        media_info = ice_service.get_media_info(request.media_id)
        
        # Extract video OSS path from media info
        file_url = media_info.get("file_url")
        if not file_url:
            raise ValueError(f"No file URL found in media info for {request.media_id}")
        
        # Parse OSS path from URL (format: oss://bucket/path or http://bucket.oss.../path)
        if file_url.startswith("oss://"):
            # Format: oss://bucket/path -> extract path
            video_oss_path = file_url.split("/", 3)[3] if "/" in file_url else file_url
        elif "aliyuncs.com/" in file_url:
            # Format: http://bucket.oss-region.aliyuncs.com/path?params -> extract path without params
            path_with_params = file_url.split(".aliyuncs.com/", 1)[1] if ".aliyuncs.com/" in file_url else file_url
            # Remove URL parameters (everything after ?)
            video_oss_path = path_with_params.split("?")[0] if "?" in path_with_params else path_with_params
        else:
            # Fallback: use as is
            video_oss_path = file_url.split("?")[0] if "?" in file_url else file_url
        
        # URL decode the path
        from urllib.parse import unquote
        video_oss_path = unquote(video_oss_path)
        
        logger.info(f"Using video OSS path: {video_oss_path}")
        
        task_data["message"] = "Extracting frames using OSS..."
        task_data["progress"] = 30
        task_data["updated_at"] = datetime.now()
        
        # 2. Use OSS video/snapshot to extract frames
        logger.info(f"Extracting frames: duration={media_info['duration']}s, level={request.frame_level}")
        frames = oss_service.extract_frames_by_oss(
            video_oss_path=video_oss_path,
            video_duration=media_info["duration"],
            frame_level=request.frame_level
        )
        
        task_data["message"] = "Generating index..."
        task_data["progress"] = 80
        task_data["updated_at"] = datetime.now()
        
        # 3. Create index data
        oss_directory = oss_service.generate_oss_path(request.brand_name, request.moss_id)
        
        index_data = FrameIndexData(
            media_id=request.media_id,
            moss_id=request.moss_id,
            brand_name=request.brand_name,
            frame_level=request.frame_level,
            total_frames=len(frames),
            video_duration=media_info["duration"],
            video_resolution=media_info.get("resolution"),
            extraction_time=datetime.now(),
            frames=frames
        )
        
        # 4. Upload index file to OSS
        index_path = oss_service.create_frame_index(index_data, oss_directory)
        index_url = oss_service.generate_signed_url(index_path)
        
        # 5. Update task with results
        task_data["status"] = TaskStatus.COMPLETED
        task_data["message"] = "Frame extraction completed using OSS real-time processing"
        task_data["progress"] = 100
        task_data["result"] = {
            "frame_count": len(frames),
            "index_file_url": index_url,
            "frame_urls": [f.url for f in frames],
            "oss_directory": oss_directory,
            "extraction_method": "oss_realtime"
        }
        task_data["completed_at"] = datetime.now()
        
        logger.info(f"OSS extraction task {task_id} completed with {len(frames)} frames")
        
    except Exception as e:
        logger.error(f"Error in OSS extraction {task_id}: {str(e)}")
        tasks_storage[task_id]["status"] = TaskStatus.FAILED
        tasks_storage[task_id]["message"] = f"OSS extraction error: {str(e)}"
        tasks_storage[task_id]["updated_at"] = datetime.now()


@router.post(
    "/api/analyze-frames",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["AI Analysis"]
)
async def analyze_frames(
    request: AnalyzeFramesRequest,
    background_tasks: BackgroundTasks
) -> TaskResponse:
    """
    Analyze video frames with Doubao AI
    
    - **frame_urls**: 帧图片URL列表（按时间顺序）
    - **video_duration**: 视频时长（秒）
    - **video_resolution**: 视频分辨率
    - **custom_prompt**: 自定义分析提示词
    """
    try:
        # Generate task ID
        task_id = f"analyze_{datetime.now().timestamp()}"
        
        # Store task info
        tasks_storage[task_id] = {
            "task_id": task_id,
            "type": "analyze_frames",
            "status": TaskStatus.PENDING,
            "request": request.model_dump(mode='json'),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        
        # Schedule background analysis
        background_tasks.add_task(perform_frame_analysis, task_id, request)
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message="Frame analysis task submitted successfully",
            created_at=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error submitting frame analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit analysis task: {str(e)}"
        )


async def perform_frame_analysis(task_id: str, request: AnalyzeFramesRequest):
    """Background task to perform frame analysis"""
    try:
        task_data = tasks_storage[task_id]
        task_data["status"] = TaskStatus.PROCESSING
        task_data["updated_at"] = datetime.now()
        
        # Prepare context
        context = {}
        if request.video_duration:
            context["duration"] = request.video_duration
        if request.video_resolution:
            context["resolution"] = request.video_resolution
        context["frame_count"] = len(request.frame_urls)
        
        # Analyze frames
        result = await doubao_service.analyze_frames(
            frame_urls=[str(url) for url in request.frame_urls],
            context=context,
            custom_prompt=request.custom_prompt
        )
        
        # Update task with results
        task_data["status"] = TaskStatus.COMPLETED
        task_data["message"] = "Analysis completed successfully"
        task_data["result"] = {
            "analysis_result": result.model_dump(),
            "frame_count": len(request.frame_urls),
            "model_used": settings.doubao_model,
        }
        task_data["completed_at"] = datetime.now()
        
        logger.info(f"Analysis task {task_id} completed")
        
    except Exception as e:
        logger.error(f"Error performing frame analysis {task_id}: {str(e)}")
        tasks_storage[task_id]["status"] = TaskStatus.FAILED
        tasks_storage[task_id]["message"] = f"Analysis error: {str(e)}"
        tasks_storage[task_id]["updated_at"] = datetime.now()


@router.post(
    "/api/analyze-media",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["AI Analysis"]
)
async def analyze_media(
    request: AnalyzeMediaRequest,
    background_tasks: BackgroundTasks
) -> TaskResponse:
    """
    Analyze media (image/video/gif) by media_id or URL
    
    - **media_id**: 媒资ID（可选，与media_url二选一）
    - **media_url**: 媒体URL（可选，与media_id二选一）
    - **media_type**: 媒体类型 (image/video/gif)
    - **moss_id**: MOSS ID（视频/GIF需要）
    - **brand_name**: 品牌方名称（视频/GIF需要）
    - **frame_level**: 抽帧等级（仅视频/GIF）
    - **custom_prompt**: 自定义分析提示词
    """
    try:
        # Validate input
        if not request.media_id and not request.media_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either media_id or media_url must be provided"
            )
        
        if request.media_type in [MediaType.VIDEO, MediaType.GIF]:
            if not request.moss_id or not request.brand_name:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="moss_id and brand_name are required for video/gif"
                )
        
        # Generate task ID
        task_id = f"analyze_media_{datetime.now().timestamp()}"
        
        # Store task info
        tasks_storage[task_id] = {
            "task_id": task_id,
            "type": "analyze_media",
            "status": TaskStatus.PENDING,
            "request": request.model_dump(mode='json'),
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
        }
        
        # Schedule background processing
        background_tasks.add_task(process_media_analysis, task_id, request)
        
        return TaskResponse(
            task_id=task_id,
            status=TaskStatus.PENDING,
            message=f"{request.media_type.value} analysis task submitted successfully",
            created_at=datetime.now()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting media analysis: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit analysis task: {str(e)}"
        )


async def process_media_analysis(task_id: str, request: AnalyzeMediaRequest):
    """Background task to process media analysis"""
    try:
        task_data = tasks_storage[task_id]
        task_data["status"] = TaskStatus.PROCESSING
        task_data["updated_at"] = datetime.now()
        
        if request.media_type == MediaType.IMAGE:
            # Analyze single image
            await process_image_analysis(task_id, request)
        elif request.media_type == MediaType.GIF:
            # Convert GIF to video and analyze
            await process_gif_analysis(task_id, request)
        elif request.media_type == MediaType.VIDEO:
            # Extract frames and analyze
            await process_video_analysis(task_id, request)
        
    except Exception as e:
        logger.error(f"Error processing media analysis {task_id}: {str(e)}")
        tasks_storage[task_id]["status"] = TaskStatus.FAILED
        tasks_storage[task_id]["message"] = f"Processing error: {str(e)}"
        tasks_storage[task_id]["updated_at"] = datetime.now()


async def process_image_analysis(task_id: str, request: AnalyzeMediaRequest):
    """Process single image analysis"""
    try:
        task_data = tasks_storage[task_id]
        task_data["message"] = "Getting image URL..."
        task_data["updated_at"] = datetime.now()
        
        # Get image URL
        if request.media_id:
            # Get image URL from ICE media
            logger.info(f"Getting image info from ICE: {request.media_id}")
            media_info = ice_service.get_media_info(request.media_id)
            
            # Extract file URL (same logic as video)
            file_url = media_info.get("file_url")
            if not file_url:
                raise ValueError(f"No file URL found in media info for {request.media_id}")
            
            # Parse and clean URL
            from urllib.parse import unquote
            if file_url.startswith("http"):
                # If it's already a full URL, use it directly
                # Remove query parameters to get clean URL
                image_url = file_url.split("?")[0] if "?" in file_url else file_url
            else:
                # If it's an OSS path, use it as is
                image_url = file_url
                
            logger.info(f"Using image URL from ICE: {image_url[:100]}...")
            
        elif request.media_url:
            image_url = str(request.media_url)
            logger.info(f"Using provided image URL: {image_url[:100]}...")
        else:
            raise ValueError("Either media_id or media_url must be provided")
        
        task_data["message"] = "Analyzing image with AI..."
        task_data["progress"] = 50
        task_data["updated_at"] = datetime.now()
        
        # Analyze image
        result = await doubao_service.analyze_single_image(
            image_url=image_url,
            custom_prompt=request.custom_prompt
        )
        
        # Update task with results
        task_data["status"] = TaskStatus.COMPLETED
        task_data["message"] = "Image analysis completed successfully"
        task_data["progress"] = 100
        task_data["result"] = {
            "analysis_result": result.model_dump(),
            "media_type": "image",
            "image_url": image_url,
            "model_used": settings.doubao_model,
        }
        task_data["completed_at"] = datetime.now()
        task_data["updated_at"] = datetime.now()
        
        logger.info(f"Image analysis task {task_id} completed")
        
    except Exception as e:
        logger.error(f"Error in image analysis {task_id}: {str(e)}")
        tasks_storage[task_id]["status"] = TaskStatus.FAILED
        tasks_storage[task_id]["message"] = f"Image analysis error: {str(e)}"
        tasks_storage[task_id]["updated_at"] = datetime.now()


async def process_gif_analysis(task_id: str, request: AnalyzeMediaRequest):
    """Process GIF analysis (convert to MP4 first)"""
    try:
        # TODO: Convert GIF to MP4 and register as media in ICE
        # For now, raise not implemented
        raise NotImplementedError("GIF analysis not fully implemented yet")
        
    except Exception as e:
        logger.error(f"Error in GIF analysis {task_id}: {str(e)}")
        raise


async def process_video_analysis(task_id: str, request: AnalyzeMediaRequest):
    """Process video analysis (extract frames first)"""
    try:
        if not request.media_id:
            raise ValueError("media_id is required for video analysis")
        
        # Submit frame extraction
        extract_request = ExtractFramesRequest(
            media_id=request.media_id,
            moss_id=request.moss_id,
            brand_name=request.brand_name,
            frame_level=request.frame_level,
            smart_frame_count=request.smart_frame_count
        )
        
        # Generate OSS path
        oss_directory = oss_service.generate_oss_path(
            request.brand_name,
            request.moss_id
        )
        
        # Submit extraction
        extraction_task_id, task_info = ice_service.submit_frame_extraction(
            media_id=request.media_id,
            output_path=oss_directory,
            frame_level=request.frame_level,
            smart_frame_count=request.smart_frame_count
        )
        
        # Poll extraction completion
        max_attempts = settings.poll_max_attempts
        poll_interval = settings.poll_interval
        
        for attempt in range(max_attempts):
            ice_status = ice_service.get_task_status(extraction_task_id)
            
            if ice_status["status"] == "completed":
                break
            elif ice_status["status"] == "failed":
                raise ValueError(f"Frame extraction failed: {ice_status.get('message')}")
            
            await asyncio.sleep(poll_interval)
        
        # Process extracted frames
        await process_completed_extraction(extraction_task_id)
        
        # Get frame URLs
        frame_paths = oss_service.list_frames(oss_directory)
        frame_urls = oss_service.generate_frame_urls(frame_paths)
        
        # Get media info
        media_info = ice_service.get_media_info(request.media_id)
        
        # Analyze frames
        context = {
            "duration": media_info.get("duration", 0),
            "resolution": media_info.get("resolution"),
            "frame_count": len(frame_urls),
        }
        
        result = await doubao_service.analyze_frames(
            frame_urls=frame_urls,
            context=context,
            custom_prompt=request.custom_prompt
        )
        
        # Update task with results
        task_data = tasks_storage[task_id]
        task_data["status"] = TaskStatus.COMPLETED
        task_data["message"] = "Video analysis completed successfully"
        task_data["result"] = {
            "analysis_result": result.model_dump(),
            "frame_count": len(frame_urls),
            "oss_directory": oss_directory,
            "model_used": settings.doubao_model,
        }
        task_data["completed_at"] = datetime.now()
        
        logger.info(f"Video analysis task {task_id} completed")
        
    except Exception as e:
        logger.error(f"Error in video analysis {task_id}: {str(e)}")
        raise


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
            status=task_data["status"],
            message=task_data.get("message", ""),
            progress=task_data.get("progress"),
            result=task_data.get("result"),
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
    Delete task from storage
    
    - **task_id**: Task ID to delete
    """
    try:
        if task_id not in tasks_storage:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )
        
        del tasks_storage[task_id]
        logger.info(f"Deleted task {task_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete task: {str(e)}"
        )

