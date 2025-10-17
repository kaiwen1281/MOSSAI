"""Doubao (Volcengine) AI model client for video/image analysis"""
import logging
from typing import List, Optional, Dict
import json

import httpx

from app.core.config import settings
from app.models.schemas import AnalysisResult, ShortVideoTaggingResult

logger = logging.getLogger(__name__)


class DoubaoService:
    """Service for interacting with Doubao AI models"""
    
    def __init__(self):
        """Initialize Doubao client"""
        self.api_key = settings.doubao_api_key
        self.endpoint = settings.doubao_endpoint
        self.model = settings.doubao_model
        self.max_images = settings.doubao_max_images
        self.max_tokens = settings.doubao_max_tokens
    
    def _build_messages(
        self,
        image_urls: List[str],
        context: Optional[Dict] = None,
        custom_prompt: Optional[str] = None
    ) -> List[Dict]:
        """
        Build messages for Doubao API
        
        Args:
            image_urls: List of image URLs
            context: Video context (duration, resolution, etc.)
            custom_prompt: Custom analysis prompt
            
        Returns:
            List of message dicts
        """
        # Build system prompt
        system_content = """你是一个专业的视频内容分析助手。请根据提供的视频帧图片序列，分析视频的内容。

请按以下格式返回JSON结果：
{
    "summary": "一句话概括视频主要内容",
    "detailed_content": "详细描述视频的内容，包括场景、人物、动作、对话等",
    "tags": ["标签1", "标签2", "标签3"],
    "key_moments": [
        {"timestamp": 0.0, "description": "关键时刻描述"}
    ]
}

注意：
1. 图片是按时间顺序排列的视频帧
2. 分析要关注内容的连续性和变化
3. 标签要准确、有代表性
4. 详细内容要完整、结构清晰
"""
        
        # Build user prompt
        user_parts = []
        
        # Add context if provided
        if context:
            context_text = "**视频信息：**\n"
            if context.get("duration"):
                context_text += f"- 时长：{context['duration']:.1f}秒\n"
            if context.get("resolution"):
                context_text += f"- 分辨率：{context['resolution']}\n"
            if context.get("frame_count"):
                context_text += f"- 帧数量：{context['frame_count']}帧\n"
            
            user_parts.append({"type": "text", "text": context_text})
        
        # Add custom prompt if provided
        if custom_prompt:
            user_parts.append({"type": "text", "text": f"**分析要求：**\n{custom_prompt}\n"})
        
        # Add instruction
        user_parts.append({
            "type": "text",
            "text": "请分析以下视频帧序列（按时间顺序）："
        })
        
        # Add images
        for idx, url in enumerate(image_urls):
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_parts}
        ]
        
        return messages
    
    async def analyze_frames(
        self,
        frame_urls: List[str],
        context: Optional[Dict] = None,
        custom_prompt: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze video frames with Doubao AI
        
        Args:
            frame_urls: List of frame image URLs (in time order)
            context: Video context information
            custom_prompt: Custom analysis prompt
            
        Returns:
            AnalysisResult object
        """
        try:
            # Check frame count
            if len(frame_urls) > self.max_images:
                logger.warning(
                    f"Frame count {len(frame_urls)} exceeds max {self.max_images}. "
                    f"Will use segmented analysis."
                )
                return await self._segmented_analysis(frame_urls, context, custom_prompt)
            
            # Build messages
            messages = self._build_messages(frame_urls, context, custom_prompt)
            
            # Call Doubao API
            response_data = await self._call_api(messages)
            
            # Parse response
            result = self._parse_response(response_data)
            
            logger.info(f"Successfully analyzed {len(frame_urls)} frames")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing frames: {str(e)}")
            raise
    
    async def _call_api(self, messages: List[Dict]) -> Dict:
        """
        Call Doubao API
        
        Args:
            messages: List of message dicts
            
        Returns:
            API response data
        """
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.endpoint}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "max_tokens": self.max_tokens,
                        "temperature": 0.7,
                    }
                )
                
                if response.status_code != 200:
                    error_detail = response.text
                    logger.error(
                        f"Doubao API error (status {response.status_code}): {error_detail}"
                    )
                    # Try to parse error as JSON for better error message
                    try:
                        error_json = response.json()
                        error_msg = error_json.get("error", {}).get("message", error_detail)
                        raise ValueError(f"Doubao API error: {error_msg}")
                    except (ValueError, KeyError):
                        raise ValueError(f"Doubao API error (status {response.status_code}): {error_detail}")
                
                return response.json()
                
        except ValueError:
            # Re-raise ValueError (our custom error messages)
            raise
        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling Doubao API: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error calling Doubao API: {str(e)}")
            raise
    
    def _parse_response(self, response_data: Dict) -> AnalysisResult:
        """
        Parse Doubao API response
        
        Args:
            response_data: API response data
            
        Returns:
            AnalysisResult object
        """
        try:
            # Extract content from response
            if "choices" not in response_data or len(response_data["choices"]) == 0:
                raise ValueError("No choices in response")
            
            content = response_data["choices"][0]["message"]["content"]
            
            # Try to parse as JSON
            try:
                # Find JSON block in markdown code block if present
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    json_str = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    json_str = content[json_start:json_end].strip()
                else:
                    json_str = content
                
                parsed = json.loads(json_str)
                
                return AnalysisResult(
                    summary=parsed.get("summary", ""),
                    detailed_content=parsed.get("detailed_content", ""),
                    tags=parsed.get("tags", []),
                    segments=parsed.get("key_moments", []),
                    raw_response=response_data
                )
                
            except json.JSONDecodeError:
                # If not valid JSON, treat as plain text
                logger.warning("Response is not valid JSON, treating as plain text")
                return AnalysisResult(
                    summary=content[:200],  # First 200 chars as summary
                    detailed_content=content,
                    tags=[],
                    segments=None,
                    raw_response=response_data
                )
                
        except Exception as e:
            logger.error(f"Error parsing response: {str(e)}")
            raise
    
    async def _segmented_analysis(
        self,
        frame_urls: List[str],
        context: Optional[Dict] = None,
        custom_prompt: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze video in segments when frame count exceeds limit
        
        Args:
            frame_urls: List of frame URLs
            context: Video context
            custom_prompt: Custom prompt
            
        Returns:
            Combined AnalysisResult
        """
        try:
            # Split frames into segments
            segment_size = self.max_images
            segments = [
                frame_urls[i:i + segment_size]
                for i in range(0, len(frame_urls), segment_size)
            ]
            
            logger.info(f"Analyzing {len(frame_urls)} frames in {len(segments)} segments")
            
            # Analyze each segment
            segment_results = []
            total_duration = context.get("duration", 0) if context else 0
            
            for idx, segment_urls in enumerate(segments):
                # Calculate segment time range
                segment_start = (idx * segment_size / len(frame_urls)) * total_duration
                segment_end = ((idx + 1) * segment_size / len(frame_urls)) * total_duration
                
                segment_context = {
                    **(context or {}),
                    "segment": f"{idx + 1}/{len(segments)}",
                    "time_range": f"{segment_start:.1f}s - {segment_end:.1f}s"
                }
                
                segment_prompt = (
                    f"这是视频的第 {idx + 1}/{len(segments)} 段 "
                    f"(时间范围: {segment_start:.1f}s - {segment_end:.1f}s)。\n"
                )
                if custom_prompt:
                    segment_prompt += custom_prompt
                
                # Analyze segment
                result = await self.analyze_frames(
                    segment_urls,
                    segment_context,
                    segment_prompt
                )
                segment_results.append(result)
            
            # Combine segment results
            combined_result = await self._combine_segment_results(
                segment_results,
                len(frame_urls),
                context
            )
            
            return combined_result
            
        except Exception as e:
            logger.error(f"Error in segmented analysis: {str(e)}")
            raise
    
    async def _combine_segment_results(
        self,
        segment_results: List[AnalysisResult],
        total_frames: int,
        context: Optional[Dict] = None
    ) -> AnalysisResult:
        """
        Combine multiple segment analysis results
        
        Args:
            segment_results: List of segment AnalysisResults
            total_frames: Total number of frames
            context: Video context
            
        Returns:
            Combined AnalysisResult
        """
        try:
            # Prepare summary of all segments
            segments_summary = []
            all_tags = []
            
            for idx, result in enumerate(segment_results):
                segments_summary.append(
                    f"**第 {idx + 1} 段:** {result.summary}\n{result.detailed_content[:200]}..."
                )
                all_tags.extend(result.tags)
            
            # Build prompt for final combination
            combine_prompt = f"""我已经对一个视频的 {len(segment_results)} 个片段进行了分析。
以下是各片段的分析结果：

{chr(10).join(segments_summary)}

请基于这些片段分析，给出视频的完整总结。
"""
            
            # Call API to combine
            messages = [
                {"role": "system", "content": "你是视频内容分析助手，请综合多个片段的分析结果，给出完整的视频内容总结。"},
                {"role": "user", "content": combine_prompt}
            ]
            
            response_data = await self._call_api(messages)
            combined = self._parse_response(response_data)
            
            # Merge tags (remove duplicates)
            combined.tags = list(set(all_tags + combined.tags))
            
            # Add segment information
            combined.segments = [
                {
                    "segment": idx + 1,
                    "summary": result.summary,
                    "tags": result.tags
                }
                for idx, result in enumerate(segment_results)
            ]
            
            logger.info(f"Combined {len(segment_results)} segment results")
            return combined
            
        except Exception as e:
            logger.error(f"Error combining segment results: {str(e)}")
            # Fallback: return first segment result with all tags
            fallback = segment_results[0]
            fallback.tags = list(set(all_tags))
            fallback.detailed_content = "\n\n".join(
                r.detailed_content for r in segment_results
            )
            return fallback
    
    async def analyze_single_image(
        self,
        image_url: str,
        custom_prompt: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze a single image
        
        Args:
            image_url: Image URL
            custom_prompt: Custom analysis prompt
            
        Returns:
            AnalysisResult object
        """
        try:
            system_prompt = "你是一个专业的图片内容分析助手。请详细分析图片的内容。"
            
            user_parts = [
                {"type": "text", "text": custom_prompt or "请分析这张图片的内容："},
                {"type": "image_url", "image_url": {"url": image_url}}
            ]
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_parts}
            ]
            
            response_data = await self._call_api(messages)
            result = self._parse_response(response_data)
            
            logger.info(f"Successfully analyzed single image")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing single image: {str(e)}")
            raise
    
    async def analyze_short_video_frames(
        self,
        frame_urls: List[str],
        context: Optional[Dict] = None
    ) -> ShortVideoTaggingResult:
        """
        专门用于短视频素材打标的帧分析
        
        Args:
            frame_urls: List of frame image URLs (in time order)
            context: Video context information (duration, resolution, etc.)
            
        Returns:
            ShortVideoTaggingResult object
        """
        try:
            # Check frame count
            if len(frame_urls) > self.max_images:
                logger.warning(
                    f"Frame count {len(frame_urls)} exceeds max {self.max_images}. "
                    f"Will use first {self.max_images} frames for short video tagging."
                )
                frame_urls = frame_urls[:self.max_images]
            
            # Build messages for short video tagging
            messages = self._build_short_video_tagging_messages(frame_urls, context)
            
            # Call Doubao API
            response_data = await self._call_api(messages)
            
            # Parse response
            result = self._parse_short_video_tagging_response(response_data)
            
            logger.info(f"Successfully analyzed {len(frame_urls)} frames for short video tagging")
            return result
            
        except Exception as e:
            logger.error(f"Error analyzing short video frames: {str(e)}")
            raise
    
    def _build_short_video_tagging_messages(
        self,
        image_urls: List[str],
        context: Optional[Dict] = None
    ) -> List[Dict]:
        """
        构建短视频素材打标的消息
        
        Args:
            image_urls: List of image URLs
            context: Video context (duration, resolution, etc.)
            
        Returns:
            List of message dicts
        """
        # 使用用户提供的完整提示词
        system_content = """你是一位专业的素材分析师和内容标签专家。你的任务是基于一系列视频抽帧图片，对该素材片段进行细致的、聚焦于画面和情感的分析。你需要将所有抽帧作为一个整体，理解素材的核心内容、视觉特征以及情绪氛围，并严格按照提供的 JSON 格式输出结果。

请对输入的图片序列进行分析，并生成以下字段的内容：

1. Main Subject (核心主体): 简短精准地描述画面最主要的焦点物体或人物。
2. Action or Event (动作或事件): 描述素材中发生的核心动态或静态事件。
3. Scene Setting (场景设置): 详细描述地点（如：城市高楼顶部的户外，深夜）、环境光照等。
4. Visual Style (视觉风格): 提取素材的拍摄技巧和画面质感（如：特写、手持镜头抖动、高饱和度）。
5. Color Palette (色彩基调): 描述画面主要的色彩倾向。
6. Emotion Dominant (主导情感): **只使用一个词汇**总结素材传达的最强烈的情绪（如：'平静'）。
7. Atmosphere Tags (氛围标签): 列出 3-5 个用于描述素材整体氛围的标签（如：'治愈'，'浪漫'，'未来主义'）。
8. **Viral Meme Tags (网络热梗标签):** 基于画面内容、主题或风格，识别素材是否属于当前流行的**网络热梗、挑战或病毒式传播的趋势**。列出 3-5 个具体的热梗名称或核心概念。如果素材内容与任何流行热梗无关，则返回空列表 `[]`。
9. Keywords (关键词): 提取 5-10 个高度相关的检索关键词，包括所有关键名词和核心形容词。

【注意】你的分析必须基于视觉信息，不要进行任何市场营销或文案总结。

你的最终输出必须是一个完整的 JSON 对象，并且严格匹配以下 Python Pydantic 模型的结构。不要在 JSON 之外输出任何解释、注释、markdown 块或代码块。

JSON Schema:
{
    "main_subject": "string",
    "action_or_event": "string",
    "scene_setting": "string",
    "visual_style": "string",
    "color_palette": "string",
    "emotion_dominant": "string",
    "atmosphere_tags": ["string"],
    "viral_meme_tags": ["string"],
    "keywords": ["string"]
}"""
        
        # Build user prompt
        user_parts = []
        
        # Add context if provided
        if context:
            context_text = "**视频信息：**\n"
            if context.get("duration"):
                context_text += f"- 时长：{context['duration']:.1f}秒\n"
            if context.get("resolution"):
                context_text += f"- 分辨率：{context['resolution']}\n"
            if context.get("frame_count"):
                context_text += f"- 帧数量：{context['frame_count']}帧\n"
            
            user_parts.append({"type": "text", "text": context_text})
        
        # Add instruction
        user_parts.append({
            "type": "text",
            "text": "请分析以下短视频抽帧序列（按时间顺序），严格按照上述JSON格式输出结果："
        })
        
        # Add images
        for idx, url in enumerate(image_urls):
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_parts}
        ]
        
        return messages
    
    def _parse_short_video_tagging_response(self, response_data: Dict) -> ShortVideoTaggingResult:
        """
        解析短视频打标的 API 响应
        
        Args:
            response_data: API response data
            
        Returns:
            ShortVideoTaggingResult object
        """
        try:
            # Extract content from response
            if "choices" not in response_data or len(response_data["choices"]) == 0:
                raise ValueError("No choices in response")
            
            content = response_data["choices"][0]["message"]["content"]
            
            # Try to parse as JSON
            try:
                # Find JSON block in markdown code block if present
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    json_str = content[json_start:json_end].strip()
                elif "```" in content:
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    json_str = content[json_start:json_end].strip()
                else:
                    json_str = content
                
                parsed = json.loads(json_str)
                
                return ShortVideoTaggingResult(
                    main_subject=parsed.get("main_subject", ""),
                    action_or_event=parsed.get("action_or_event", ""),
                    scene_setting=parsed.get("scene_setting", ""),
                    visual_style=parsed.get("visual_style", ""),
                    color_palette=parsed.get("color_palette", ""),
                    emotion_dominant=parsed.get("emotion_dominant", ""),
                    atmosphere_tags=parsed.get("atmosphere_tags", []) or [],
                    viral_meme_tags=parsed.get("viral_meme_tags", []) or [],
                    keywords=parsed.get("keywords", []) or []
                )
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error: {e}, content: {content}")
                # If not valid JSON, create a fallback result
                logger.warning("Response is not valid JSON, creating fallback result")
                return ShortVideoTaggingResult(
                    main_subject="解析错误",
                    action_or_event="无法解析响应内容",
                    scene_setting="",
                    visual_style="",
                    color_palette="",
                    emotion_dominant="未知",
                    atmosphere_tags=[],
                    viral_meme_tags=[],
                    keywords=[]
                )
                
        except Exception as e:
            logger.error(f"Error parsing short video tagging response: {str(e)}")
            raise


# Global service instance
doubao_service = DoubaoService()

