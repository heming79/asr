import asyncio
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator, Tuple
from dataclasses import dataclass
import aiohttp

from app.core.config import settings, VolcKeyConfig
from app.core.protocol import (
    CommonUtils, RequestBuilder, ResponseParser, 
    AsrResponse, DEFAULT_SAMPLE_RATE
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AsrTask:
    task_id: str
    audio_data: bytes
    future: asyncio.Future
    key_id: Optional[str] = None


class KeyPool:
    def __init__(self, key_config: VolcKeyConfig):
        self.key_config = key_config
        self.semaphore = asyncio.Semaphore(key_config.max_concurrent)
        self.current_usage = 0
        
    @property
    def key_id(self) -> str:
        return self.key_config.key_id
    
    @property
    def app_key(self) -> str:
        return self.key_config.app_key
    
    @property
    def access_key(self) -> str:
        return self.key_config.access_key
    
    @property
    def max_concurrent(self) -> int:
        return self.key_config.max_concurrent
    
    @property
    def available_slots(self) -> int:
        return self.max_concurrent - self.current_usage
    
    async def acquire(self) -> bool:
        if self.semaphore.locked():
            return False
        await self.semaphore.acquire()
        self.current_usage += 1
        return True
    
    def release(self):
        self.semaphore.release()
        self.current_usage -= 1


class AsrWsClient:
    def __init__(self, url: str, app_key: str, access_key: str, segment_duration: int = 200):
        self.seq = 1
        self.url = url
        self.app_key = app_key
        self.access_key = access_key
        self.segment_duration = segment_duration
        self.conn = None
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc, tb):
        if self.conn and not self.conn.closed:
            await self.conn.close()
        if self.session and not self.session.closed:
            await self.session.close()
    
    def get_segment_size(self, content: bytes) -> int:
        channel_num, samp_width, frame_rate, _, _ = CommonUtils.read_wav_info(content)[:5]
        size_per_sec = channel_num * samp_width * frame_rate
        segment_size = size_per_sec * self.segment_duration // 1000
        return segment_size
            
    async def create_connection(self) -> None:
        headers = RequestBuilder.new_auth_headers(self.app_key, self.access_key)
        self.conn = await self.session.ws_connect(
            self.url,
            headers=headers
        )
        logger.info(f"Connected to {self.url} with key: {self.app_key[:8]}...")
            
    async def send_full_client_request(self) -> None:
        request = RequestBuilder.new_full_client_request(self.seq)
        self.seq += 1
        await self.conn.send_bytes(request)
        logger.info(f"Sent full client request with seq: {self.seq-1}")
        
        msg = await self.conn.receive()
        if msg.type == aiohttp.WSMsgType.BINARY:
            response = ResponseParser.parse_response(msg.data)
            logger.info(f"Received response: {response.to_dict()}")
            
    async def send_messages(self, segment_size: int, content: bytes) -> AsyncGenerator[None, None]:
        audio_segments = CommonUtils.split_audio(content, segment_size)
        total_segments = len(audio_segments)
        
        for i, segment in enumerate(audio_segments):
            is_last = (i == total_segments - 1)
            request = RequestBuilder.new_audio_only_request(
                self.seq, 
                segment,
                is_last=is_last
            )
            await self.conn.send_bytes(request)
            logger.info(f"Sent audio segment with seq: {self.seq} (last: {is_last})")
            
            if not is_last:
                self.seq += 1
                
            await asyncio.sleep(self.segment_duration / 1000)
            yield
            
    async def recv_messages(self) -> AsyncGenerator[AsrResponse, None]:
        async for msg in self.conn:
            if msg.type == aiohttp.WSMsgType.BINARY:
                response = ResponseParser.parse_response(msg.data)
                yield response
                
                if response.is_last_package or response.code != 0:
                    break
            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket error: {msg.data}")
                break
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                logger.info("WebSocket connection closed")
                break
            
    async def start_audio_stream(self, segment_size: int, content: bytes) -> AsyncGenerator[AsrResponse, None]:
        async def sender():
            async for _ in self.send_messages(segment_size, content):
                pass
                
        sender_task = asyncio.create_task(sender())
        
        try:
            async for response in self.recv_messages():
                yield response
        finally:
            sender_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
                
    async def execute(self, audio_data: bytes) -> AsyncGenerator[AsrResponse, None]:
        self.seq = 1
        
        try:
            segment_size = self.get_segment_size(audio_data)
            
            await self.create_connection()
            
            await self.send_full_client_request()
            
            async for response in self.start_audio_stream(segment_size, audio_data):
                yield response
                
        except Exception as e:
            logger.error(f"Error in ASR execution: {e}")
            raise
        finally:
            if self.conn:
                await self.conn.close()


