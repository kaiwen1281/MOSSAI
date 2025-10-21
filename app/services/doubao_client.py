"""Doubao (Volcengine) AI model client for video/image analysis"""
import logging
from typing import List, Optional, Dict
import json

import httpx

from app.core.config import settings
from app.models.schemas import AnalysisResult, ShortVideoTaggingResult, SingleImageTaggingResult

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

    def _build_single_image_tagging_messages(self, image_url: str) -> List[Dict]:
        """构建单张图片打标的消息"""
        system_prompt = """你是一位专业的图片分析师和视觉标签专家。你的任务是基于输入的单张图片，进行细致的、聚焦于画面和情感的分析。你需要严格按照提供的 JSON 格式输出结果。

请对输入的图片进行分析，并生成以下字段的内容：

1. Main Subject (核心主体): 简短精准地描述画面最主要的焦点物体或人物。
2. Subject State (主体状态): 描述核心主体所处的具体动作或状态。
3. Scene Setting (场景设置): 详细描述地点、环境、时间等背景信息。
4. Composition Style (构图与风格): 提取图片的构图方式和拍摄角度特点。
5. Color Lighting (色彩与光线): 描述画面主要的色彩倾向和光线类型（如硬光、柔光）。
6. Emotion Dominant (主导情感): **只使用一个词汇**总结图片传达的最强烈的情绪（如：'平静'）。
7. Atmosphere Tags (氛围标签): 列出 3-5 个用于描述图片整体氛围的标签。
8. **Viral Meme Tags (网络热梗标签):** 分析图片是否紧密关联当前流行的**网络热梗、视觉梗或社交挑战**。列出 3-5 个具体的热梗名称或核心概念。如果图片与任何流行热梗无关，则返回空列表 `[]`。
9. Keywords (关键词): 提取 5-10 个高度相关的检索关键词，包括所有关键名词和核心形容词。

【注意】你的分析必须完全基于视觉信息，不要进行任何超出图片内容的推测或描述。

你的最终输出必须是一个完整的 JSON 对象，并且严格匹配以下 Python Pydantic 模型的结构。不要在 JSON 之外输出任何解释、注释、markdown 块或代码块。

JSON Schema:
{
    "main_subject": "string",
    "subject_state": "string", 
    "scene_setting": "string",
    "composition_style": "string",
    "color_lighting": "string",
    "emotion_dominant": "string",
    "atmosphere_tags": ["string"],
    "viral_meme_tags": ["string"],
    "keywords": ["string"]
}"""

        user_parts = [
            {"type": "text", "text": "请按照上述要求分析这张图片："},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_parts}
        ]

    def _build_single_image_tagging_messages_strict(self, image_url: str) -> List[Dict]:
        """严格提示词：只允许返回纯 JSON，对未知字段用空字符串或空列表。"""
        system_prompt = (
            "你是图片标签生成器。严格、唯一输出一个 JSON 对象，且字段必须完整，"
            "文本字段未知则为空字符串\"\"，列表字段未知则为 []，禁止任何解释或 Markdown。\n\n"
            "JSON Schema:{\n"
            "  \"main_subject\": \"string\",\n"
            "  \"subject_state\": \"string\",\n"
            "  \"scene_setting\": \"string\",\n"
            "  \"composition_style\": \"string\",\n"
            "  \"color_lighting\": \"string\",\n"
            "  \"emotion_dominant\": \"string\",\n"
            "  \"atmosphere_tags\": [\"string\"],\n"
            "  \"viral_meme_tags\": [\"string\"],\n"
            "  \"keywords\": [\"string\"]\n"
            "}"
        )
        user_parts = [
            {"type": "text", "text": "仅输出上述结构的 JSON 对象，不要包含解释："},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_parts}
        ]

    def _build_single_image_tagging_messages_coarse(self, image_url: str) -> List[Dict]:
        """更宽松的提示词：尽量从视觉给出简短描述，仍需返回规范 JSON。"""
        system_prompt = (
            "你只根据图片视觉信息做简短客观描述。必须返回 JSON，字段缺失时文本为\"\"，列表为 []。"
        )
        user_parts = [
            {"type": "text", "text": "用最直观的词汇填充各字段，无法确定时留空字符串或空数组："},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_parts}
        ]

    @staticmethod
    def _sanitize_single_image_result(result: SingleImageTaggingResult) -> SingleImageTaggingResult:
        """统一将 None→空字符串/空数组，并清理失败占位词。"""
        def s(v: Optional[str]) -> str:
            if v is None:
                return ""
            bad = {"分析失败", "解析错误", "系统错误", "未知"}
            return "" if v.strip() in bad else v
        def l(v):
            if isinstance(v, list):
                return v
            return []
        return SingleImageTaggingResult(
            main_subject=s(getattr(result, "main_subject", "")),
            subject_state=s(getattr(result, "subject_state", "")),
            scene_setting=s(getattr(result, "scene_setting", "")),
            composition_style=s(getattr(result, "composition_style", "")),
            color_lighting=s(getattr(result, "color_lighting", "")),
            emotion_dominant=s(getattr(result, "emotion_dominant", "")),
            atmosphere_tags=l(getattr(result, "atmosphere_tags", [])),
            viral_meme_tags=l(getattr(result, "viral_meme_tags", [])),
            keywords=l(getattr(result, "keywords", [])),
        )

    @staticmethod
    def _is_invalid_single_image_result(result: SingleImageTaggingResult) -> bool:
        """判定首响应是否不可用。"""
        bad_texts = {"分析失败", "解析错误", "系统错误"}
        texts = [
            result.main_subject.strip() if result.main_subject else "",
            result.subject_state.strip() if result.subject_state else "",
            result.emotion_dominant.strip() if result.emotion_dominant else "",
        ]
        # 典型失败占位词或几乎完全为空
        if any(t in bad_texts for t in texts):
            return True
        if all(t == "" for t in [
            result.main_subject, result.subject_state, result.scene_setting,
            result.composition_style, result.color_lighting, result.emotion_dominant
        ]):
            return True
        return False

    def _parse_single_image_tagging_response(self, response_data: dict) -> SingleImageTaggingResult:
        """解析单张图片打标的AI响应"""
        try:
            content = response_data["choices"][0]["message"]["content"]
            logger.info(f"Raw AI response: {content[:200]}...")
            
            # 提取JSON内容
            json_str = content
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
            
            return SingleImageTaggingResult(
                main_subject=parsed.get("main_subject", ""),
                subject_state=parsed.get("subject_state", ""),
                scene_setting=parsed.get("scene_setting", ""),
                composition_style=parsed.get("composition_style", ""),
                color_lighting=parsed.get("color_lighting", ""),
                emotion_dominant=parsed.get("emotion_dominant", ""),
                atmosphere_tags=parsed.get("atmosphere_tags", []) or [],
                viral_meme_tags=parsed.get("viral_meme_tags", []) or [],
                keywords=parsed.get("keywords", []) or []
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}, content: {content}")
            logger.warning("Response is not valid JSON, creating fallback result")
            return SingleImageTaggingResult(
                main_subject="解析错误",
                subject_state="无法解析响应内容",
                scene_setting="",
                composition_style="",
                color_lighting="",
                emotion_dominant="未知",
                atmosphere_tags=[],
                viral_meme_tags=[],
                keywords=[]
            )
        except Exception as e:
            logger.error(f"Error parsing single image tagging response: {str(e)}")
            raise

    async def analyze_single_image_tagging(
        self,
        image_url: str
    ) -> SingleImageTaggingResult:
        """
        专门用于单张图片打标的分析
        
        Args:
            image_url: 图片URL
            
        Returns:
            SingleImageTaggingResult: 图片打标结果
        """
        try:
            logger.info(f"Starting single image tagging analysis for: {image_url}")
            # 第一次：常规提示词
            try:
                response_data = await self._call_api(self._build_single_image_tagging_messages(image_url))
                result = self._parse_single_image_tagging_response(response_data)
                result = self._sanitize_single_image_result(result)
                if not self._is_invalid_single_image_result(result):
                    logger.info("Single image tagging analysis completed successfully (primary)")
                    return result
                logger.warning("Primary image tagging result invalid, trying strict prompt...")
            except Exception as e:
                logger.warning(f"Primary attempt failed: {e}")

            # 第二次：严格提示词
            try:
                response_data2 = await self._call_api(self._build_single_image_tagging_messages_strict(image_url))
                result2 = self._parse_single_image_tagging_response(response_data2)
                result2 = self._sanitize_single_image_result(result2)
                if not self._is_invalid_single_image_result(result2):
                    logger.info("Single image tagging analysis completed successfully (strict)")
                    return result2
                logger.warning("Strict image tagging result invalid, trying coarse prompt...")
            except Exception as e2:
                logger.warning(f"Strict attempt failed: {e2}")

            # 第三次：宽松提示词（兜底）
            try:
                response_data3 = await self._call_api(self._build_single_image_tagging_messages_coarse(image_url))
                result3 = self._parse_single_image_tagging_response(response_data3)
                result3 = self._sanitize_single_image_result(result3)
                if not self._is_invalid_single_image_result(result3):
                    logger.info("Single image tagging analysis completed successfully (coarse)")
                    return result3
            except Exception as e3:
                logger.warning(f"Coarse attempt failed: {e3}")

            # 最终兜底：最小可写库结果（空字符串与空数组）
            logger.error("All attempts failed or invalid. Returning minimal valid result.")
            return self._sanitize_single_image_result(
                SingleImageTaggingResult(
                    main_subject="",
                    subject_state="",
                    scene_setting="",
                    composition_style="",
                    color_lighting="",
                    emotion_dominant="",
                    atmosphere_tags=[],
                    viral_meme_tags=[],
                    keywords=[]
                )
            )
        except Exception as e:
            logger.error(f"Error in single image tagging analysis (unexpected): {str(e)}")
            # 兜底：最小可写库结果
            return self._sanitize_single_image_result(
                SingleImageTaggingResult(
                    main_subject="",
                    subject_state="",
                    scene_setting="",
                    composition_style="",
                    color_lighting="",
                    emotion_dominant="",
                    atmosphere_tags=[],
                    viral_meme_tags=[],
                    keywords=[]
                )
            )


# Global service instance
doubao_service = DoubaoService()

