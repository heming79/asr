import json
from typing import List, Dict, Any
from pydantic import BaseModel
from pydantic_settings import BaseSettings


class VolcKeyConfig(BaseModel):
    key_id: str
    app_key: str
    access_key: str
    max_concurrent: int = 3


class Settings(BaseSettings):
    VOLC_KEYS_CONFIG: str = '[{"key_id":"tiyan01","app_key":"5908854963","access_key":"hEHVg2S8fpg3ih9zmsELOzmGbMP89DWy","max_concurrent":3},{"key_id":"tiyan02","app_key":"1271279660","access_key":"lezyzPsQ68J3ZtR5CbOkTPrZe1ZDyM6f","max_concurrent":3},{"key_id":"tiyan03","app_key":"8581953827","access_key":"UMlqA_Anul815mC8M5nj2kKXtOGlUV29","max_concurrent":3}]'
    
    ASR_WS_URL: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
    DEFAULT_SAMPLE_RATE: int = 16000
    SEGMENT_DURATION: int = 200
    
    HOST: str = "0.0.0.0"
    PORT: int = 8005
    
    @property
    def volc_keys(self) -> List[VolcKeyConfig]:
        keys_data = json.loads(self.VOLC_KEYS_CONFIG)
        return [VolcKeyConfig(**key) for key in keys_data]
    
    @property
    def total_concurrent(self) -> int:
        return sum(key.max_concurrent for key in self.volc_keys)


settings = Settings()
