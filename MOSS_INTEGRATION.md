# MOSS 集成文档 - MOSSAI 视频分析服务

## 📋 概述

本文档说明 MOSS 端如何集成 MOSSAI 视频分析服务，实现视频内容的自动化 AI 分析。

### 服务地址
- **开发环境**: `http://localhost:8001`
- **生产环境**: `http://your-domain:8001`

### API 文档
- **Swagger UI**: `http://localhost:8001/docs`
- **ReDoc**: `http://localhost:8001/redoc`

---

## 🎯 核心功能

MOSSAI 提供以下核心功能：
1. ✅ 视频抽帧（使用阿里云 OSS 实时处理）
2. ✅ AI 内容分析（使用豆包大模型）
3. ✅ 异步任务处理（立即返回，后台处理）
4. ✅ 任务状态追踪
5. ✅ 并发控制（抽帧5并发，分析3并发）
6. ✅ 自动内存管理

---

## 🔑 核心 API 接口

### 1. 提交视频分析任务

**接口地址：** `POST /api/analyze-video`

**请求参数：**

```json
{
  "moss_id": "video_20231017_001",      // 必需：MOSS系统视频ID
  "brand_name": "nike",                  // 必需：品牌方名称
  "media_id": "****0343c45e0ce64664a",  // 必需：阿里云ICE媒资ID
  "frame_level": "medium"                // 必需：抽帧等级 (low/medium/high)
}
```

**参数说明：**

| 参数 | 类型 | 必需 | 说明 | 可选值 |
|------|------|------|------|--------|
| `moss_id` | string | ✅ | MOSS系统中的视频唯一标识 | - |
| `brand_name` | string | ✅ | 品牌方名称（用于OSS存储路径） | - |
| `media_id` | string | ✅ | 阿里云ICE媒资ID | - |
| `frame_level` | string | ✅ | 抽帧等级 | `low`, `medium`, `high` |

**抽帧等级说明：**

| 等级 | 说明 | 预计帧数 | 适用场景 |
|------|------|----------|----------|
| `low` | 低密度抽帧，间隔约15秒 | ~5-10帧 | 快速预览 |
| `medium` | 中等密度，间隔约8秒 | ~10-20帧 | 标准分析（推荐） |
| `high` | 高密度抽帧，间隔约3秒 | ~20-50帧 | 详细分析 |

**响应示例：**

```json
{
  "task_id": "video_analysis_1729152000_a1b2c3d4",
  "status": "pending",
  "message": "任务已提交，请使用 task_id 查询处理状态",
  "created_at": "2025-10-17T10:30:00Z"
}
```

**HTTP 状态码：**
- `202 Accepted`: 任务提交成功
- `400 Bad Request`: 参数错误
- `500 Internal Server Error`: 服务器错误

---

### 2. 查询任务状态

**接口地址：** `GET /api/task/{task_id}`

**路径参数：**
- `task_id`: 提交任务时返回的任务ID

**响应示例（处理中）：**

```json
{
  "task_id": "video_analysis_1729152000_a1b2c3d4",
  "moss_id": "video_20231017_001",
  "brand_name": "nike",
  "media_id": "****0343c45e0ce64664a",
  "frame_level": "medium",
  "status": "processing",
  "message": "正在抽帧（等级：medium）...",
  "progress": 30,
  "result": null,
  "error_detail": null,
  "created_at": "2025-10-17T10:30:00Z",
  "updated_at": "2025-10-17T10:30:15Z",
  "completed_at": null
}
```

**响应示例（完成）：**

