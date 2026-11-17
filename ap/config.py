"""Configuration: environment variables for secrets and runtime, YAML for business policy."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

try:  # .env is optional; mock mode needs no key
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Policy:
    amount_tolerance_pct: float = 1.0
    unit_price_tolerance_pct: float = 1.0
    quantity_over_allowed: float = 0
    supported_currencies: tuple[str, ...] = ("USD", "EUR")
    max_file_mb: float = 10
    extraction_retry_limit: int = 1
    manager_escalation_threshold: float = 5000

    @classmethod
    def load(cls, path: Path | None = None) -> "Policy":
        path = path or ROOT / "config" / "policy.yaml"
        raw = yaml.safe_load(Path(path).read_text()) or {}
        raw["supported_currencies"] = tuple(raw.get("supported_currencies", ("USD", "EUR")))
        return cls(**raw)


@dataclass(frozen=True)
class Settings:
    provider: str = "groq"
    base_url: str = "https://api.groq.com/openai/v1"
    api_key: str = field(default="", repr=False)   # repr=False keeps the key out of logs
    model: str = "qwen/qwen3.8-27b"
    reasoning_effort: str = "low"
    timeout_seconds: float = 60.0
    max_tokens: int = 2000
    tokens_per_minute: int = 6000
    extraction_mode: str = "mock"
    storage_backend: str = "csv"            # csv | sheets
    google_sheet_id: str = ""
    google_credentials_file: str = ""       # path to a service-account JSON key (never commit it)
    notify_backend: str = "none"            # none | console | slack
    slack_webhook_url: str = field(default="", repr=False)   # secret
    data_dir: Path = ROOT / "data"
    logs_dir: Path = ROOT / "logs"
    cache_dir: Path = ROOT / "cache" / "extractions"

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        e = os.environ
        base = dict(
            provider=e.get("LLM_PROVIDER", "groq"),
            base_url=e.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
            api_key=e.get("LLM_API_KEY", ""),
            model=e.get("LLM_MODEL", "qwen/qwen3.8-27b"),
            reasoning_effort=e.get("LLM_REASONING_EFFORT", "low"),
            timeout_seconds=float(e.get("LLM_TIMEOUT_SECONDS", "60")),
            max_tokens=int(e.get("LLM_MAX_TOKENS", "2000")),
            tokens_per_minute=int(e.get("LLM_TOKENS_PER_MINUTE", "6000")),
            extraction_mode=e.get("EXTRACTION_MODE", "live").strip().lower(),
            storage_backend=e.get("STORAGE_BACKEND", "csv").strip().lower(),
            google_sheet_id=e.get("GOOGLE_SHEET_ID", "").strip(),
            google_credentials_file=e.get("GOOGLE_CREDENTIALS_FILE", "").strip(),
            notify_backend=e.get("NOTIFY_BACKEND", "none").strip().lower(),
            slack_webhook_url=e.get("SLACK_WEBHOOK_URL", "").strip(),
        )
        for env_name, key in (("DATA_DIR", "data_dir"), ("LOGS_DIR", "logs_dir"), ("CACHE_DIR", "cache_dir")):
            if e.get(env_name):
                base[key] = Path(e[env_name])
        base.update(overrides)
        return cls(**base)
