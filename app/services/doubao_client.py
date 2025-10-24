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
        """更宽松的提示词：从视觉给出简短描述，尽可能填入对应 JSON 键，仍需返回规范 JSON。"""
        system_prompt = (
            "你仅基于图片视觉内容进行客观描述。必须返回一个 JSON 对象；无法确定时，文本字段用空字符串\"\"，列表字段用 []。"
            "请尽可能把信息归类到指定的 JSON 键（main_subject/subject_state/scene_setting/\n"
            "composition_style/color_lighting/emotion_dominant/atmosphere_tags/viral_meme_tags/keywords）。"
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

            # 第二次：宽松提示词（兜底）
            try:
                response_data3 = await self._call_api(self._build_single_image_tagging_messages_coarse(image_url))
                result3 = self._parse_single_image_tagging_response(response_data3)
                result3 = self._sanitize_single_image_result(result3)
                if not self._is_invalid_single_image_result(result3):
                    logger.info("Single image tagging analysis completed successfully (coarse fallback)")
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
    
    async def analyze_video_with_transcript(
        self,
        frame_urls: List[str],
        transcript: List[dict],
        video_duration: float,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        带字幕的视频分析：画面+语音联合分析，生成整体打标和时间轴片段
        
        Args:
            frame_urls: 帧图片URL列表（按时间顺序）
            transcript: 字幕片段列表，格式为 [{"start_time": 0.0, "end_time": 3.5, "text": "..."}, ...]
            video_duration: 视频总时长（秒）
            context: 视频上下文信息
            
        Returns:
            {
                "overall_tagging": ShortVideoTaggingResult,
                "timeline_segments": List[TimelineSegmentTagging],
                "metadata": dict
            }
        """
        try:
            logger.info(f"Starting video analysis with transcript: {len(frame_urls)} frames, {len(transcript)} segments")
            
            # 分批处理帧（每批10帧）
            batch_size = 10
            batches = []
            
            for i in range(0, len(frame_urls), batch_size):
                batch_frames = frame_urls[i:i + batch_size]
                
                # 计算这批帧的时间范围
                start_idx = i
                end_idx = min(i + batch_size - 1, len(frame_urls) - 1)
                
                # 估算每帧的时间戳
                frame_interval = video_duration / max(len(frame_urls), 1)
                batch_start_time = start_idx * frame_interval
                batch_end_time = end_idx * frame_interval
                
                # 找到这个时间段的字幕
                batch_transcript = []
                for seg in transcript:
                    # 如果字幕片段与当前批次有重叠
                    if seg["start_time"] <= batch_end_time and seg["end_time"] >= batch_start_time:
                        batch_transcript.append(seg)
                
                # 合并字幕文本
                batch_text = " ".join([seg["text"] for seg in batch_transcript])
                
                batches.append({
                    "frames": batch_frames,
                    "start_time": batch_start_time,
                    "end_time": batch_end_time,
                    "transcript": batch_text,
                    "start_idx": start_idx,
                    "end_idx": end_idx
                })
            
            # 分析每个批次
            timeline_segments = []
            
            for idx, batch in enumerate(batches):
                logger.info(f"Analyzing batch {idx + 1}/{len(batches)}: frames {batch['start_idx']}-{batch['end_idx']}")
                
                # 构建带字幕的提示词
                messages = self._build_video_with_transcript_messages(
                    batch["frames"],
                    batch["transcript"],
                    batch["start_time"],
                    batch["end_time"]
                )
                
                # 调用AI
                response_data = await self._call_api(messages)
                
                # 解析结果
                segment_result = self._parse_short_video_tagging_response(response_data)
                
                # 构建时间轴片段
                segment = {
                    "start_time": round(batch["start_time"], 3),
                    "end_time": round(batch["end_time"], 3),
                    "spoken_content": batch["transcript"],
                    "main_subject": segment_result.main_subject or "",
                    "action_or_event": segment_result.action_or_event or "",
                    "scene_setting": segment_result.scene_setting or "",
                    "visual_style": segment_result.visual_style or "",
                    "color_palette": segment_result.color_palette or "",
                    "emotion_dominant": segment_result.emotion_dominant or "",
                    "atmosphere_tags": segment_result.atmosphere_tags or [],
                    "viral_meme_tags": segment_result.viral_meme_tags or [],
                    "keywords": segment_result.keywords or [],
                    "frame_range": f"{batch['start_idx'] + 1}-{batch['end_idx'] + 1}"
                }
                
                timeline_segments.append(segment)
            
            # 生成整体视频打标（基于所有片段的汇总）
            overall_messages = self._build_overall_tagging_from_segments(
                timeline_segments,
                video_duration,
                len(frame_urls)
            )
            
            overall_response = await self._call_api(overall_messages)
            overall_tagging = self._parse_short_video_tagging_response(overall_response)
            
            logger.info(f"Video analysis with transcript completed: {len(timeline_segments)} segments")
            
            return {
                "overall_tagging": overall_tagging,
                "timeline_segments": timeline_segments,
                "metadata": {
                    "video_duration": video_duration,
                    "total_frames": len(frame_urls),
                    "total_segments": len(timeline_segments),
                    "has_transcript": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error in video analysis with transcript: {e}", exc_info=True)
            raise
    
    def _build_video_with_transcript_messages(
        self,
        frame_urls: List[str],
        transcript_text: str,
        start_time: float,
        end_time: float
    ) -> List[Dict]:
        """构建带字幕的视频分析提示词"""
        
        system_content = """你是一位专业的视频内容分析师。你的任务是基于视频画面（一系列帧图片）和对应时间段的语音内容（ASR识别结果），对视频片段进行全面分析。

请综合画面和语音内容，按照以下格式输出JSON结果：

1. Main Subject (核心主体): 简短精准地描述画面和内容的主要焦点
2. Action or Event (动作或事件): 结合画面和语音，描述这段时间发生的核心事件
3. Scene Setting (场景设置): 描述地点、环境、时间等背景信息
4. Visual Style (视觉风格): 描述拍摄技巧和画面质感
5. Color Palette (色彩基调): 描述画面主要色彩
6. Emotion Dominant (主导情感): 只用一个词概括情绪
7. Atmosphere Tags (氛围标签): 3-5个氛围标签
8. Viral Meme Tags (网络热梗标签): 3-5个热梗标签，无相关则返回空列表
9. Keywords (关键词): 5-10个关键词，结合画面和语音内容

你的输出必须是纯JSON格式，不要包含任何解释、注释或markdown块。

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
        
        # 构建用户消息
        user_parts = []
        
        # 添加时间和字幕信息
        time_text = f"**时间段：** {start_time:.1f}秒 - {end_time:.1f}秒\n\n"
        if transcript_text:
            time_text += f"**语音内容：**\n{transcript_text}\n\n"
        else:
            time_text += "**语音内容：** （无语音或静音）\n\n"
        
        time_text += "**画面内容：**\n请分析以下帧序列："
        
        user_parts.append({"type": "text", "text": time_text})
        
        # 添加图片
        for url in frame_urls:
            user_parts.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_parts}
        ]
    
    def _build_overall_tagging_from_segments(
        self,
        segments: List[dict],
        video_duration: float,
        total_frames: int
    ) -> List[Dict]:
        """基于所有片段生成整体视频打标的提示词"""
        
        system_content = """你是一位专业的视频内容分析师。现在需要你基于视频各个时间段的分析结果，生成整体视频的打标。

请综合所有片段的信息，提取出整个视频的核心特征和主题，按照以下格式输出JSON结果：

你的输出必须是纯JSON格式，不要包含任何解释、注释或markdown块。

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
        
        # 构建片段摘要
        segments_summary = f"**视频总时长：** {video_duration:.1f}秒\n"
        segments_summary += f"**总帧数：** {total_frames}\n"
        segments_summary += f"**片段数量：** {len(segments)}\n\n"
        segments_summary += "**各时间段分析结果：**\n\n"
        
        for idx, seg in enumerate(segments):
            segments_summary += f"片段 {idx + 1}: {seg['start_time']:.1f}s - {seg['end_time']:.1f}s\n"
            if seg.get('spoken_content'):
                segments_summary += f"  语音: {seg['spoken_content'][:100]}...\n" if len(seg.get('spoken_content', '')) > 100 else f"  语音: {seg['spoken_content']}\n"
            segments_summary += f"  主体: {seg['main_subject']}\n"
            segments_summary += f"  事件: {seg['action_or_event']}\n"
            segments_summary += f"  关键词: {', '.join(seg['keywords'][:5])}\n\n"
        
        segments_summary += "\n请基于以上所有片段，生成整个视频的整体打标。"
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": segments_summary}
        ]
    
    async def analyze_video_with_visual_segments(
        self,
        frame_urls: List[str],
        video_duration: float,
        context: Optional[Dict] = None
    ) -> Dict:
        """
        纯视觉分段分析：基于画面帧进行分段分析（无字幕）
        
        Args:
            frame_urls: 帧图片URL列表（按时间顺序）
            video_duration: 视频总时长（秒）
            context: 视频上下文信息
            
        Returns:
            {
                "overall_tagging": ShortVideoTaggingResult,
                "timeline_segments": List[TimelineSegmentTagging],
                "metadata": dict
            }
        """
        try:
            logger.info(f"Starting visual-only segmentation analysis: {len(frame_urls)} frames, duration={video_duration}s")
            
            # 分批处理帧（每批10帧）
            batch_size = 10
            batches = []
            
            for i in range(0, len(frame_urls), batch_size):
                batch_frames = frame_urls[i:i + batch_size]
                
                # 计算这批帧的时间范围
                start_idx = i
                end_idx = min(i + batch_size - 1, len(frame_urls) - 1)
                
                # 估算每帧的时间戳
                frame_interval = video_duration / max(len(frame_urls), 1)
                batch_start_time = start_idx * frame_interval
                batch_end_time = end_idx * frame_interval
                
                batches.append({
                    "frames": batch_frames,
                    "start_time": batch_start_time,
                    "end_time": batch_end_time,
                    "start_idx": start_idx,
                    "end_idx": end_idx
                })
            
            # 分析每个批次
            timeline_segments = []
            
            for idx, batch in enumerate(batches):
                logger.info(f"Analyzing visual batch {idx + 1}/{len(batches)}: frames {batch['start_idx']}-{batch['end_idx']}")
                
                # 构建纯视觉分析提示词
                messages = self._build_visual_segment_messages(
                    batch["frames"],
                    batch["start_time"],
                    batch["end_time"]
                )
                
                # 调用AI
                response_data = await self._call_api(messages)
                
                # 解析结果
                segment_result = self._parse_short_video_tagging_response(response_data)
                
                # 构建时间轴片段
                segment = {
                    "start_time": round(batch["start_time"], 3),
                    "end_time": round(batch["end_time"], 3),
                    "spoken_content": None,  # 纯视觉分析无语音内容
                    "main_subject": segment_result.main_subject or "",
                    "action_or_event": segment_result.action_or_event or "",
                    "scene_setting": segment_result.scene_setting or "",
                    "visual_style": segment_result.visual_style or "",
                    "color_palette": segment_result.color_palette or "",
                    "emotion_dominant": segment_result.emotion_dominant or "",
                    "atmosphere_tags": segment_result.atmosphere_tags or [],
                    "viral_meme_tags": segment_result.viral_meme_tags or [],
                    "keywords": segment_result.keywords or [],
                    "frame_range": f"{batch['start_idx'] + 1}-{batch['end_idx'] + 1}"
                }
                
                timeline_segments.append(segment)
            
            # 生成整体视频打标（基于所有片段的汇总）
            overall_messages = self._build_overall_tagging_from_segments(
                timeline_segments,
                video_duration,
                len(frame_urls)
            )
            
            overall_response = await self._call_api(overall_messages)
            overall_tagging = self._parse_short_video_tagging_response(overall_response)
            
            logger.info(f"Visual segmentation analysis completed: {len(timeline_segments)} segments")
            
            return {
                "overall_tagging": overall_tagging,
                "timeline_segments": timeline_segments,
                "metadata": {
                    "video_duration": video_duration,
                    "total_frames": len(frame_urls),
                    "total_segments": len(timeline_segments),
                    "has_transcript": False
                }
            }
            
        except Exception as e:
            logger.error(f"Error in visual segmentation analysis: {e}", exc_info=True)
            raise
    
    def _build_visual_segment_messages(
        self,
        frame_urls: List[str],
        start_time: float,
        end_time: float
    ) -> List[Dict]:
        """构建纯视觉分段分析提示词"""
        
        system_content = """你是一位专业的视频内容分析师。你的任务是基于视频画面（一系列帧图片）对视频片段进行全面分析。

