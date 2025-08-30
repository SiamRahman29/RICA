"""Tests for configuration management."""

import pytest
from rica.core.config import Config


class TestConfig:
    """Test configuration class."""
    
    def test_config_creation(self):
        """Test config creation with defaults."""
        config = Config(
            openai_api_key="test_key",
            openai_model="gpt-3.5-turbo"
        )
        
        assert config.openai_api_key == "test_key"
        assert config.openai_model == "gpt-3.5-turbo"
        assert config.audio_sample_rate == 16000
        assert config.host == "127.0.0.1"
        assert config.port == 8000
    
    def test_get_openai_config(self):
        """Test OpenAI config retrieval."""
        config = Config(
            openai_api_key="test_key",
            openai_model="gpt-4"
        )
        
        openai_config = config.get_openai_config()
        assert openai_config["api_key"] == "test_key"
        assert openai_config["model"] == "gpt-4"
    
    def test_get_audio_config(self):
        """Test audio config retrieval."""
        config = Config(
            openai_api_key="test_key",
            audio_sample_rate=44100,
            audio_channels=2
        )
        
        audio_config = config.get_audio_config()
        assert audio_config["sample_rate"] == 44100
        assert audio_config["channels"] == 2
        assert audio_config["chunk_size"] == 1024
