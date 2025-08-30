"""Configuration management for RICA."""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseSettings, Field


class Config(BaseSettings):
    """Configuration for RICA."""
    
    # OpenAI Configuration
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4", env="OPENAI_MODEL")
    
    # Audio Configuration
    audio_sample_rate: int = Field(default=16000, env="AUDIO_SAMPLE_RATE")
    audio_channels: int = Field(default=1, env="AUDIO_CHANNELS")
    audio_chunk_size: int = Field(default=1024, env="AUDIO_CHUNK_SIZE")
    
    # Speech Recognition
    speech_recognition_timeout: float = Field(default=5.0, env="SPEECH_RECOGNITION_TIMEOUT")
    speech_recognition_phrase_time_limit: float = Field(default=10.0, env="SPEECH_PHRASE_TIME_LIMIT")
    
    # Text-to-Speech
    tts_voice_id: Optional[str] = Field(default=None, env="TTS_VOICE_ID")
    tts_speed: float = Field(default=1.0, env="TTS_SPEED")
    
    # Server Configuration
    host: str = Field(default="127.0.0.1", env="HOST")
    port: int = Field(default=8000, env="PORT")
    debug: bool = Field(default=False, env="DEBUG")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Optional[Path] = Field(default=None, env="LOG_FILE")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    @classmethod
    def load_from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls()
    
    def get_openai_config(self) -> dict:
        """Get OpenAI configuration as a dictionary."""
        return {
            "api_key": self.openai_api_key,
            "model": self.openai_model,
        }
    
    def get_audio_config(self) -> dict:
        """Get audio configuration as a dictionary."""
        return {
            "sample_rate": self.audio_sample_rate,
            "channels": self.audio_channels,
            "chunk_size": self.audio_chunk_size,
        }
