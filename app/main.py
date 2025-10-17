"""Main FastAPI application entry point"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.api.routes import router

# Configure logging
log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
if settings.debug:
    log_level = logging.DEBUG

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    
    # Check ffmpeg availability
    from app.utils.media_converter import media_converter
    if media_converter.check_ffmpeg_available():
        logger.info("FFmpeg is available")
    else:
        logger.warning("FFmpeg is not available - GIF conversion may not work")
    
    yield
    
    # Shutdown
    logger.info(f"Shutting down {settings.app_name}")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    MOSS-AI - Video Frame Extraction and Analysis Service
    
    This service provides:
    - Frame extraction from videos using Aliyun ICE
    - AI-powered video content analysis using Doubao models
    - Support for video, image, and GIF formats
    - Intelligent and fixed-interval frame extraction
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