```json
{
  "task_id": "video_analysis_1729152000_a1b2c3d4",
  "moss_id": "video_20231017_001",
  "brand_name": "nike",
  "media_id": "****0343c45e0ce64664a",
  "frame_level": "medium",
  "status": "completed",
  "message": "视频分析完成",
  "progress": 100,
  "result": {
    "moss_id": "video_20231017_001",
    "brand_name": "nike",
    "media_id": "****0343c45e0ce64664a",
    "frame_level": "medium",
    "analysis": {
      "summary": "这是一个美食制作视频，展示了烹饪全过程...",
      "detailed_content": "视频开始展示了食材准备，包括新鲜蔬菜和肉类。接下来是烹饪过程，厨师娴熟地处理食材...",
      "tags": ["美食", "烹饪", "教程", "中餐"],
      "segments": [
        {
          "timestamp": 0.0,
          "description": "准备食材"
        },
        {
          "timestamp": 30.5,
          "description": "开始烹饪"
        },
        {
          "timestamp": 90.0,
          "description": "装盘展示"
        }
      ]
    },
    "metadata": {
      "frame_count": 15,
      "video_duration": 120.5,
      "video_resolution": "1920x1080",
      "model_used": "doubao-vision-pro"
    }
  },
  "error_detail": null,
  "created_at": "2025-10-17T10:30:00Z",
  "updated_at": "2025-10-17T10:31:30Z",
  "completed_at": "2025-10-17T10:31:30Z"
}
```

**响应示例（失败）：**

```json
{
  "task_id": "video_analysis_1729152000_a1b2c3d4",
  "moss_id": "video_20231017_001",
  "brand_name": "nike",
  "media_id": "****0343c45e0ce64664a",
  "frame_level": "medium",
  "status": "failed",
  "message": "任务失败: 无法获取媒资信息",
  "progress": 10,
  "result": null,
  "error_detail": {
    "error_type": "ValueError",
    "error_message": "媒资ID不存在或已删除"
  },
  "created_at": "2025-10-17T10:30:00Z",
  "updated_at": "2025-10-17T10:30:05Z",
  "completed_at": null
}
```

**任务状态说明：**

| 状态 | 说明 | 下一步操作 |
|------|------|-----------|
| `pending` | 已提交，等待处理 | 继续轮询 |
| `processing` | 正在处理中 | 继续轮询 |
| `completed` | 处理完成 | 获取结果，保存数据，删除任务 |
| `failed` | 处理失败 | 检查错误，决定是否重试 |
| `retry` | 重试中 | 继续轮询 |

**HTTP 状态码：**
- `200 OK`: 查询成功
- `404 Not Found`: 任务不存在
- `500 Internal Server Error`: 服务器错误

---

### 3. 批量查询任务状态

**接口地址：** `POST /api/tasks/batch-status`

**请求参数：**

```json
{
  "task_ids": [
    "video_analysis_1729152000_a1b2c3d4",
    "video_analysis_1729152030_b2c3d4e5",
    "video_analysis_1729152060_c3d4e5f6"
  ]
}
```

**响应示例：**

```json
{
  "results": {
    "video_analysis_1729152000_a1b2c3d4": {
      "task_id": "video_analysis_1729152000_a1b2c3d4",
      "status": "completed",
      "message": "分析完成",
      "progress": 100,
      ...
    },
    "video_analysis_1729152030_b2c3d4e5": {
      "task_id": "video_analysis_1729152030_b2c3d4e5",
      "status": "processing",
      "message": "正在分析...",
      "progress": 60,
      ...
    },
    "video_analysis_1729152060_c3d4e5f6": null
  },
  "total": 3,
  "found": 2,
  "not_found": ["video_analysis_1729152060_c3d4e5f6"]
}
```

---

### 4. 删除任务

**接口地址：** `DELETE /api/task/{task_id}`

**说明：**
MOSS 获取分析结果并保存到数据库后，应该调用此接口删除 MOSSAI 端的任务记录，释放内存。

**响应：**
- `204 No Content`: 删除成功
- `404 Not Found`: 任务不存在

---

## 📝 完整工作流程

### 流程图

