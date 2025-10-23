# MOSS-AI

视频抽帧与AI内容分析服务

## 项目简介

MOSS-AI 是一个基于 FastAPI 的无状态微服务，专注于视频和图片内容的智能处理与分析。主要功能包括：

- 🎬 **视频抽帧**：
  - 低/中/高：基于阿里云OSS实时处理的高效抽帧
  - 智能（SMART）：基于阿里云ICE SubmitSnapshotJob + 模板ID，支持动态覆盖帧数
- 🖼️ **图片分析**：直接通过媒资ID或URL进行AI内容理解
- 🤖 **AI分析**：使用豆包大模型进行智能内容理解
- 📦 **多格式支持**：支持视频、图片 两种格式
- 🎯 **灵活抽帧**：提供低/中/高/智能（SMART）四种抽帧等级
- ☁️ **云存储**：自动管理OSS存储和URL签名
- 🚀 **极速响应**：OSS实时抽帧，无需等待异步任务

## 核心特性

### 1. 统一媒资处理

**图片和视频都支持通过媒资ID进行分析**，MOSS端只需传递ICE媒资ID即可：

- **视频分析**：自动抽帧 + AI分析，一键完成
- **图片分析**：直接进行AI内容理解
- **统一接口**：`/api/analyze-media` 处理所有媒体类型

### 2. 多级抽帧策略

- **低等级（Low）**：每10秒抽一帧，适合长视频快速预览
- **中等级（Medium）**：每3秒抽一帧（推荐），平衡精度与成本
- **高等级（High）**：每秒抽一帧，适合细节要求高的场景

### 3. 智能分段分析

当视频帧数超过模型限制时，自动进行分段分析并合并结果：

- 自动将视频分成多个片段
- 每个片段独立分析
- 智能合并生成完整报告

### 4. 完整的业务流程

**视频分析流程：**
```
用户请求 → 获取媒资信息 → OSS实时抽帧（生成URL） → 生成索引文件 
         → 豆包AI分析 → 返回结构化结果
```

**图片分析流程：**
```
用户请求 → 获取图片URL（从ICE或直接提供） → 豆包AI分析 → 返回结果
```

## 技术栈

- **框架**: FastAPI + Uvicorn
- **包管理**: UV
- **云服务**: 
  - 阿里云ICE（视频处理）
  - 阿里云OSS（对象存储）
  - 豆包大模型（AI分析）
- **依赖库**:
  - `pydantic-settings`: 配置管理
  - `httpx`: 异步HTTP客户端
  - `pillow`: 图片处理
  - `oss2`: OSS SDK
  - `alibabacloud-ice`: ICE SDK

## 快速开始

### 1. 环境要求

- Python 3.10+
- UV 包管理器
- FFmpeg（用于GIF转换，可选）

### 2. 安装依赖

```bash
# 使用 UV 安装依赖
uv sync
```

### 3. 配置环境变量

复制 `.env.template` 创建 `.env` 文件：

```bash
# 注意：.env 文件会被 .gitignore 忽略
# 请手动创建该文件并配置以下变量
```

必需/可选的环境变量：

```env
# 阿里云访问凭证
ALIYUN_ACCESS_KEY_ID=your_access_key_id
ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret

# 阿里云ICE配置（SMART 模式）
ALIYUN_ICE_REGION=cn-shanghai
ALIYUN_ICE_ENDPOINT=ice.cn-shanghai.aliyuncs.com
ICE_SNAPSHOT_TEMPLATE_ID=your_snapshot_template_id

# 阿里云OSS配置（低/中/高）
ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com
ALIYUN_OSS_BUCKET=your-bucket-name

# 豆包大模型配置
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_MODEL=doubao-vision
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# 服务配置
MOSSAI_HOST=0.0.0.0
MOSSAI_PORT=8001

# 智能模式默认帧数（可选，默认50）
DEFAULT_INTELLIGENT_FRAME_COUNT=50
```

完整配置说明请参考项目中的 `.env.template` 文件。

### 4. 启动服务

```bash

#启动
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 访问文档

服务启动后，访问以下地址查看API文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 接口

### 1. 健康检查

```http
GET /health
```

### 2. 提交抽帧任务

```http
POST /api/extract-frames
Content-Type: application/json

{
  "media_id": "abc123def456",
  "moss_id": "video_001",
  "brand_name": "example_brand",
  "frame_level": "medium",
  "smart_frame_count": 100
}
```

**响应**：
```json
{
  "task_id": "extraction_task_123",
  "status": "pending",
  "message": "Frame extraction task submitted successfully",
  "created_at": "2024-01-01T10:00:00"
}
```

### 3. 分析视频帧

```http
POST /api/analyze-frames
Content-Type: application/json

