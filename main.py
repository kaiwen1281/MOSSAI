"""Main entry point for MOSS-AI application"""
from app.main import app
from app.core.config import settings

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.mossai_host,
        port=settings.mossai_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
