"""Speech-to-Text service using OpenAI Whisper or AssemblyAI.

Blueprint section 4.2 - Primary: OpenAI Whisper API, Alternative: AssemblyAI.
"""

from __future__ import annotations

import io
from typing import Literal

from openai import AsyncOpenAI

from services.hermes.core.settings import get_settings


class STTService:
    """Speech-to-Text client supporting multiple providers."""
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
        )
    
    async def transcribe(
        self,
        audio_content: bytes,
        filename: str,
        provider: Literal["whisper", "assemblyai"] = "whisper",
    ) -> str:
        """Transcribe audio to text.
        
        Args:
            audio_content: Raw audio bytes
            filename: Original filename for extension detection
            provider: STT provider to use
            
        Returns:
            Transcribed text
        """
        if provider == "whisper":
            return await self._transcribe_whisper(audio_content, filename)
        elif provider == "assemblyai":
            return await self._transcribe_assemblyai(audio_content)
        else:
            raise ValueError(f"Unknown STT provider: {provider}")
    
    async def _transcribe_whisper(self, audio_content: bytes, filename: str) -> str:
        """Transcribe using OpenAI Whisper API."""
        # Create file-like object from bytes
        audio_file = io.BytesIO(audio_content)
        audio_file.name = filename
        
        try:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
            )
            return response
        except Exception as e:
            # Log error and fall back to mock for now
            print(f"Whisper transcription failed: {e}")
            return f"[Whisper transcription unavailable - {filename}]"
    
    async def _transcribe_assemblyai(self, audio_content: bytes) -> str:
        """Transcribe using AssemblyAI (placeholder)."""
        # TODO: Implement AssemblyAI integration
        # Requires: settings.assemblyai_api_key
        return "[AssemblyAI transcription - not yet configured]"


# Singleton instance
_stt_service: STTService | None = None


def get_stt_service() -> STTService:
    """Get or create STT service singleton."""
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service


async def transcribe_audio(
    audio_content: bytes,
    filename: str,
    provider: Literal["whisper", "assemblyai"] = "whisper",
) -> str:
    """Convenience function to transcribe audio."""
    service = get_stt_service()
    return await service.transcribe(audio_content, filename, provider)