```
MOSS 端                                    MOSSAI 端
   │                                          │
   ├─ 1. 提交分析任务 ──────────────────────►│ 创建任务
   │   POST /api/analyze-video               │ 返回 task_id
   │   {moss_id, brand_name, media_id, ...}  │ status: pending
   │                                          │
   │◄─────────────────────────────────────────┤
   │   {task_id, status: pending}            │
   │                                          │
   ├─ 2. 开始轮询（每30秒）                   │
   │   GET /api/task/{task_id}               │
   │                                          │
   │◄─────────────────────────────────────────┤ 后台处理中
   │   {status: processing, progress: 30}    │ 获取媒资信息
   │                                          │ 抽帧（5并发）
   ├─ 3. 继续轮询                             │ AI分析（3并发）
   │   GET /api/task/{task_id}               │
   │                                          │
   │◄─────────────────────────────────────────┤
   │   {status: processing, progress: 60}    │
   │                                          │
   ├─ 4. 继续轮询                             │
   │   GET /api/task/{task_id}               │
   │                                          │
   │◄─────────────────────────────────────────┤ 处理完成
   │   {status: completed, result: {...}}    │
   │                                          │
   ├─ 5. 保存结果到数据库                     │
   │   - tasks 表                             │
   │   - analysis_results 表                  │
   │                                          │
   ├─ 6. 删除远程任务 ───────────────────────►│ 释放内存
   │   DELETE /api/task/{task_id}            │
   │                                          │
   └─ 完成                                    └─
```

---

## 💻 代码实现示例

### Python 实现（推荐）

```python
import httpx
import asyncio
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

class MOSSAIClient:
    """MOSSAI 客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def submit_video_analysis(
        self,
        moss_id: str,
        brand_name: str,
        media_id: str,
        frame_level: str = "medium"
    ) -> Dict:
        """
        提交视频分析任务
        
        Args:
            moss_id: MOSS视频ID
            brand_name: 品牌名称
            media_id: ICE媒资ID
            frame_level: 抽帧等级 (low/medium/high)
            
        Returns:
            任务信息 {task_id, status, message, created_at}
        """
        url = f"{self.base_url}/api/analyze-video"
        payload = {
            "moss_id": moss_id,
            "brand_name": brand_name,
            "media_id": media_id,
            "frame_level": frame_level
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Failed to submit analysis: {e}")
            raise
    
    async def get_task_status(self, task_id: str) -> Dict:
        """
        查询任务状态
        
        Args:
            task_id: 任务ID
            
        Returns:
            任务状态信息
        """
        url = f"{self.base_url}/api/task/{task_id}"
        
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Task {task_id} not found")
                return None
            raise
    
    async def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否删除成功
        """
        url = f"{self.base_url}/api/task/{task_id}"
        
        try:
            response = await self.client.delete(url)
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return False
    
    async def poll_until_complete(
        self,
        task_id: str,
        interval: int = 30,
        max_attempts: int = 120
    ) -> Optional[Dict]:
        """
        轮询直到任务完成
        
        Args:
            task_id: 任务ID
            interval: 轮询间隔（秒）
            max_attempts: 最大尝试次数
            
        Returns:
            完成的任务信息（包含result），失败返回None
        """
        for attempt in range(max_attempts):
            task = await self.get_task_status(task_id)
            
            if not task:
                logger.error(f"Task {task_id} not found")
                return None
            
            status = task["status"]
            progress = task.get("progress", 0)
            message = task.get("message", "")
            
            logger.info(
                f"Task {task_id}: {status} - {progress}% - {message}"
            )
            
            if status == "completed":
                logger.info(f"Task {task_id} completed successfully")
                return task
            
            elif status == "failed":
                error_detail = task.get("error_detail", {})
                logger.error(
                    f"Task {task_id} failed: {error_detail}"
                )
                return None
            
            # 继续轮询
            await asyncio.sleep(interval)
        
        logger.error(f"Task {task_id} timeout after {max_attempts} attempts")
        return None
    
    async def analyze_video_complete(
        self,
        moss_id: str,
        brand_name: str,
        media_id: str,
        frame_level: str = "medium"
    ) -> Optional[Dict]:
        """
        完整的视频分析流程（提交 → 轮询 → 获取结果 → 删除任务）
        
        Returns:
            分析结果，失败返回None
        """
        try:
            # 1. 提交任务
            logger.info(f"Submitting analysis for video {moss_id}")
            task_info = await self.submit_video_analysis(
                moss_id=moss_id,
                brand_name=brand_name,
                media_id=media_id,
                frame_level=frame_level
            )
            task_id = task_info["task_id"]
            logger.info(f"Task submitted: {task_id}")
            
            # 2. 轮询直到完成
            task = await self.poll_until_complete(task_id, interval=30)
            
            if not task:
                return None
            
            # 3. 提取结果
            result = task.get("result")
            
            # 4. 删除任务
            await self.delete_task(task_id)
            logger.info(f"Task {task_id} deleted from MOSSAI")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in video analysis: {e}")
            return None
    
    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


# ============================================================================
# 使用示例
# ============================================================================

async def main():
    """使用示例"""
    client = MOSSAIClient(base_url="http://localhost:8001")
    
    try:
        # 分析视频
        result = await client.analyze_video_complete(
            moss_id="video_20231017_001",
            brand_name="nike",
            media_id="****0343c45e0ce64664a",
            frame_level="medium"
        )
        
        if result:
            # 保存到数据库
            analysis = result["analysis"]
            print(f"摘要: {analysis['summary']}")
            print(f"标签: {analysis['tags']}")
            print(f"详细内容: {analysis['detailed_content']}")
            
            # 保存到 MOSS 数据库
            # await save_to_database(result)
        else:
            print("分析失败")
            
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

### Node.js 实现

```javascript
const axios = require('axios');

