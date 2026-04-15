from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.routers import asr
from app.services.asr_service import asr_service

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ASR Service...")
    await asr_service.initialize()
    logger.info(f"ASR Service started on {settings.HOST}:{settings.PORT}")
    yield
    logger.info("Shutting down ASR Service...")
    await asr_service.shutdown()
    logger.info("ASR Service shutdown complete")


app = FastAPI(
    title="ASR Streaming API",
    description="火山引擎流式语音识别API服务",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(asr.router)


@app.get("/")
async def root():
    return {
        "message": "ASR Streaming API",
        "version": "1.0.0",
        "endpoints": {
            "streaming": "/api/v1/asr/streaming",
            "status": "/api/v1/asr/status"
        }
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
