from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SpeechAdapter(Protocol):
    enabled: bool

    def transcribe(self, audio_bytes: bytes) -> str: ...

    def synthesize(self, text: str) -> bytes: ...


class NoopSpeechAdapter:
    enabled = False

    def transcribe(self, audio_bytes: bytes) -> str:  # noqa: ARG002
        raise NotImplementedError("voice_disabled")

    def synthesize(self, text: str) -> bytes:  # noqa: ARG002
        raise NotImplementedError("voice_disabled")


_adapter: SpeechAdapter = NoopSpeechAdapter()


def get_speech_adapter() -> SpeechAdapter:
    return _adapter
