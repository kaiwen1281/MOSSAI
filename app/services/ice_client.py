"""Aliyun ICE (Intelligent Media Services) client for media info retrieval"""
import logging
from typing import Dict, Optional

from alibabacloud_ice20201109.client import Client as IceClient
from alibabacloud_ice20201109 import models as ice_models
from alibabacloud_tea_openapi import models as open_api_models

from app.core.config import settings

logger = logging.getLogger(__name__)


class ICEService:
    """Service for interacting with Aliyun ICE - Media Info Only"""
    
    def __init__(self):
        """Initialize ICE client"""
        self.client = self._create_client()
        logger.info("ICE Service initialized (Media Info Only)")
    
    def _create_client(self) -> IceClient:
        """Create and configure ICE client"""
        config = open_api_models.Config(
            access_key_id=settings.aliyun_access_key_id,
            access_key_secret=settings.aliyun_access_key_secret,
            region_id=settings.aliyun_ice_region,
        )
        
        if settings.aliyun_ice_endpoint:
            config.endpoint = settings.aliyun_ice_endpoint
        else:
            config.endpoint = f"ice.{settings.aliyun_ice_region}.aliyuncs.com"
        
        return IceClient(config)
    
    def get_media_info(self, media_id: str) -> Dict:
        """
        Get media information from ICE
        
        Args:
            media_id: ICE media ID
            
        Returns:
            Dict containing media info (duration, resolution, etc.)
        """
        try:
            request = ice_models.GetMediaInfoRequest(
                media_id=media_id,
                input_url=None
            )
            
            response = self.client.get_media_info(request)
            
            if not response.body:
                raise ValueError(f"No media info found for media_id: {media_id}")
            
            media_info = response.body.media_info
            
            # Extract video stream info and file URL
            video_stream = None
            file_url = None
            
            if media_info.file_info_list and len(media_info.file_info_list) > 0:
                file_info = media_info.file_info_list[0]
                file_basic_info = file_info.file_basic_info
                duration = file_basic_info.duration if file_basic_info else None
                
                # Extract file URL (OSS path)
                if file_basic_info and hasattr(file_basic_info, 'file_url'):
                    file_url = file_basic_info.file_url
                    logger.info(f"Extracted file URL from ICE: {file_url}")
                
                # Get video stream info
                if file_basic_info and file_basic_info.format_name:
                    video_stream = {
                        "duration": float(duration) if duration else 0.0,
                        "width": file_basic_info.width if hasattr(file_basic_info, 'width') else None,
                        "height": file_basic_info.height if hasattr(file_basic_info, 'height') else None,
                        "format": file_basic_info.format_name,
                    }
            
            result = {
                "media_id": media_id,
                "title": media_info.media_basic_info.title if media_info.media_basic_info else None,
                "duration": video_stream.get("duration") if video_stream else 0.0,
                "width": video_stream.get("width") if video_stream else None,
                "height": video_stream.get("height") if video_stream else None,
                "format": video_stream.get("format") if video_stream else None,
                "resolution": f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream and video_stream.get('width') else None,
                "file_url": file_url,  # 添加原始文件URL
            }
            
            logger.info(f"Retrieved media info for {media_id}: duration={result['duration']}s, resolution={result['resolution']}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting media info for {media_id}: {str(e)}")
            raise


# Global service instance
ice_service = ICEService()

