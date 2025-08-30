"""Speech-to-text functionality using speech recognition."""

import asyncio
import logging
from typing import Optional
import speech_recognition as sr
import sounddevice as sd
import numpy as np
from pydub import AudioSegment
from pydub.playback import play


class SpeechToText:
    """Speech-to-text conversion using speech recognition."""
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.energy_threshold = 4000
        self.recognizer.dynamic_energy_threshold = True
        
        # Audio settings
        self.sample_rate = config.get("sample_rate", 16000)
        self.channels = config.get("channels", 1)
        self.chunk_size = config.get("chunk_size", 1024)
        
        # Speech recognition settings
        self.timeout = config.get("speech_recognition_timeout", 5.0)
        self.phrase_time_limit = config.get("speech_recognition_phrase_time_limit", 10.0)
        
        self.logger.info("Speech-to-text component initialized")
    
    async def listen_and_convert(self) -> str:
        """Listen for speech and convert to text."""
        try:
            self.logger.info("Listening for speech...")
            
            # Use microphone as source
            with sr.Microphone(sample_rate=self.sample_rate) as source:
                # Adjust for ambient noise
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen for audio
                audio = self.recognizer.listen(
                    source,
                    timeout=self.timeout,
                    phrase_time_limit=self.phrase_time_limit
                )
                
                self.logger.info("Audio captured, processing...")
                
                # Convert speech to text
                text = await self._recognize_speech(audio)
                
                self.logger.info(f"Speech converted: {text}")
                return text
                
        except sr.WaitTimeoutError:
            self.logger.warning("No speech detected within timeout")
            raise TimeoutError("No speech detected")
        except Exception as e:
            self.logger.error(f"Error in speech recognition: {e}")
            raise
    
    async def _recognize_speech(self, audio: sr.AudioData) -> str:
        """Recognize speech from audio data."""
        try:
            # Try Google Speech Recognition first
            text = self.recognizer.recognize_google(audio)
            return text
        except sr.UnknownValueError:
            self.logger.warning("Speech was unintelligible")
            raise ValueError("Speech was unintelligible")
        except sr.RequestError as e:
            self.logger.error(f"Could not request results from Google Speech Recognition: {e}")
            # Fallback to other recognition services if available
            raise
        except Exception as e:
            self.logger.error(f"Error in speech recognition: {e}")
            raise
    
    async def listen_from_file(self, audio_file_path: str) -> str:
        """Convert speech from an audio file to text."""
        try:
            self.logger.info(f"Processing audio file: {audio_file_path}")
            
            # Load audio file
            with sr.AudioFile(audio_file_path) as source:
                audio = self.recognizer.record(source)
                
                # Convert to text
                text = await self._recognize_speech(audio)
                
                self.logger.info(f"File converted: {text}")
                return text
                
        except Exception as e:
            self.logger.error(f"Error processing audio file: {e}")
            raise
    
    def get_audio_devices(self) -> dict:
        """Get available audio input devices."""
        try:
            devices = sd.query_devices()
            input_devices = []
            
            for i, device in enumerate(devices):
                if device['max_inputs'] > 0:
                    input_devices.append({
                        'id': i,
                        'name': device['name'],
                        'channels': device['max_inputs'],
                        'sample_rate': device['default_samplerate']
                    })
            
            return {'input_devices': input_devices}
            
        except Exception as e:
            self.logger.error(f"Error getting audio devices: {e}")
            return {'input_devices': []}
    
    def set_audio_device(self, device_id: int) -> bool:
        """Set the audio input device."""
        try:
            devices = sd.query_devices()
            if 0 <= device_id < len(devices) and devices[device_id]['max_inputs'] > 0:
                sd.default.device[0] = device_id
                self.logger.info(f"Audio input device set to: {devices[device_id]['name']}")
                return True
            else:
                self.logger.error(f"Invalid audio device ID: {device_id}")
                return False
        except Exception as e:
            self.logger.error(f"Error setting audio device: {e}")
            return False
    
    def get_status(self) -> dict:
        """Get current status of speech recognition."""
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "timeout": self.timeout,
            "phrase_time_limit": self.phrase_time_limit,
            "energy_threshold": self.recognizer.energy_threshold,
            "dynamic_energy_threshold": self.recognizer.dynamic_energy_threshold,
            "audio_devices": self.get_audio_devices()
        }
