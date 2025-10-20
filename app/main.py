"""Main FastAPI application entry point"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging  # 新的日志系统
from app.api.routes import router, cleanup_old_tasks

# 初始化日志系统
logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    
    # Start background cleanup task
    cleanup_task = asyncio.create_task(cleanup_old_tasks())
    logger.info("Memory cleanup task started")
    
    # Start scheduled cleanup service (日志清理等)
    try:
        from app.core.scheduled_cleanup import start_scheduled_cleanup_service
        await start_scheduled_cleanup_service(
            hour=2,  # 每天凌晨2点执行
            minute=0,
            log_retention_days=7,  # 日志保留7天
        )
        logger.info("✅ Scheduled cleanup service started")
    except Exception as e:
        logger.error(f"Failed to start scheduled cleanup service: {e}")
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.app_name}")
    
    # Stop scheduled cleanup service
    try:
        from app.core.scheduled_cleanup import stop_scheduled_cleanup_service
        await stop_scheduled_cleanup_service()
        logger.info("Scheduled cleanup service stopped")
    except Exception as e:
        logger.error(f"Failed to stop scheduled cleanup service: {e}")
    
    # Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        logger.info("Memory cleanup task stopped")
        pass


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    MOSS-AI - Video Frame Extraction and Analysis Service
    
    This service provides:
    - Frame extraction from videos using Aliyun OSS real-time processing
    - AI-powered video content analysis using Doubao models
    - Support for video and image analysis
    - Intelligent concurrent task processing with automatic memory management
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle uncaught exceptions"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.debug else "An unexpected error occurred",
            "detail": None
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.mossai_host,
        port=settings.mossai_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )

