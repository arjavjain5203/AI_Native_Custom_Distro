"""Voice interface — future module for speech-driven interaction.

This module is a placeholder for voice-based interaction with the AI
daemon.  The planned architecture uses local Speech-to-Text (Whisper)
and Text-to-Speech for hands-free developer workflows.
"""

from __future__ import annotations

from typing import Any


class VoiceInterface:
    """Placeholder for future voice-based interaction.

    When implemented, this class will handle:
    - Local speech-to-text via Whisper
    - Wake-word detection
    - Text-to-speech for daemon responses
    - Push-to-talk keyboard shortcut integration
    """

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled

    def listen(self) -> str:
        """Capture audio and return transcribed text."""
        raise NotImplementedError("Voice interface is not yet implemented")

    def speak(self, text: str) -> None:
        """Synthesize and play the given text."""
        raise NotImplementedError("Voice interface is not yet implemented")

    def status(self) -> dict[str, Any]:
        """Return the current voice interface status."""
        return {
            "enabled": self.enabled,
            "stt_engine": None,
            "tts_engine": None,
            "status": "not_implemented",
        }
