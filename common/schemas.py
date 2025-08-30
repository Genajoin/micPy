from pydantic import BaseModel, ConfigDict
from typing import Optional

class TranscribeRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    audio_data: str  # base64 encoded audio
    model_size: Optional[str] = "medium"
    language: Optional[str] = None

class TranscribeResponse(BaseModel):
    text: str
    success: bool
    error: Optional[str] = None
    processing_time: Optional[float] = None

class ServerStatus(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    
    status: str  # "ready", "processing", "error"
    model_loaded: bool
    gpu_available: bool
    current_model: str