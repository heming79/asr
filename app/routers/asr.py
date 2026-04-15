import os
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.services.asr_service import asr_service
from app.core.protocol import CommonUtils

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/asr", tags=["ASR"])


class AsrRequest(BaseModel):
    file_path: Optional[str] = None


class AsrResponse(BaseModel):
    task_id: str
    key_id: str
    final_text: str
    status: str = "success"


@router.post("/streaming", response_model=AsrResponse)
async def streaming_asr(
    background_tasks: BackgroundTasks,
    file_path: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    """
    流式语音识别接口
    
    - 可以通过 file_path 参数指定本地文件路径
    - 也可以通过上传文件的方式
    - 如果都不指定，默认使用 d:/test.wav
    """
    try:
        audio_data = None
        
        if file:
            audio_data = await file.read()
            logger.info(f"Received uploaded file: {file.filename}, size: {len(audio_data)} bytes")
        elif file_path:
            if not os.path.exists(file_path):
                raise HTTPException(status_code=400, detail=f"File not found: {file_path}")
            with open(file_path, 'rb') as f:
                audio_data = f.read()
            logger.info(f"Read file from path: {file_path}, size: {len(audio_data)} bytes")
        else:
            default_path = "d:/test.wav"
            if not os.path.exists(default_path):
                raise HTTPException(
                    status_code=400, 
                    detail="No file provided and default file d:/test.wav not found"
                )
            with open(default_path, 'rb') as f:
                audio_data = f.read()
            logger.info(f"Using default file: {default_path}, size: {len(audio_data)} bytes")
        
        if not CommonUtils.judge_wav(audio_data):
            raise HTTPException(status_code=400, detail="Only WAV format audio files are supported")
        
        result = await asr_service.recognize(audio_data)
        
        return AsrResponse(
            task_id=result["task_id"],
            key_id=result["key_id"],
            final_text=result["final_text"],
            status="success"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ASR processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """
    获取服务状态
    """
    from app.services.asr_service import asr_service
    from app.core.config import settings
    
    key_status = {}
    for key_id, pool in asr_service.key_pools.items():
        key_status[key_id] = {
            "max_concurrent": pool.max_concurrent,
            "current_usage": pool.current_usage,
            "available_slots": pool.available_slots
        }
    
    return {
        "status": "running",
        "total_concurrent": settings.total_concurrent,
        "queue_size": asr_service.task_queue.qsize(),
        "keys": key_status
    }
