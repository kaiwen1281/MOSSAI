"""Pydantic schemas for API requests and responses"""
from pydantic import BaseModel, Field, HttpUrl
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum


class FrameLevel(str, Enum):
    """Frame extraction level enum"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SMART = "smart"


class TaskStatus(str, Enum):
    """Task status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRY = "retry"
    CANCELLED = "cancelled"


class MediaType(str, Enum):
    """Media type enum"""
    VIDEO = "video"
    IMAGE = "image"
    GIF = "gif"


# Request Models
class ExtractFramesRequest(BaseModel):
    """Request to extract frames from video"""
    media_id: str = Field(..., description="阿里云ICE媒资ID")
    moss_id: str = Field(..., description="MOSS系统中的视频ID")
    brand_name: str = Field(..., description="品牌方名称")
    frame_level: FrameLevel = Field(default=FrameLevel.MEDIUM, description="抽帧等级")
    smart_frame_count: Optional[int] = Field(default=50, description="智能抽帧时的目标帧数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "media_id": "abc123def456",
                "moss_id": "video_001",
                "brand_name": "example_brand",
                "frame_level": "medium",
                "smart_frame_count": 100
            }
        }


class AnalyzeFramesRequest(BaseModel):
    """Request to analyze frames with Doubao AI"""
    frame_urls: List[HttpUrl] = Field(..., description="帧图片URL列表（按时间顺序）")
    video_duration: Optional[float] = Field(None, description="视频时长（秒）")
    video_resolution: Optional[str] = Field(None, description="视频分辨率，如1920x1080")
    custom_prompt: Optional[str] = Field(None, description="自定义提示词")
    
    class Config:
        json_schema_extra = {
            "example": {
                "frame_urls": [
                    "https://example.oss.com/frames/frame_0001.jpg",
                    "https://example.oss.com/frames/frame_0002.jpg"
                ],
                "video_duration": 135.5,
                "video_resolution": "1920x1080"
            }
        }


class AnalyzeMediaRequest(BaseModel):
    """Request to analyze media (image/video/gif) by media_id or url"""
    media_id: Optional[str] = Field(None, description="媒资ID（图片或视频）")
    media_url: Optional[HttpUrl] = Field(None, description="媒体URL（二选一）")
    media_type: MediaType = Field(..., description="媒体类型")
    moss_id: Optional[str] = Field(None, description="MOSS ID（视频/GIF需要）")
    brand_name: Optional[str] = Field(None, description="品牌方名称（视频/GIF需要）")
    frame_level: FrameLevel = Field(default=FrameLevel.MEDIUM, description="抽帧等级（仅视频/GIF）")
    smart_frame_count: Optional[int] = Field(default=50, description="智能抽帧目标帧数")
    custom_prompt: Optional[str] = Field(None, description="自定义分析提示词")
    
    class Config:
        json_schema_extra = {
            "example": {
                "media_id": "img123abc",
                "media_type": "image",
                "custom_prompt": "请分析这张图片的内容"
            }
        }


class VideoAnalysisRequest(BaseModel):
    """Video analysis request - unified interface (4 required parameters)"""
    moss_id: str = Field(..., description="MOSS系统视频ID")
    brand_name: str = Field(..., description="品牌方名称")
    media_id: str = Field(..., description="阿里云ICE媒资ID")
    frame_level: FrameLevel = Field(..., description="抽帧等级: low/medium/high")
    
    class Config:
        json_schema_extra = {
            "example": {
                "moss_id": "video_20231017_001",
                "brand_name": "nike",
                "media_id": "****0343c45e0ce64664a",
                "frame_level": "medium"
            }
        }


class ConvertGifRequest(BaseModel):
    """Request to convert GIF to MP4"""
    gif_url: HttpUrl = Field(..., description="GIF文件URL")
    moss_id: str = Field(..., description="MOSS系统ID")
    brand_name: str = Field(..., description="品牌方名称")


# Response Models
class FrameInfo(BaseModel):
    """Single frame information"""
    frame_number: int = Field(..., description="帧序号")
    timestamp: float = Field(..., description="视频时间戳（秒）")
    url: str = Field(..., description="帧图片URL")
    oss_path: str = Field(..., description="OSS存储路径")


class FrameIndexData(BaseModel):
    """Frame index metadata"""
    media_id: str
    moss_id: str
    brand_name: str
    frame_level: FrameLevel
    total_frames: int
    video_duration: Optional[float] = None
    video_resolution: Optional[str] = None
    extraction_time: datetime
    frames: List[FrameInfo]


class TaskResponse(BaseModel):
    """Task submission response"""
    task_id: str = Field(..., description="任务ID")
    status: TaskStatus = Field(..., description="任务状态")
    message: str = Field(..., description="状态消息")
    created_at: datetime = Field(default_factory=datetime.now)


class TaskStatusResponse(BaseModel):
    """Task status query response"""
    task_id: str
    moss_id: str = Field(..., description="MOSS视频ID")
    brand_name: str = Field(..., description="品牌方名称")
    media_id: str = Field(..., description="媒资ID")
    frame_level: str = Field(..., description="抽帧等级")
    status: TaskStatus
    message: str
    progress: Optional[int] = Field(None, description="进度百分比（0-100）")
    result: Optional[dict] = Field(None, description="任务结果数据")
    error_detail: Optional[dict] = Field(None, description="错误详情")
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class AnalysisResult(BaseModel):
    """AI analysis result"""
    summary: str = Field(..., description="视频摘要")
    detailed_content: str = Field(..., description="详细内容描述")
    tags: List[str] = Field(default_factory=list, description="标签/关键词")
    segments: Optional[List[dict]] = Field(None, description="分段分析结果")
    raw_response: Optional[dict] = Field(None, description="原始AI响应")


class ExtractFramesResponse(BaseModel):
    """Frame extraction completion response"""
    task_id: str
    media_id: str
    moss_id: str
    status: TaskStatus
    frame_count: int = Field(..., description="抽取的帧数量")
    index_file_url: str = Field(..., description="索引文件URL")
    frame_urls: List[str] = Field(..., description="所有帧的URL列表")
    oss_directory: str = Field(..., description="OSS存储目录")


class AnalyzeResponse(BaseModel):
    """Analysis completion response"""
    task_id: str
    status: TaskStatus
    analysis_result: AnalysisResult
    frame_count: int = Field(..., description="分析的帧数量")
    model_used: str = Field(..., description="使用的模型")


class BatchTaskStatusRequest(BaseModel):
    """Batch task status query request"""
    task_ids: List[str] = Field(..., description="任务ID列表", max_length=50)
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_ids": ["task_001", "task_002", "task_003"]
            }
        }


class BatchTaskStatusResponse(BaseModel):
    """Batch task status query response"""
    results: dict = Field(..., description="任务状态字典 {task_id: TaskStatusResponse}")
    total: int = Field(..., description="查询总数")
    found: int = Field(..., description="找到的任务数")
    not_found: List[str] = Field(default_factory=list, description="未找到的任务ID列表")


class ErrorResponse(BaseModel):
    """Error response"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    detail: Optional[str] = Field(None, description="详细错误信息")
    timestamp: datetime = Field(default_factory=datetime.now)