{
  "frame_urls": [
    "https://example.oss.com/frames/frame_0001.jpg",
    "https://example.oss.com/frames/frame_0002.jpg"
  ],
  "video_duration": 135.5,
  "video_resolution": "1920x1080",
  "custom_prompt": "请重点分析视频中的产品展示"
}
```

### 4. 提交视频分析（SMART 智能模式：ICE）

```http
POST /api/analyze-video
Content-Type: application/json

{
  "moss_id": "ed648c17-cb50-4a3d-a65f-23a5ac1ea20b",
  "brand_name": "JD003",
  "media_id": "932b8070af0e71f0a983f6e7c7496302",
  "frame_level": "smart",
  "smart_frame_count": 100
}
```

说明：
- 必填参数：`moss_id`, `brand_name`, `media_id`, `frame_level`
- 当 `frame_level=smart` 时，`smart_frame_count` 生效（1-200，未传默认50）；模板中的其它参数（关键帧等）不变
- 严格不回退：若ICE任务失败或参数非法，将返回错误，不会切换到OSS抽帧

成功响应（异步任务提交）：
```json
{
  "task_id": "task_xxx",
  "status": "pending",
  "message": "任务已提交"
}
```

查询任务：`GET /api/task/{task_id}`，当 `status=completed` 时的 `result` 字段包含短视频打标结果。

### 5. 统一媒体分析（推荐）

**一个接口处理图片和视频，支持media_id和media_url两种方式**

#### 分析视频（通过media_id）

```http
POST /api/analyze-media
Content-Type: application/json

{
  "media_id": "b510ac10aa3671f0bc97e6e7c7586302",
  "media_type": "video",
  "moss_id": "c6ffb0a0-1bfe-46dc-9406-0d0faacad0b4",
  "brand_name": "京东业务一",
  "frame_level": "smart",
  "smart_frame_count": 50,
  "custom_prompt": "请重点分析产品特点"
}
```

#### 分析图片（通过media_id）

```http
POST /api/analyze-media
Content-Type: application/json

{
  "media_id": "img_abc123def456",
  "media_type": "image",
  "custom_prompt": "请分析图片内容"
}
```

#### 分析图片（通过URL）

```http
POST /api/analyze-media
Content-Type: application/json

{
  "media_url": "https://your-oss.aliyuncs.com/image.jpg",
  "media_type": "image",
  "custom_prompt": "请描述这张图片"
}
```

**支持的媒体类型：**
- `video`: 自动抽帧后分析（需要moss_id和brand_name）
- `image`: 直接分析图片（支持media_id或media_url）
- `gif`: 转换为MP4后抽帧分析（待完善）

### 5. 查询任务状态

```http
GET /api/task/{task_id}
```

**响应**：
```json
{
  "task_id": "task_123",
  "status": "completed",
  "message": "Task completed successfully",
  "progress": 100,
  "result": {
    "analysis_result": {
      "summary": "视频摘要",
      "detailed_content": "详细内容描述",
      "tags": ["标签1", "标签2"]
    }
  },
  "created_at": "2024-01-01T10:00:00",
  "updated_at": "2024-01-01T10:05:00",
  "completed_at": "2024-01-01T10:05:00"
}
```

## 项目结构

```
MOSS-AI/
├── app/
│   ├── api/                 # API路由
│   │   └── routes.py        # 路由处理器
│   ├── core/                # 核心配置
│   │   └── config.py        # 配置管理
│   ├── models/              # 数据模型
│   │   └── schemas.py       # Pydantic模型
│   ├── services/            # 服务层
│   │   ├── ice_client.py    # ICE客户端
│   │   ├── oss_client.py    # OSS客户端
│   │   └── doubao_client.py # 豆包客户端
│   ├── utils/               # 工具函数
│   │   └── media_converter.py # 媒体转换
│   └── main.py              # FastAPI应用
├── main.py                  # 入口文件
├── pyproject.toml           # UV配置
├── .env.template            # 环境变量模板
└── README.md                # 项目文档
```

## 工作流程详解

### 视频抽帧流程

1. **接收请求**：MOSS通过API提交抽帧任务（包含media_id、抽帧等级等）
2. **提交ICE任务**：调用阿里云ICE提交抽帧作业
3. **异步轮询**：后台任务轮询ICE任务状态
4. **帧存储**：抽帧完成后，帧图片自动存储到OSS
5. **生成索引**：创建index.json记录所有帧信息
6. **返回结果**：返回帧URL列表和索引文件地址

### OSS存储结构

```
{brand_name}/
  └── {YYYY-MM}/
      └── video_frames/
          └── {moss_id}/
              ├── frame_0001.jpg
              ├── frame_0002.jpg
              ├── ...
              └── index.json