class MOSSAIClient {
  constructor(baseURL = 'http://localhost:8001') {
    this.baseURL = baseURL;
    this.client = axios.create({
      baseURL: baseURL,
      timeout: 30000
    });
  }

  /**
   * 提交视频分析任务
   */
  async submitVideoAnalysis(mossId, brandName, mediaId, frameLevel = 'medium') {
    try {
      const response = await this.client.post('/api/analyze-video', {
        moss_id: mossId,
        brand_name: brandName,
        media_id: mediaId,
        frame_level: frameLevel
      });
      return response.data;
    } catch (error) {
      console.error('Failed to submit analysis:', error);
      throw error;
    }
  }

  /**
   * 查询任务状态
   */
  async getTaskStatus(taskId) {
    try {
      const response = await this.client.get(`/api/task/${taskId}`);
      return response.data;
    } catch (error) {
      if (error.response && error.response.status === 404) {
        console.warn(`Task ${taskId} not found`);
        return null;
      }
      throw error;
    }
  }

  /**
   * 删除任务
   */
  async deleteTask(taskId) {
    try {
      await this.client.delete(`/api/task/${taskId}`);
      return true;
    } catch (error) {
      console.error(`Failed to delete task ${taskId}:`, error);
      return false;
    }
  }

  /**
   * 轮询直到完成
   */
  async pollUntilComplete(taskId, interval = 30000, maxAttempts = 120) {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const task = await this.getTaskStatus(taskId);
      
      if (!task) {
        console.error(`Task ${taskId} not found`);
        return null;
      }
      
      const { status, progress, message } = task;
      console.log(`Task ${taskId}: ${status} - ${progress}% - ${message}`);
      
      if (status === 'completed') {
        console.log(`Task ${taskId} completed successfully`);
        return task;
      }
      
      if (status === 'failed') {
        console.error(`Task ${taskId} failed:`, task.error_detail);
        return null;
      }
      
      // 继续轮询
      await new Promise(resolve => setTimeout(resolve, interval));
    }
    
    console.error(`Task ${taskId} timeout after ${maxAttempts} attempts`);
    return null;
  }

  /**
   * 完整的视频分析流程
   */
  async analyzeVideoComplete(mossId, brandName, mediaId, frameLevel = 'medium') {
    try {
      // 1. 提交任务
      console.log(`Submitting analysis for video ${mossId}`);
      const taskInfo = await this.submitVideoAnalysis(mossId, brandName, mediaId, frameLevel);
      const taskId = taskInfo.task_id;
      console.log(`Task submitted: ${taskId}`);
      
      // 2. 轮询直到完成
      const task = await this.pollUntilComplete(taskId, 30000);
      
      if (!task) {
        return null;
      }
      
      // 3. 提取结果
      const result = task.result;
      
      // 4. 删除任务
      await this.deleteTask(taskId);
      console.log(`Task ${taskId} deleted from MOSSAI`);
      
      return result;
      
    } catch (error) {
      console.error('Error in video analysis:', error);
      return null;
    }
  }
}

