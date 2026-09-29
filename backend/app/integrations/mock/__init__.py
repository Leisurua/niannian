"""Deterministic Mock adapters. All outputs are labelled provider=mock."""

from .adapters import (
    MockASR, MockAvatar, MockEmbedding, MockLLM, MockPush, MockTTS,
    MockWakeWord, MockWeather,
)

__all__ = [
    "MockASR", "MockAvatar", "MockEmbedding", "MockLLM", "MockPush",
    "MockTTS", "MockWakeWord", "MockWeather",
]