```

### AI分析流程

1. **接收帧列表**：获取按时间排序的帧URL列表
2. **检查帧数**：判断是否超过模型限制
3. **分段处理**（如需要）：
   - 将帧列表分成多个段
   - 每段独立分析
   - 合并分析结果
4. **调用AI**：发送到豆包大模型
5. **解析结果**：提取摘要、详细内容、标签等
6. **返回报告**：返回结构化分析结果

## 豆包模型配置

当前使用的模型：`ep-20250325124811-g4hv5`（豆包视觉理解模型）

**重要配置说明：**

| 配置项 | 值 | 说明 |
|--------|-----|------|
| DOUBAO_MODEL | ep-20250325124811-g4hv5 | 豆包端点ID |
| DOUBAO_MAX_IMAGES | 30 | 单次最大图片数 |
| DOUBAO_MAX_TOKENS | 8192 | **最大tokens（不要超过12288）** |
| DOUBAO_ENDPOINT | https://ark.cn-beijing.volces.com/api/v3 | API端点 |

在 `.env` 中配置：

```env
DOUBAO_MODEL=ep-20250325124811-g4hv5
DOUBAO_MAX_IMAGES=30
DOUBAO_MAX_TOKENS=8192
DOUBAO_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
```

⚠️ **注意**：`max_tokens`最大值为12288，建议设置为8192以确保稳定性。

## 注意事项

### 1. 无状态设计

MOSS-AI 是无状态服务，不操作数据库。所有必要信息通过API参数传入。

### 2. 任务存储

当前版本使用内存存储任务状态（`tasks_storage`）。生产环境建议使用：
- Redis（推荐）
- 数据库
- 分布式缓存

### 3. 媒资ID

视频必须预先在阿里云ICE注册，获得media_id后才能进行抽帧。

### 4. URL有效期（与严格不回退）

OSS签名URL默认有效期为24小时，确保在有效期内完成分析。SMART模式使用ICE返回的URL，避免二次签名；若ICE失败则直接报错，不回退到OSS。

```

## 开发指南

### 添加新功能

1. 在 `app/models/schemas.py` 定义数据模型
2. 在 `app/services/` 实现服务逻辑
3. 在 `app/api/routes.py` 添加路由
4. 更新文档

### 日志配置

日志级别由 `DEBUG` 环境变量控制：

```env
DEBUG=true   # 开启调试日志
DEBUG=false  # 仅INFO级别
```

### 测试

```bash
# 运行测试（如有）
uv run pytest

# 代码检查
uv run ruff check .
uv run mypy .
```

## 性能优化

1. **并发处理**：使用异步IO提高吞吐量
2. **分段分析**：自动处理超长视频
3. **缓存策略**：OSS URL缓存、结果缓存
4. **智能抽帧**：减少不必要的帧数

## 故障排查

### 1. ICE任务失败

- 检查media_id是否有效
- 确认视频格式是否支持
- 查看ICE控制台任务详情

### 2. OSS访问失败

- 验证AccessKey权限
- 检查Bucket和Endpoint配置
- 确认网络连接

### 3. 豆包API错误

- 检查API Key是否有效
- 确认模型名称正确
- 查看是否超过配额限制

## 与MOSS集成

### 推荐方式：使用统一接口

MOSS端统一使用`/api/analyze-media`接口，通过`media_type`区分图片和视频：

