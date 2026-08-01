"""SpeechAdapter: `NoopSpeechAdapter` is bound + `voice_disabled` semantics."""
from __future__ import annotations

import pytest

from app.domain.ai.speech_adapter import (
    NoopSpeechAdapter,
    SpeechAdapter,
    get_speech_adapter,
)


def test_noop_adapter_disabled_by_default() -> None:
    adapter = get_speech_adapter()
    assert isinstance(adapter, NoopSpeechAdapter)
    assert adapter.enabled is False


def test_transcribe_raises_voice_disabled() -> None:
    adapter = NoopSpeechAdapter()
    with pytest.raises(NotImplementedError) as exc:
        adapter.transcribe(b"audio")
    assert "voice_disabled" in str(exc.value)


def test_synthesize_raises_voice_disabled() -> None:
    adapter = NoopSpeechAdapter()
    with pytest.raises(NotImplementedError) as exc:
        adapter.synthesize("hello")
    assert "voice_disabled" in str(exc.value)


def test_noop_conforms_to_protocol() -> None:
    assert isinstance(NoopSpeechAdapter(), SpeechAdapter)
