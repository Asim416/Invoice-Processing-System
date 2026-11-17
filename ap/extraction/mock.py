"""Mock provider: returns a stored fixture for a known file. Always labeled mock in output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ap.extraction.base import ExtractionResponse, ProviderError
from ap.schemas import ErrorCode


class MockProvider:
    name = "mock"
    model = "fixture"
    last_wait_ms = 0

    def __init__(self, fixture_dir: Path):
        self.fixture_dir = Path(fixture_dir)

    def extract(self, text: str, feedback: Optional[str] = None, *, source: str = "") -> ExtractionResponse:
        f = self.fixture_dir / f"{source}.json"
        if not f.exists():
            raise ProviderError(f"No mock fixture for '{source}'. Use --mode live for unknown invoices.",
                                code=ErrorCode.LLM_UNAVAILABLE, retryable=False)
        return ExtractionResponse(raw=f.read_text(), usage=None)
