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
    frame_level: FrameLevel = Field(..., description="抽帧等级: low/medium/high/smart")
    smart_frame_count: Optional[int] = Field(
        default=None,
        ge=1,
        le=200,
        description="智能模式目标帧数（1-200）；未传则使用默认50"
    )
    transcript_url: Optional[str] = Field(
        default=None,
        description="字幕文件OSS URL（可选）；如果提供，将进行画面+字幕联合分析"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "moss_id": "video_20231017_001",
                "brand_name": "nike",
                "media_id": "****0343c45e0ce64664a",
                "frame_level": "smart",
                "smart_frame_count": 100,
                "transcript_url": "https://oss.../transcripts/xxx.json"
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


class ShortVideoTaggingResult(BaseModel):
    """短视频素材打标结果"""
    main_subject: str = Field(..., description="核心主体：简短精准地描述画面最主要的焦点物体或人物")
    action_or_event: str = Field(..., description="动作或事件：描述素材中发生的核心动态或静态事件")
    scene_setting: str = Field(..., description="场景设置：详细描述地点、环境光照等")
    visual_style: str = Field(..., description="视觉风格：提取素材的拍摄技巧和画面质感")
    color_palette: str = Field(..., description="色彩基调：描述画面主要的色彩倾向")
    emotion_dominant: str = Field(..., description="主导情感：只使用一个词汇总结素材传达的最强烈的情绪")
    atmosphere_tags: List[str] = Field(default_factory=list, description="氛围标签：3-5个用于描述素材整体氛围的标签")
    viral_meme_tags: List[str] = Field(default_factory=list, description="网络热梗标签：3-5个具体的热梗名称或核心概念，无相关则为空列表")
    keywords: List[str] = Field(default_factory=list, description="关键词：5-10个高度相关的检索关键词")
    
    class Config:
        json_schema_extra = {
            "example": {
                "main_subject": "年轻女性",
                "action_or_event": "在镜头前做手势舞蹈",
                "scene_setting": "室内卧室，柔和自然光照",
                "visual_style": "竖屏拍摄，近景特写，手持设备轻微抖动",
                "color_palette": "暖色调为主，粉色和米白色",
                "emotion_dominant": "活力",
                "atmosphere_tags": ["青春", "活泼", "日常", "治愈"],
                "viral_meme_tags": ["手势舞", "卧室挑战"],
                "keywords": ["女性", "舞蹈", "手势", "卧室", "青春", "活力", "日常"]
            }
        }


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


class SingleImageTaggingResult(BaseModel):
    """单张图片打标结果"""
    main_subject: str = Field(..., description="核心主体：简短精准地描述画面最主要的焦点物体或人物")
    subject_state: str = Field(..., description="主体状态：描述核心主体所处的具体动作或状态")
    scene_setting: str = Field(..., description="场景设置：详细描述地点、环境、时间等背景信息")
    composition_style: str = Field(..., description="构图与风格：提取图片的构图方式和拍摄角度特点")
    color_lighting: str = Field(..., description="色彩与光线：描述画面主要的色彩倾向和光线类型")
    emotion_dominant: str = Field(..., description="主导情感：只使用一个词汇总结图片传达的最强烈的情绪")
    atmosphere_tags: List[str] = Field(default_factory=list, description="氛围标签：3-5个用于描述图片整体氛围的标签")
    viral_meme_tags: List[str] = Field(default_factory=list, description="网络热梗标签：3-5个具体的热梗名称或核心概念，无相关则为空列表")
    keywords: List[str] = Field(default_factory=list, description="关键词：5-10个高度相关的检索关键词")
    
    class Config:
        json_schema_extra = {
            "example": {
                "main_subject": "年轻女性",
                "subject_state": "微笑着看向镜头",
                "scene_setting": "室内咖啡厅，温暖的下午光线",
                "composition_style": "中景人像，三分法构图",
                "color_lighting": "暖色调，柔和自然光",
                "emotion_dominant": "愉悦",
                "atmosphere_tags": ["温馨", "休闲", "文艺", "舒适"],
                "viral_meme_tags": ["咖啡文化", "都市生活"],
                "keywords": ["女性", "咖啡厅", "微笑", "室内", "温暖", "休闲", "都市"]
            }
        }


class ImageAnalysisRequest(BaseModel):
    """单张图片分析请求"""
    moss_id: str = Field(..., description="MOSS系统中的图片ID")
    brand_name: str = Field(..., description="品牌方名称")
    media_id: str = Field(..., description="阿里云ICE媒资ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "moss_id": "image_20231017_001",
                "brand_name": "nike",
                "media_id": "****0343c45e0ce64664a"
            }
        }