class AsrService:
    def __init__(self):
        self.key_pools: Dict[str, KeyPool] = {}
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.worker_tasks: List[asyncio.Task] = []
        self._initialized = False
        
    async def initialize(self):
        if self._initialized:
            return
            
        for key_config in settings.volc_keys:
            self.key_pools[key_config.key_id] = KeyPool(key_config)
            
        for _ in range(settings.total_concurrent):
            task = asyncio.create_task(self._worker())
            self.worker_tasks.append(task)
            
        self._initialized = True
        logger.info(f"ASR Service initialized with {len(self.key_pools)} keys, total concurrent: {settings.total_concurrent}")
    
    async def shutdown(self):
        for task in self.worker_tasks:
            task.cancel()
        self.worker_tasks.clear()
        self._initialized = False
        logger.info("ASR Service shutdown")
    
    def _select_best_key(self) -> Optional[KeyPool]:
        available_keys = [
            pool for pool in self.key_pools.values() 
            if pool.available_slots > 0
        ]
        
        if not available_keys:
            return None
            
        available_keys.sort(key=lambda x: x.available_slots, reverse=True)
        return available_keys[0]
    
    async def _worker(self):
        while True:
            try:
                task = await self.task_queue.get()
                
                key_pool = None
                while key_pool is None:
                    key_pool = self._select_best_key()
                    if key_pool is None:
                        await asyncio.sleep(0.1)
                
                acquired = await key_pool.acquire()
                if not acquired:
                    await asyncio.sleep(0.1)
                    await self.task_queue.put(task)
                    continue
                
                task.key_id = key_pool.key_id
                logger.info(f"Task {task.task_id} acquired key {key_pool.key_id}")
                
                try:
                    result = await self._process_task(task, key_pool)
                    if not task.future.done():
                        task.future.set_result(result)
                except Exception as e:
                    logger.error(f"Task {task.task_id} failed: {e}")
                    if not task.future.done():
                        task.future.set_exception(e)
                finally:
                    key_pool.release()
                    logger.info(f"Task {task.task_id} released key {key_pool.key_id}")
                    self.task_queue.task_done()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
    
    async def _process_task(self, task: AsrTask, key_pool: KeyPool) -> Dict[str, Any]:
        async with AsrWsClient(
            url=settings.ASR_WS_URL,
            app_key=key_pool.app_key,
            access_key=key_pool.access_key,
            segment_duration=settings.SEGMENT_DURATION
        ) as client:
            responses = []
            final_text = ""
            
            async for response in client.execute(task.audio_data):
                responses.append(response.to_dict())
                
                if response.payload_msg and 'result' in response.payload_msg:
                    result = response.payload_msg['result']
                    if 'text' in result:
                        final_text = result['text']
                
                if response.is_last_package:
                    break
            
            return {
                "task_id": task.task_id,
                "key_id": task.key_id,
                "final_text": final_text,
                "responses": responses
            }
    
    async def recognize(self, audio_data: bytes) -> Dict[str, Any]:
        if not self._initialized:
            await self.initialize()
        
        task_id = f"task_{asyncio.get_event_loop().time()}_{id(audio_data)}"
        future = asyncio.get_event_loop().create_future()
        
        task = AsrTask(
            task_id=task_id,
            audio_data=audio_data,
            future=future
        )
        
        await self.task_queue.put(task)
        logger.info(f"Task {task_id} queued, queue size: {self.task_queue.qsize()}")
        
        result = await future
        return result
    
    async def recognize_file(self, file_path: str) -> Dict[str, Any]:
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        
        if not CommonUtils.judge_wav(audio_data):
            raise ValueError("Only WAV files are supported")
        
        return await self.recognize(audio_data)


asr_service = AsrService()