// ============================================================================
// 使用示例
// ============================================================================

async function main() {
  const client = new MOSSAIClient('http://localhost:8001');
  
  const result = await client.analyzeVideoComplete(
    'video_20231017_001',
    'nike',
    '****0343c45e0ce64664a',
    'medium'
  );
  
  if (result) {
    const { analysis } = result;
    console.log('摘要:', analysis.summary);
    console.log('标签:', analysis.tags);
    console.log('详细内容:', analysis.detailed_content);
    
    // 保存到数据库
    // await saveToDatabase(result);
  } else {
    console.log('分析失败');
  }
}

main();
```

---

## 🗄️ 数据库设计建议

### 1. tasks 表（任务历史记录）

```sql
CREATE TABLE tasks (
    task_id VARCHAR(64) PRIMARY KEY,
    moss_id VARCHAR(128) NOT NULL,
    brand_name VARCHAR(128),
    media_id VARCHAR(128) NOT NULL,
    frame_level VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT,
    progress INT DEFAULT 0,
    error_type VARCHAR(100),
    error_message TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    
    INDEX idx_moss_id (moss_id),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) COMMENT='视频分析任务历史表';
```

### 2. analysis_results 表（分析结果）

```sql
CREATE TABLE analysis_results (
    moss_id VARCHAR(128) PRIMARY KEY,
    latest_task_id VARCHAR(64) NOT NULL,
    media_id VARCHAR(128) NOT NULL,
    brand_name VARCHAR(128),
    summary TEXT NOT NULL,
    detailed_content TEXT NOT NULL,
    tags JSON NOT NULL,
    segments JSON,
    frame_level VARCHAR(20) NOT NULL,
    frame_count INT,
    video_duration FLOAT,
    video_resolution VARCHAR(20),
    model_used VARCHAR(100),
    first_analyzed_at DATETIME NOT NULL,
    last_analyzed_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_brand (brand_name),
    INDEX idx_latest_task (latest_task_id)
) COMMENT='视频分析结果表（每个视频只保留最新结果）';
```

### 数据保存示例（Python）

```python
async def save_analysis_result(result: Dict):
    """保存分析结果到数据库"""
    
    # 保存任务记录
    await db.execute("""
        INSERT INTO tasks (
            task_id, moss_id, brand_name, media_id, frame_level,
            status, message, progress, created_at, updated_at, completed_at
        ) VALUES (
            :task_id, :moss_id, :brand_name, :media_id, :frame_level,
            'completed', '分析完成', 100, :created_at, :updated_at, :completed_at
        )
    """, {
        "task_id": result["latest_task_id"],
        "moss_id": result["moss_id"],
        "brand_name": result["brand_name"],
        "media_id": result["media_id"],
        "frame_level": result["frame_level"],
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
        "completed_at": datetime.now()
    })
    
    # 保存分析结果（覆盖旧结果）
    analysis = result["analysis"]
    metadata = result["metadata"]
    
    await db.execute("""
        INSERT INTO analysis_results (
            moss_id, latest_task_id, media_id, brand_name,
            summary, detailed_content, tags, segments,
            frame_level, frame_count, video_duration, video_resolution,
            model_used, first_analyzed_at, last_analyzed_at
        ) VALUES (
            :moss_id, :task_id, :media_id, :brand_name,
            :summary, :detailed_content, :tags, :segments,
            :frame_level, :frame_count, :video_duration, :video_resolution,
            :model_used, NOW(), NOW()
        )
        ON DUPLICATE KEY UPDATE
            latest_task_id = :task_id,
            summary = :summary,
            detailed_content = :detailed_content,
            tags = :tags,
            segments = :segments,
            frame_level = :frame_level,
            frame_count = :frame_count,
            video_duration = :video_duration,
            video_resolution = :video_resolution,
            model_used = :model_used,
            last_analyzed_at = NOW()
    """, {
        "moss_id": result["moss_id"],
        "task_id": result["latest_task_id"],
        "media_id": result["media_id"],
        "brand_name": result["brand_name"],
        "summary": analysis["summary"],
        "detailed_content": analysis["detailed_content"],
        "tags": json.dumps(analysis["tags"]),
        "segments": json.dumps(analysis["segments"]),
        "frame_level": result["frame_level"],
        "frame_count": metadata["frame_count"],
        "video_duration": metadata["video_duration"],
        "video_resolution": metadata["video_resolution"],
        "model_used": metadata["model_used"]
    })
