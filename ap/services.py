"""Factories that turn configuration (.env) into concrete storage, notifier and pipeline objects."""
from __future__ import annotations

from ap.config import Policy, Settings
from ap.extraction.factory import build_provider
from ap.notify import ConsoleNotifier, Notifier, NullNotifier, SlackWebhookNotifier
from ap.pipeline import Pipeline
from ap.storage import CsvStorage, Storage, StorageError


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "sheets":
        from ap.storage_sheets import SheetsStorage
        return SheetsStorage.from_settings(settings)
    if settings.storage_backend == "csv":
        return CsvStorage(settings.data_dir, settings.logs_dir)
    raise StorageError(f"Unknown STORAGE_BACKEND '{settings.storage_backend}'. Use csv or sheets.")


def build_notifier(settings: Settings) -> Notifier:
    if settings.notify_backend == "slack":
        if not settings.slack_webhook_url:
            return NullNotifier()
        return SlackWebhookNotifier(settings.slack_webhook_url)
    if settings.notify_backend == "console":
        return ConsoleNotifier()
    return NullNotifier()


def build_pipeline(settings: Settings, mode: str | None = None, storage: Storage | None = None) -> Pipeline:
    mode = mode or settings.extraction_mode
    provider = build_provider(settings, mode) if mode in ("live", "mock") else None
    return Pipeline(settings, Policy.load(), storage or build_storage(settings), provider, mode)
