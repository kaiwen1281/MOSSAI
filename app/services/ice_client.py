"""Aliyun ICE (Intelligent Media Services) client for media info retrieval and snapshot jobs"""
import logging
import time
from typing import Dict, Optional, List

from alibabacloud_ice20201109.client import Client as IceClient
from alibabacloud_ice20201109 import models as ice_models
from alibabacloud_tea_openapi import models as open_api_models

from app.core.config import settings
from app.services.oss_client import oss_service

logger = logging.getLogger(__name__)


class ICEService:
    """Service for interacting with Aliyun ICE"""
    
    def __init__(self):
        """Initialize ICE client"""
        self.client = self._create_client()
        logger.info("ICE Service initialized")
    
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

    def submit_snapshot_job_with_template(
        self,
        media_id: str,
        template_id: str,
        count: Optional[int] = None,
        poll_seconds: int = 60
    ) -> List[str]:
        """
        使用指定模板提交截图任务；当 count 提供且不等于 50 时仅覆盖 Count，其它配置沿用模板（例如关键帧）。
        通过 GetSnapshotUrls 轮询获取截图URL，直到达到目标帧数或超时，返回URL列表。
        """
        try:
            if not template_id:
                raise ValueError("未配置 ICE 截图模板ID")

            # 构造 TemplateConfig（对象形式），按需覆盖 Count
            overwrite = None
            if count is not None and count != 50:
                overwrite = ice_models.SubmitSnapshotJobRequestTemplateConfigOverwriteParams(
                    count=int(count)
                )
            tpl_cfg = ice_models.SubmitSnapshotJobRequestTemplateConfig(
                template_id=template_id,
                overwrite_params=overwrite
            )

            request = ice_models.SubmitSnapshotJobRequest(
                input=ice_models.SubmitSnapshotJobRequestInput(
                    type='Media',
                    media=media_id
                ),
                output=ice_models.SubmitSnapshotJobRequestOutput(
                    type='Media',
                    media=media_id
                ),
                template_config=tpl_cfg
            )

            logger.info(
                f"Submitting ICE snapshot job: media_id={media_id}, template_id={template_id}, count={count}"
            )

            response = self.client.submit_snapshot_job(request)
            if not response or not response.body or not getattr(response.body, 'job_id', None):
                raise RuntimeError("提交截图任务失败：未返回 job_id")

            job_id = response.body.job_id
            target = int(count) if (count is not None and count > 0) else 50

            # 轮询任务状态（指数退避：10s,20s,30s,40s,50s）
            status_waits = [10, 20, 30, 40, 50]
            job_status = "Init"
            total_wait = 0
            for wait in status_waits:
                status_req = ice_models.GetSnapshotJobRequest(job_id=job_id)
                status_resp = self.client.get_snapshot_job(status_req)
                job = status_resp.body.snapshot_job if status_resp and status_resp.body else None
                job_status = job.status if job else None
                logger.info(
                    "[%s] SnapshotJob status=%s (waited %ss/%ss)",
                    job_id,
                    job_status,
                    total_wait,
                    sum(status_waits)
                )
                if job_status == "Success":
                    break
                if job_status in {"Failed", "Stop", "Cancel"}:
                    raise RuntimeError(f"ICE截图任务失败，状态: {job_status}")
                time.sleep(wait)
                total_wait += wait
            else:
                raise RuntimeError(f"ICE截图任务超时等待完成，最后状态: {job_status}")

            # 捕获截图URL，采用递增等待（0s,10s,20s,30s,40s,50s）
            safe_page_size = min(20, target) if target > 0 else 20
            max_pages = max(1, min(15, (target + safe_page_size - 1) // safe_page_size + 1))
            wait_plan = [0, 10, 20, 30, 40, 50]
            collected: List[str] = []

            for wait in wait_plan:
                if wait > 0:
                    logger.info("[%s] Waiting %ss before fetching snapshot urls", job_id, wait)
                    time.sleep(wait)

                temp_urls: List[str] = []
                for page_num in range(1, max_pages + 1):
                    get_req = ice_models.GetSnapshotUrlsRequest(
                        job_id=job_id,
                        page_size=safe_page_size,
                        page_number=page_num
                    )
                    req_map = get_req.to_map()
                    logger.info("[%s] Calling get_snapshot_urls with params: %s", job_id, req_map)
                    # 短重试以应对远端偶发断连（1s/2s/4s）
                    get_resp = None
                    last_exc: Optional[Exception] = None
                    for attempt in range(3):
                        try:
                            get_resp = self.client.get_snapshot_urls(get_req)
                            last_exc = None
                            break
                        except Exception as exc:
                            last_exc = exc
                            backoff = 1 << attempt  # 1,2,4 秒
                            logger.warning(
                                "[%s] get_snapshot_urls attempt %s failed, retry in %ss: %s",
                                job_id,
                                attempt + 1,
                                backoff,
                                exc
                            )
                            time.sleep(backoff)
                    if get_resp is None:
                        logger.error(
                            "[%s] get_snapshot_urls failed for params %s after retries: %s",
                            job_id,
                            req_map,
                            last_exc
                        )
                        raise last_exc if last_exc else RuntimeError("get_snapshot_urls failed")
                    body = get_resp.body if get_resp else None
                    returned = len(body.snapshot_urls) if body and body.snapshot_urls else 0
                    logger.info(
                        "[%s] get_snapshot_urls call: page_num=%s page_size=%s returned=%s",
                        job_id,
                        page_num,
                        get_req.page_size,
                        returned
                    )
                    if not body or not body.snapshot_urls:
                        break

                    temp_urls.extend(body.snapshot_urls)
                    if len(body.snapshot_urls) < safe_page_size:
                        break

                collected = temp_urls
                if len(collected) >= target:
                    break

            if not collected:
                raise RuntimeError(
                    f"ICE截图URL不足：期望{target} 实际{len(collected)} job_id:{job_id}"
                )

            if len(collected) < target:
                logger.warning(
                    "[%s] 仅获取到 %s/%s 帧，继续使用现有帧进行分析",
                    job_id,
                    len(collected),
                    target
                )

            final_urls = collected[:target]
            logger.info(f"ICE snapshot generated {len(final_urls)} urls for job {job_id}")
            return final_urls
        except Exception as e:
            logger.error(f"SubmitSnapshotJob failed: {e}")
            raise


# Global service instance
ice_service = ICEService()