class TimelineSegmentTagging(BaseModel):
    """时间轴片段打标结果（与整体视频打标结构一致）"""
    start_time: float = Field(..., description="开始时间（秒）")
    end_time: float = Field(..., description="结束时间（秒）")
    spoken_content: Optional[str] = Field(None, description="这段时间的语音内容（ASR识别结果）")
    
    # 9个标准打标字段
    main_subject: str = Field(..., description="核心主体")
    action_or_event: str = Field(..., description="动作或事件")
    scene_setting: str = Field(..., description="场景设置")
    visual_style: str = Field(..., description="视觉风格")
    color_palette: str = Field(..., description="色彩基调")
    emotion_dominant: str = Field(..., description="主导情感")
    atmosphere_tags: List[str] = Field(default_factory=list, description="氛围标签")
    viral_meme_tags: List[str] = Field(default_factory=list, description="网络热梗标签")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    
    # 辅助字段
    frame_range: Optional[str] = Field(None, description="对应的帧范围，如 '1-15'")
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_time": 0.0,
                "end_time": 30.5,
                "spoken_content": "大家好，欢迎来到新品发布会。今天我们将介绍...",
                "main_subject": "主持人和产品LOGO",
                "action_or_event": "开场介绍，展示产品外观",
                "scene_setting": "舞台中央，背景大屏显示产品图片",
                "visual_style": "全景镜头，主持人正面特写",
                "color_palette": "蓝白色调，明亮照明",
                "emotion_dominant": "期待",
                "atmosphere_tags": ["开场", "介绍", "专业"],
                "viral_meme_tags": [],
                "keywords": ["新品", "发布会", "欢迎"],
                "frame_range": "1-15"
            }
        }


class VideoAnalysisWithTranscriptResult(BaseModel):
    """带字幕的视频分析结果"""
    # 整体视频打标
    overall_tagging: ShortVideoTaggingResult = Field(..., description="整体视频的打标结果")
    
    # 时间轴片段打标
    timeline_segments: List[TimelineSegmentTagging] = Field(
        default_factory=list,
        description="时间轴片段数组，每个片段包含完整的打标信息"
    )
    
    # 元数据
    metadata: dict = Field(
        default_factory=dict,
        description="元数据信息（视频时长、分辨率、模型等）"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "overall_tagging": {
                    "main_subject": "产品发布会，主讲人介绍新款智能手机",
                    "action_or_event": "产品功能演示和技术讲解",
                    "scene_setting": "室内会议厅，专业舞台灯光",
                    "visual_style": "专业录制，多机位切换",
                    "color_palette": "蓝白色调为主",
                    "emotion_dominant": "专业",
                    "atmosphere_tags": ["科技", "专业", "商务"],
                    "viral_meme_tags": ["新品发布"],
                    "keywords": ["iPhone", "智能手机", "5G"]
                },
                "timeline_segments": [
                    {
                        "start_time": 0.0,
                        "end_time": 30.5,
                        "spoken_content": "大家好，欢迎...",
                        "main_subject": "主持人开场",
                        "keywords": ["欢迎", "介绍"]
                    }
                ],
                "metadata": {
                    "video_duration": 600.0,
                    "total_segments": 10
                }
            }
        }