请仔细观察画面，按照以下格式输出JSON结果：

1. Main Subject (核心主体): 简短精准地描述画面的主要焦点
2. Action or Event (动作或事件): 描述这段时间画面中发生的核心事件
3. Scene Setting (场景设置): 描述地点、环境、时间等背景信息
4. Visual Style (视觉风格): 描述拍摄技巧和画面质感
5. Color Palette (色彩基调): 描述画面主要的色彩倾向
6. Emotion Dominant (主导情感): 只用一个词总结画面传达的最强烈的情绪
7. Atmosphere Tags (氛围标签): 3-5个描述画面整体氛围的标签
8. Viral Meme Tags (网络热梗标签): 如果画面包含可识别的网络热梗，列出3-5个；否则留空
9. Keywords (关键词): 5-10个高度相关的检索关键词

输出格式必须是标准JSON格式：
{
  "main_subject": "string",
  "action_or_event": "string",
  "scene_setting": "string",
  "visual_style": "string",
  "color_palette": "string",
  "emotion_dominant": "string",
  "atmosphere_tags": ["tag1", "tag2", "tag3"],
  "viral_meme_tags": ["meme1", "meme2"],
  "keywords": ["keyword1", "keyword2", ...]
}

注意事项：
1. 所有字符串字段不能为null，至少返回空字符串
2. 所有数组字段不能为null，至少返回空数组[]
3. atmosphere_tags至少包含3个标签，最多5个
4. viral_meme_tags如果没有热梗则返回空数组[]
5. keywords至少包含5个，最多10个
6. 确保输出是合法的JSON格式，可以被直接解析"""
        
        # 构建用户消息
        time_text = f"**时间段：** {start_time:.1f}秒 - {end_time:.1f}秒\n\n"
        time_text += "**画面帧序列：**\n"
        time_text += "请分析以下画面帧（按时间顺序），给出这个时间段的完整打标。\n\n"
        
        # 构建包含图片的消息内容
        content = [{"type": "text", "text": time_text}]
        for url in frame_urls:
            content.append({
                "type": "image_url",
                "image_url": {"url": url}
            })
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": content}
        ]


# Global service instance
doubao_service = DoubaoService()