```python
import httpx
import asyncio
from typing import Dict, Optional

class MOSSAIClient:
    """MOSS-AI 客户端（推荐集成方式）"""
    
    def __init__(self, base_url: str = "http://moss-ai:8001"):
        self.base_url = base_url
    
    async def analyze_media(
        self,
        media_id: str,
        media_type: str,  # "video" 或 "image"
        moss_id: Optional[str] = None,
        brand_name: Optional[str] = None,
        frame_level: str = "medium",
        custom_prompt: Optional[str] = None
    ) -> Dict:
        """
        统一分析接口（图片和视频都支持media_id）
        
        Args:
            media_id: ICE媒资ID（图片和视频通用）
            media_type: 媒体类型 "video" 或 "image"
            moss_id: MOSS ID（视频必填）
            brand_name: 品牌方名称（视频必填）
            frame_level: 抽帧等级（仅视频：low/medium/high）
            custom_prompt: 自定义分析提示词
            
        Returns:
            分析结果字典
        """
        async with httpx.AsyncClient(timeout=300.0) as client:
            # 构建请求
            payload = {
                "media_id": media_id,
                "media_type": media_type,
                "custom_prompt": custom_prompt
            }
            
            # 视频需要额外参数
            if media_type == "video":
                if not moss_id or not brand_name:
                    raise ValueError("moss_id and brand_name are required for video")
                payload.update({
                    "moss_id": moss_id,
                    "brand_name": brand_name,
                    "frame_level": frame_level
                })
            
            # 1. 提交任务
            response = await client.post(
                f"{self.base_url}/api/analyze-media",
                json=payload
            )
            response.raise_for_status()
            task_id = response.json()["task_id"]
            
            # 2. 轮询状态
            max_attempts = 120  # 最多等待10分钟
            for _ in range(max_attempts):
                await asyncio.sleep(5)
                
                status_response = await client.get(
                    f"{self.base_url}/api/task/{task_id}"
                )
                status_data = status_response.json()
                
                if status_data["status"] == "completed":
                    return status_data["result"]
                elif status_data["status"] == "failed":
                    raise Exception(f"Analysis failed: {status_data['message']}")
            
            raise TimeoutError("Analysis timeout")

# 使用示例
async def main():
    client = MOSSAIClient("http://localhost:8001")
    
    # 分析视频（通过media_id）
    video_result = await client.analyze_media(
        media_id="b510ac10aa3671f0bc97e6e7c7586302",
        media_type="video",
        moss_id="c6ffb0a0-1bfe-46dc-9406-0d0faacad0b4",
        brand_name="京东业务一",
        frame_level="medium"
    )
    print(f"视频摘要: {video_result['analysis_result']['summary']}")
    
    # 分析图片（通过media_id）
    image_result = await client.analyze_media(
        media_id="img_abc123",
        media_type="image",
        custom_prompt="请分析图片内容"
    )
    print(f"图片摘要: {image_result['analysis_result']['summary']}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 性能指标

| 操作 | 耗时 | 说明 |
|------|------|------|
| 视频抽帧（22秒视频） | 1-2秒 | OSS实时处理 |
| 单张图片分析 | 2-5秒 | 取决于图片大小 |
| 8帧视频分析 | 5-10秒 | 豆包AI处理 |
| 完整视频分析流程 | 10-15秒 | 抽帧 + 分析 |

## 许可证

[添加许可证信息]

## 联系方式

[添加联系方式]

## 更新日志

### v0.3.0 (2025-10-22)

✅ 智能模式（SMART）上线（视频抽帧基于阿里云ICE模板截图）
- 使用 SubmitSnapshotJob + 模板ID，支持请求时动态覆盖 Count（1-200，默认50）
- 轮询 GetSnapshotJob（10/20/30/40/50s）直至 Success，再分页 GetSnapshotUrls（安全 PageSize≤20）
- 严格不回退到OSS：ICE失败即报错，不做降级
- 修复：避免对ICE已签名URL进行二次签名导致的下载错误
- 新增环境变量：ICE_SNAPSHOT_TEMPLATE_ID、DEFAULT_INTELLIGENT_FRAME_COUNT、MOSSAI_HOST、MOSSAI_PORT

### v0.2.0 (2025-10-17)

✅ **重大更新**
- 🚀 切换到OSS实时抽帧，极速响应（1-2秒完成抽帧）
- 🖼️ 完善图片分析功能，支持通过media_id直接分析
- 🔧 修复豆包API max_tokens配置问题
- 📦 统一媒资处理接口（图片和视频都支持media_id）
- ✨ 完整的MOSS集成示例代码
- 📝 更新完整的API文档和使用指南

**技术改进**
- 移除ICE SubmitSnapshotJob依赖（不再需要模板ID）
- 使用OSS video/snapshot实时处理
- 优化帧URL生成逻辑（预览模式，非下载模式）
- 改进错误处理和日志记录

**测试验证**
- ✅ 22秒视频抽取8帧测试通过
- ✅ 豆包AI分析8帧测试通过
- ✅ 完整流程（抽帧+分析）测试通过

### v0.1.0 (2025-10-16)

- 初始版本发布
- 支持视频抽帧（低/中/高）
- 支持豆包AI分析
- 支持图片、视频、GIF三种格式
- 完整的API文档