```

---

## ⚠️ 错误处理

### 常见错误及处理方式

| 错误场景 | HTTP状态码 | 处理方式 |
|---------|-----------|----------|
| 媒资ID不存在 | 400 | 检查 media_id 是否正确 |
| 任务不存在 | 404 | 任务可能已被清理，重新提交 |
| 抽帧失败 | - | status=failed，检查视频文件 |
| AI分析超时 | - | status=failed，考虑降低抽帧等级 |
| 服务不可用 | 500/503 | 实现重试机制 |

### 重试策略

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def submit_with_retry(client, moss_id, brand_name, media_id, frame_level):
    """带重试的提交"""
    return await client.submit_video_analysis(
        moss_id=moss_id,
        brand_name=brand_name,
        media_id=media_id,
        frame_level=frame_level
    )
```

---

## 🎯 最佳实践

### 1. 轮询间隔建议

- **标准视频（<5分钟）**: 30秒轮询一次
- **长视频（>5分钟）**: 60秒轮询一次
- **高并发场景**: 使用批量查询接口减少请求

### 2. 超时设置

```python
# 建议超时设置
SUBMIT_TIMEOUT = 30  # 提交任务30秒超时
POLL_TIMEOUT = 3600  # 轮询总时长1小时超时
POLL_INTERVAL = 30   # 每30秒轮询一次
```

### 3. 并发控制

MOSSAI 已内置并发控制：
- 抽帧最多 5 个并发
- AI分析最多 3 个并发

MOSS 端建议：
- 不要同时提交超过 20 个任务
- 使用队列管理待处理视频

### 4. 错误监控

建议监控以下指标：
- 任务成功率
- 平均处理时长
- 失败原因分布
- API 响应时间

### 5. 日志记录

```python
# 关键操作都记录日志
logger.info(f"Submitting task for video {moss_id}")
logger.info(f"Task {task_id} status: {status}, progress: {progress}%")
logger.info(f"Task {task_id} completed in {elapsed_time}s")
logger.error(f"Task {task_id} failed: {error_message}")
```

---

## 🔍 监控和调试

### 健康检查

```bash
# 检查服务状态
curl http://localhost:8001/health

# 响应示例
{
  "status": "healthy",
  "service": "MOSS-AI",
  "version": "0.1.0",
  "timestamp": "2025-10-17T10:30:00Z"
}
```

### 并发统计

```bash
# 查看当前并发情况
curl http://localhost:8001/api/system/concurrency

# 响应示例
{
  "concurrency": {
    "extraction": {
      "active": 3,
      "max": 5
    },
    "analysis": {
      "active": 2,
      "max": 3
    }
  },
  "tasks": {
    "total": 15,
    "by_status": {
      "pending": 5,
      "processing": 5,
      "completed": 3,
      "failed": 2,
      "retry": 0
    }
  },
  "timestamp": "2025-10-17T10:30:00Z"
}
```

---

## 📞 技术支持

如有问题，请联系：
- **开发团队**: dev@example.com
- **API 文档**: http://localhost:8001/docs
- **问题反馈**: GitHub Issues

---

## 📄 更新日志

### v0.1.0 (2025-10-17)
- ✅ 初始版本发布
- ✅ 统一视频分析接口
- ✅ 精细并发控制
- ✅ 智能内存管理
- ✅ 批量查询支持

