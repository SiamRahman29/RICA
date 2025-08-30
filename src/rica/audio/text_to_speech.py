"""Text-to-speech functionality using pyttsx3."""

import asyncio
import logging
from typing import Optional
import pyttsx3
import tempfile
import os


class TextToSpeech:
    """Text-to-speech conversion using pyttsx3."""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize TTS engine
        self.engine = pyttsx3.init()
        
        # Configure TTS settings
        self._configure_engine()
        
        # TTS settings
        self.voice_id = config.get("tts_voice_id")
        self.speed = config.get("tts_speed", 1.0)
        
        self.logger.info("Text-to-speech component initialized")
    
    def _configure_engine(self) -> None:
        """Configure the TTS engine with default settings."""
        try:
            # Get available voices
            voices = self.engine.getProperty('voices')
            
            # Set default voice (first available)
            if voices:
                self.engine.setProperty('voice', voices[0].id)
                self.logger.info(f"Default voice set: {voices[0].name}")
            
            # Set default properties
            self.engine.setProperty('rate', 150)  # Speed of speech
            self.engine.setProperty('volume', 0.9)  # Volume level
            
            self.logger.info("TTS engine configured successfully")
            
        except Exception as e:
            self.logger.error(f"Error configuring TTS engine: {e}")
            raise
    
    async def speak_text(self, text: str) -> None:
        """Convert text to speech and play it."""
        try:
            self.logger.info(f"Converting text to speech: {text[:50]}...")
            
            # Run TTS in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._speak_sync, text)
            
            self.logger.info("Text-to-speech completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error in text-to-speech: {e}")
            raise
    
    def _speak_sync(self, text: str) -> None:
        """Synchronous text-to-speech (runs in executor)."""
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            self.logger.error(f"Error in synchronous TTS: {e}")
            raise
    
    async def save_to_file(self, text: str, file_path: str) -> str:
        """Convert text to speech and save to audio file."""
        try:
            self.logger.info(f"Saving speech to file: {file_path}")
            
            # Run TTS in a thread
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._save_to_file_sync, text, file_path)
            
            self.logger.info(f"Speech saved to: {file_path}")
            return file_path
            
        except Exception as e:
            self.logger.error(f"Error saving speech to file: {e}")
            raise
    
    def _save_to_file_sync(self, text: str, file_path: str) -> None:
        """Synchronous save to file (runs in executor)."""
        try:
            self.engine.save_to_file(text, file_path)
            self.engine.runAndWait()
        except Exception as e:
            self.logger.error(f"Error in synchronous save to file: {e}")
            raise
    
    def set_voice(self, voice_id: str) -> bool:
        """Set the TTS voice."""
        try:
            voices = self.engine.getProperty('voices')
            
            # Find voice by ID
            for voice in voices:
                if voice.id == voice_id:
                    self.engine.setProperty('voice', voice.id)
                    self.voice_id = voice_id
                    self.logger.info(f"Voice set to: {voice.name}")
                    return True
            
            self.logger.warning(f"Voice ID not found: {voice_id}")
            return False
            
        except Exception as e:
            self.logger.error(f"Error setting voice: {e}")
            return False
    
    def set_speed(self, speed: float) -> None:
        """Set the speech rate."""
        try:
            if 0.1 <= speed <= 3.0:
                self.engine.setProperty('rate', int(150 * speed))
                self.speed = speed
                self.logger.info(f"Speech speed set to: {speed}")
            else:
                self.logger.warning(f"Speed value out of range (0.1-3.0): {speed}")
        except Exception as e:
            self.logger.error(f"Error setting speed: {e}")
    
    def set_volume(self, volume: float) -> None:
        """Set the speech volume."""
        try:
            if 0.0 <= volume <= 1.0:
                self.engine.setProperty('volume', volume)
                self.logger.info(f"Volume set to: {volume}")
            else:
                self.logger.warning(f"Volume value out of range (0.0-1.0): {volume}")
        except Exception as e:
            self.logger.error(f"Error setting volume: {e}")
    
    def get_available_voices(self) -> list:
        """Get list of available voices."""
        try:
            voices = self.engine.getProperty('voices')
            voice_list = []
            
            for voice in voices:
                voice_list.append({
                    'id': voice.id,
                    'name': voice.name,
                    'languages': voice.languages,
                    'gender': voice.gender,
                    'age': voice.age
                })
            
            return voice_list
            
        except Exception as e:
            self.logger.error(f"Error getting available voices: {e}")
            return []
    
    def get_current_voice(self) -> dict:
        """Get current voice information."""
        try:
            current_voice_id = self.engine.getProperty('voice')
            voices = self.engine.getProperty('voices')
            
            for voice in voices:
                if voice.id == current_voice_id:
                    return {
                        'id': voice.id,
                        'name': voice.name,
                        'languages': voice.languages,
                        'gender': voice.gender,
                        'age': voice.age
                    }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error getting current voice: {e}")
            return {}
    
    def get_status(self) -> dict:
        """Get current status of text-to-speech."""
        return {
            "voice_id": self.voice_id,
            "speed": self.speed,
            "rate": self.engine.getProperty('rate'),
            "volume": self.engine.getProperty('volume'),
            "current_voice": self.get_current_voice(),
            "available_voices": len(self.get_available_voices())
        }
