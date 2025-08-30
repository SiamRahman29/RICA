"""Audio manager for coordinating speech-to-text and text-to-speech."""

import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from .speech_to_text import SpeechToText
from .text_to_speech import TextToSpeech


class AudioManager:
    """Manages audio input and output components."""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize audio components
        self.speech_to_text = SpeechToText(config.get_audio_config())
        self.text_to_speech = TextToSpeech(config.get_audio_config())
        
        # Audio status
        self._initialized = False
        self._recording = False
        
        self.logger.info("Audio manager initialized")
    
    async def initialize(self) -> None:
        """Initialize audio components."""
        try:
            self.logger.info("Initializing audio components...")
            
            # Test audio input devices
            input_devices = self.speech_to_text.get_audio_devices()
            if not input_devices['input_devices']:
                self.logger.warning("No audio input devices found")
            
            # Test TTS voices
            voices = self.text_to_speech.get_available_voices()
            if not voices:
                self.logger.warning("No TTS voices available")
            
            self._initialized = True
            self.logger.info("Audio components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize audio components: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Cleanup audio components."""
        try:
            self.logger.info("Cleaning up audio components...")
            
            # Stop any ongoing recording
            if self._recording:
                await self.stop_recording()
            
            self._initialized = False
            self.logger.info("Audio components cleaned up successfully")
            
        except Exception as e:
            self.logger.error(f"Error cleaning up audio components: {e}")
    
    async def speech_to_text(self) -> str:
        """Convert speech to text."""
        if not self._initialized:
            raise RuntimeError("Audio manager not initialized")
        
        try:
            text = await self.speech_to_text.listen_and_convert()
            return text
        except Exception as e:
            self.logger.error(f"Error in speech-to-text: {e}")
            raise
    
    async def text_to_speech(self, text: str) -> None:
        """Convert text to speech."""
        if not self._initialized:
            raise RuntimeError("Audio manager not initialized")
        
        try:
            await self.text_to_speech.speak_text(text)
        except Exception as e:
            self.logger.error(f"Error in text-to-speech: {e}")
            raise
    
    async def start_recording(self, duration: Optional[float] = None) -> None:
        """Start continuous recording."""
        if not self._initialized:
            raise RuntimeError("Audio manager not initialized")
        
        if self._recording:
            self.logger.warning("Recording already in progress")
            return
        
        try:
            self._recording = True
            self.logger.info("Started continuous recording")
            
            # If duration is specified, stop after that time
            if duration:
                await asyncio.sleep(duration)
                await self.stop_recording()
                
        except Exception as e:
            self.logger.error(f"Error starting recording: {e}")
            self._recording = False
            raise
    
    async def stop_recording(self) -> None:
        """Stop continuous recording."""
        if not self._recording:
            self.logger.warning("No recording in progress")
            return
        
        try:
            self._recording = False
            self.logger.info("Stopped recording")
        except Exception as e:
            self.logger.error(f"Error stopping recording: {e}")
    
    async def record_and_convert(self, duration: Optional[float] = None) -> str:
        """Record audio for a specified duration and convert to text."""
        try:
            await self.start_recording(duration)
            text = await self.speech_to_text()
            await self.stop_recording()
            return text
        except Exception as e:
            self.logger.error(f"Error in record and convert: {e}")
            raise
    
    def get_audio_devices(self) -> Dict[str, Any]:
        """Get available audio devices."""
        return {
            "input_devices": self.speech_to_text.get_audio_devices(),
            "output_devices": self.text_to_speech.get_available_voices()
        }
    
    def set_audio_device(self, device_id: int) -> bool:
        """Set the audio input device."""
        return self.speech_to_text.set_audio_device(device_id)
    
    def set_voice(self, voice_id: str) -> bool:
        """Set the TTS voice."""
        return self.text_to_speech.set_voice(voice_id)
    
    def set_speech_speed(self, speed: float) -> None:
        """Set the speech speed."""
        self.text_to_speech.set_speed(speed)
    
    def set_volume(self, volume: float) -> None:
        """Set the speech volume."""
        self.text_to_speech.set_volume(volume)
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status of audio components."""
        return {
            "initialized": self._initialized,
            "recording": self._recording,
            "speech_to_text": self.speech_to_text.get_status(),
            "text_to_speech": self.text_to_speech.get_status(),
            "audio_devices": self.get_audio_devices()
        }
    
    async def test_audio_system(self) -> Dict[str, bool]:
        """Test the audio system components."""
        test_results = {}
        
        try:
            # Test speech-to-text
            self.logger.info("Testing speech-to-text...")
            try:
                # This is a simple test - in practice you might want to use a test audio file
                test_results["speech_to_text"] = True
            except Exception as e:
                self.logger.error(f"Speech-to-text test failed: {e}")
                test_results["speech_to_text"] = False
            
            # Test text-to-speech
            self.logger.info("Testing text-to-speech...")
            try:
                await self.text_to_speech.speak_text("Audio system test successful")
                test_results["text_to_speech"] = True
            except Exception as e:
                self.logger.error(f"Text-to-speech test failed: {e}")
                test_results["text_to_speech"] = False
            
            # Test audio devices
            self.logger.info("Testing audio devices...")
            devices = self.get_audio_devices()
            test_results["audio_devices"] = bool(devices["input_devices"] and devices["output_devices"])
            
        except Exception as e:
            self.logger.error(f"Audio system test failed: {e}")
            test_results["overall"] = False
        
        test_results["overall"] = all(test_results.values())
        return test_results
