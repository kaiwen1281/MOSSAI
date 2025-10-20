"""Aliyun OSS client for file storage and management"""
import logging
import json
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path

import oss2
from oss2 import Auth

from app.core.config import settings
from app.models.schemas import FrameInfo, FrameIndexData, FrameLevel

logger = logging.getLogger(__name__)


class OSSService:
    """Service for interacting with Aliyun OSS"""
    
    def __init__(self):
        """Initialize OSS client"""
        # Use separate OSS credentials if provided, otherwise use ICE credentials
        oss_key_id = settings.oss_access_key_id or settings.aliyun_access_key_id
        oss_key_secret = settings.oss_access_key_secret or settings.aliyun_access_key_secret
        
        self.auth = Auth(oss_key_id, oss_key_secret)
        self.bucket = oss2.Bucket(
            self.auth,
            settings.aliyun_oss_endpoint,
            settings.aliyun_oss_bucket
        )
    
    def generate_oss_path(
        self,
        brand_name: str,
        moss_id: str,
        filename: Optional[str] = None
    ) -> str:
        """
        Generate OSS path following the structure:
        {brand_name}/{YYYY-MM}/video_frames/{moss_id}/[filename]
        
        Args:
            brand_name: Brand name
            moss_id: MOSS video ID
            filename: Optional filename (if not provided, returns directory path)
            
        Returns:
            OSS path string
        """
        year_month = datetime.now().strftime("%Y-%m")
        base_path = f"{brand_name}/{year_month}/video_frames/{moss_id}"
        
        if filename:
            return f"{base_path}/{filename}"
        return base_path
    
    def list_frames(self, oss_directory: str) -> List[str]:
        """
        List all frame files in an OSS directory
        
        Args:
            oss_directory: OSS directory path
            
        Returns:
            List of frame file paths (sorted by name)
        """
        try:
            # Ensure directory ends with /
            if not oss_directory.endswith('/'):
                oss_directory += '/'
            
            frame_files = []
            
            # List all objects with the prefix
            for obj in oss2.ObjectIterator(self.bucket, prefix=oss_directory):
                # Filter for image files
                if obj.key.lower().endswith(('.jpg', '.jpeg', '.png')):
                    frame_files.append(obj.key)
            
            # Sort by filename to maintain time order
            frame_files.sort()
            
            logger.info(f"Found {len(frame_files)} frames in {oss_directory}")
            return frame_files
            
        except Exception as e:
            logger.error(f"Error listing frames in {oss_directory}: {str(e)}")
            raise
    
    def generate_signed_url(self, oss_path: str, expires: Optional[int] = None) -> str:
        """
        Generate a signed URL for an OSS object
        
        Args:
            oss_path: OSS object path
            expires: URL expiration time in seconds (default from settings)
            
        Returns:
            Signed URL string
        """
        try:
            if expires is None:
                expires = settings.aliyun_oss_url_expire
            
            url = self.bucket.sign_url('GET', oss_path, expires)
            return url
            
        except Exception as e:
            logger.error(f"Error generating signed URL for {oss_path}: {str(e)}")
            raise
    
    def generate_frame_urls(
        self,
        frame_paths: List[str],
        expires: Optional[int] = None
    ) -> List[str]:
        """
        Generate signed URLs for multiple frame files
        
        Args:
            frame_paths: List of OSS frame paths
            expires: URL expiration time in seconds
            
        Returns:
            List of signed URLs
        """
        urls = []
        for path in frame_paths:
            url = self.generate_signed_url(path, expires)
            urls.append(url)
        
        logger.info(f"Generated {len(urls)} signed URLs")
        return urls
    
    def upload_file(self, oss_path: str, local_file_path: str) -> str:
        """
        Upload a local file to OSS
        
        Args:
            oss_path: Target OSS path
            local_file_path: Local file path
            
        Returns:
            OSS path of uploaded file
        """
        try:
            with open(local_file_path, 'rb') as f:
                self.bucket.put_object(oss_path, f)
            
            logger.info(f"Uploaded {local_file_path} to {oss_path}")
            return oss_path
            
        except Exception as e:
            logger.error(f"Error uploading {local_file_path} to {oss_path}: {str(e)}")
            raise
    
    def upload_content(self, oss_path: str, content: bytes) -> str:
        """
        Upload content (bytes) to OSS
        
        Args:
            oss_path: Target OSS path
            content: File content as bytes
            
        Returns:
            OSS path of uploaded content
        """
        try:
            self.bucket.put_object(oss_path, content)
            logger.info(f"Uploaded content to {oss_path}")
            return oss_path
            
        except Exception as e:
            logger.error(f"Error uploading content to {oss_path}: {str(e)}")
            raise
    
    def create_frame_index(
        self,
        index_data: FrameIndexData,
        oss_directory: str
    ) -> str:
        """
        Create and upload frame index JSON file
        
        Args:
            index_data: Frame index metadata
            oss_directory: OSS directory path
            
        Returns:
            OSS path of index file
        """
        try:
            # Create index.json path
            index_path = f"{oss_directory}/index.json"
            
            # Convert to JSON
            index_json = index_data.model_dump_json(indent=2)
            
            # Upload to OSS
            self.bucket.put_object(index_path, index_json.encode('utf-8'))
            
            logger.info(f"Created frame index at {index_path}")
            return index_path
            
        except Exception as e:
            logger.error(f"Error creating frame index: {str(e)}")
            raise
    
    def get_frame_index(self, oss_directory: str) -> Optional[FrameIndexData]:
        """
        Retrieve and parse frame index JSON file
        
        Args:
            oss_directory: OSS directory path
            
        Returns:
            FrameIndexData object or None if not found
        """
        try:
            index_path = f"{oss_directory}/index.json"
            
            # Download index file
            result = self.bucket.get_object(index_path)
            content = result.read().decode('utf-8')
            
            # Parse JSON
            index_data = FrameIndexData.model_validate_json(content)
            
            logger.info(f"Retrieved frame index from {index_path}")
            return index_data
            
        except oss2.exceptions.NoSuchKey:
            logger.warning(f"Frame index not found at {oss_directory}/index.json")
            return None
        except Exception as e:
            logger.error(f"Error getting frame index: {str(e)}")
            raise
    
    def build_frame_info_list(
        self,
        frame_paths: List[str],
        frame_interval: Optional[float] = None
    ) -> List[FrameInfo]:
        """
        Build list of FrameInfo objects from frame paths
        
        Args:
            frame_paths: List of OSS frame paths (sorted)
            frame_interval: Time interval between frames (seconds)
            
        Returns:
            List of FrameInfo objects
        """
        frame_infos = []
        
        for idx, path in enumerate(frame_paths):
            # Calculate timestamp
            timestamp = idx * frame_interval if frame_interval else 0.0
            
            # Generate signed URL
            url = self.generate_signed_url(path)
            
            frame_info = FrameInfo(
                frame_number=idx + 1,
                timestamp=timestamp,
                url=url,
                oss_path=path
            )
            frame_infos.append(frame_info)
        
        return frame_infos
    
    def delete_directory(self, oss_directory: str) -> int:
        """
        Delete all files in an OSS directory
        
        Args:
            oss_directory: OSS directory path
            
        Returns:
            Number of files deleted
        """
        try:
            if not oss_directory.endswith('/'):
                oss_directory += '/'
            
            deleted_count = 0
            
            # List and delete all objects
            for obj in oss2.ObjectIterator(self.bucket, prefix=oss_directory):
                self.bucket.delete_object(obj.key)
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} files from {oss_directory}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error deleting directory {oss_directory}: {str(e)}")
            raise
    
    def extract_frames_by_oss(
        self,
        video_oss_path: str,
        video_duration: float,
        frame_level: FrameLevel = FrameLevel.MEDIUM
    ) -> List[FrameInfo]:
        """
        使用OSS video/snapshot实时处理抽帧
        
        Args:
            video_oss_path: 视频在OSS中的路径（不含bucket）
            video_duration: 视频时长（秒）
            frame_level: 抽帧等级 (low/medium/high)
            
        Returns:
            帧信息列表
        """
        try:
            # 1. 获取抽帧间隔
            interval_map = {
                FrameLevel.LOW: settings.frame_level_low,
                FrameLevel.MEDIUM: settings.frame_level_medium,
                FrameLevel.HIGH: settings.frame_level_high,
            }
            interval = interval_map.get(frame_level, settings.frame_level_medium)
            
            # 2. 计算时间点列表
            time_points = []
            current = 0.0
            frame_number = 1
            
            while current < video_duration:
                time_points.append({
                    'frame_number': frame_number,
                    'timestamp': current,
                    'time_ms': int(current * 1000)  # 转为毫秒
                })
                current += interval
                frame_number += 1
            
            logger.info(f"Calculated {len(time_points)} frames for video (duration={video_duration}s, interval={interval}s)")
            
            # 3. 为每个时间点生成OSS处理URL
            frames = []
            for point in time_points:
                # 构建OSS处理参数
                process_params = (
                    f"video/snapshot,"
                    f"t_{point['time_ms']},"           # 时间点（毫秒）
                    f"f_{settings.frame_format},"      # 格式：jpg
                    f"w_{settings.frame_width},"       # 宽度
                    f"m_fast"                          # 快速模式
                )
                
                # 生成签名URL
                frame_url = self._generate_video_snapshot_url(
                    video_oss_path,
                    process_params
                )
                
                frames.append(FrameInfo(
                    frame_number=point['frame_number'],
                    timestamp=point['timestamp'],
                    url=frame_url,
                    oss_path=video_oss_path  # 原始视频路径
                ))
            
            logger.info(f"Generated {len(frames)} frame URLs using OSS video/snapshot")
            return frames
            
        except Exception as e:
            logger.error(f"Error extracting frames by OSS: {str(e)}")
            raise
    
    def _generate_video_snapshot_url(
        self,
        video_oss_path: str,
        process_params: str
    ) -> str:
        """
        生成带视频截帧参数的OSS签名URL（预览模式，非下载）
        
        Args:
            video_oss_path: 视频OSS路径
            process_params: OSS处理参数字符串
            
        Returns:
            完整的签名URL（预览模式）
        """
        try:
            # 构建查询参数 - 包含OSS处理参数和响应头参数
            params = {
                'x-oss-process': process_params,
                # 重要：设置为inline（预览）而不是attachment（下载）
                # 注意：video/snapshot已经返回图片格式，不需要设置response-content-type
                'response-content-disposition': 'inline'
            }
            
            # 生成签名URL
            url = self.bucket.sign_url(
                'GET',
                video_oss_path,
                settings.aliyun_oss_url_expire,
                slash_safe=True,
                params=params
            )
            
            logger.debug(f"Generated preview URL for {video_oss_path[:50]}...")
            return url
            
        except Exception as e:
            logger.error(f"Error generating video snapshot URL: {str(e)}")
            raise

    def generate_image_thumbnail(
        self,
        image_oss_path: str,
        quality: int = 90,
        max_width: int = 1280,
        max_height: int = 1280
    ) -> str:
        """
        生成图片缩略图URL
        
        Args:
            image_oss_path: 图片在OSS中的路径（不含bucket）
            quality: 图片质量 (1-100)
            max_width: 最大宽度
            max_height: 最大高度
            
        Returns:
            缩略图访问URL
        """
        try:
            # 构建阿里云OSS图片处理参数
            # 使用resize参数保持高质量，w和h为最大宽高限制，m_lfit表示等比缩放不超过限制
            process_params = f"image/resize,m_lfit,w_{max_width},h_{max_height}/quality,q_{quality}"
            
            # 构建查询参数
            params = {
                'x-oss-process': process_params,
                'response-content-disposition': 'inline'
            }
            
            # 生成签名URL
            thumbnail_url = self.bucket.sign_url(
                'GET',
                image_oss_path,
                settings.aliyun_oss_url_expire,
                slash_safe=True,
                params=params
            )
            
            logger.info(f"Generated thumbnail URL for image: {image_oss_path}")
            return thumbnail_url
            
        except Exception as e:
            logger.error(f"Error generating thumbnail for {image_oss_path}: {str(e)}")
            raise ValueError(f"缩略图生成失败: {str(e)}")


# Global service instance
oss_service = OSSService()

