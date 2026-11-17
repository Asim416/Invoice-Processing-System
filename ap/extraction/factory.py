from __future__ import annotations

from pathlib import Path

from ap.config import Settings
from ap.extraction.mock import MockProvider
from ap.extraction.openai_compatible import OpenAICompatibleProvider


def build_provider(settings: Settings, mode: str, fixture_dir: Path | None = None):
    if mode == "mock":
        return MockProvider(fixture_dir or settings.data_dir / "ground_truth")
    if mode == "live":
        return OpenAICompatibleProvider(
            base_url=settings.base_url, api_key=settings.api_key, model=settings.model, name=settings.provider,
            reasoning_effort=settings.reasoning_effort, timeout=settings.timeout_seconds,
            max_tokens=settings.max_tokens, tokens_per_minute=settings.tokens_per_minute)
    raise ValueError(f"Unknown mode: {mode}")
