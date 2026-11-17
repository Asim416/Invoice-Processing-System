"""Structured JSON logging. Never log invoice text, amounts at info level, or secrets."""
from __future__ import annotations

import json
import logging
import sys

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                   "event": record.getMessage()}
        for k, v in record.__dict__.items():
            if k not in _RESERVED:
                payload[k] = v
        return json.dumps(payload, default=str)


class _StderrHandler(logging.StreamHandler):
    """Always writes to the CURRENT sys.stderr (so redirection and test capture work)."""

    def __init__(self):
        logging.Handler.__init__(self)

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, _):
        pass


def get_logger(name: str = "ap") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        h = _StderrHandler()
        h.setFormatter(JsonFormatter())
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
