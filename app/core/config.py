"""Application configuration using pydantic-settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application
    app_name: str = "MOSS-AI"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # Service Configuration
    mossai_port: int = 8001
    mossai_host: str = "0.0.0.0"
    
    # Aliyun ICE Configuration
    aliyun_access_key_id: str
    aliyun_access_key_secret: str
    aliyun_ice_region: str = "cn-shanghai"
    aliyun_ice_endpoint: str = "ice.cn-shanghai.aliyuncs.com"
    
    # Aliyun OSS Configuration
    aliyun_oss_endpoint: str
    aliyun_oss_bucket: str
    aliyun_oss_url_expire: int = 86400  # 24 hours in seconds
    
    # OSS Separate Credentials (if different from ICE)
    oss_access_key_id: Optional[str] = None
    oss_access_key_secret: Optional[str] = None
    
    # Doubao (Volcengine) Configuration
    doubao_api_key: str
    doubao_endpoint: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_model: str = "doubao-pro"  # 可选: doubao-vision, doubao-pro, doubao-pro-32k
    doubao_max_images: int = 30  # 单次最大图片数
    doubao_max_tokens: int = 8192  # 豆包模型最大tokens（实际max: 12288，设8192更安全）
    
    # Frame Extraction Levels
    frame_level_low: int = 10  # 10 seconds per frame
    frame_level_medium: int = 3  # 3 seconds per frame (default)
    frame_level_high: int = 1  # 1 second per frame
    
    # Frame Configuration
    frame_width: int = 1280  # Output frame width
    frame_format: str = "jpg"  # jpg or png
    frame_quality: int = 95
    
    # Task Polling Configuration
    poll_interval: int = 5  # seconds
    poll_max_attempts: int = 360  # 30 minutes max (360 * 5s)
    
    # Concurrency Control
    max_concurrent_tasks: int = 3
    max_extraction_concurrent: int = 5  # 抽帧最大并发数
    max_analysis_concurrent: int = 3    # AI分析最大并发数
    
    # Task Cleanup Configuration
    task_cleanup_interval: int = 1800           # 清理检查间隔：30分钟（秒）
    task_pending_timeout: int = 3600            # PENDING超时：1小时（秒）
    task_processing_timeout: int = 7200         # PROCESSING超时：2小时（秒）
    task_completed_retain: int = 172800         # 已完成任务保留：48小时（秒）
    task_failed_retain: int = 172800            # 失败任务保留：48小时（秒）
    max_tasks_in_memory: int = 1000             # 内存中最大任务数
    
    # Logging
    log_level: str = "INFO"
    

# Global settings instance
settings = Settings()

