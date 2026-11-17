"""OpenAI-compatible provider: retries, backoff, throttling, error mapping. Uses a fake client (no network)."""
from types import SimpleNamespace

import openai
import pytest

from ap.extraction.base import ProviderError, ProviderOutputInvalid, wire_schema
from ap.extraction.openai_compatible import OpenAICompatibleProvider
from ap.schemas import ErrorCode

REQ = SimpleNamespace(method="POST", url="http://example.test")   # duck-typed: independent of the HTTP library


def resp(content='{"ok": true}', finish="stop", tokens=100):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=finish)],
                           usage=SimpleNamespace(prompt_tokens=tokens - 10, completion_tokens=10, total_tokens=tokens))


def status_err(cls, code, headers=None):
    response = SimpleNamespace(status_code=code, headers=headers or {}, request=REQ)
    return cls("err", response=response, body=None)


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        o = self.outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return o


def provider(outcomes, sleeps=None, **kw):
    sleeps = sleeps if sleeps is not None else []
    c = FakeClient(outcomes)
    p = OpenAICompatibleProvider(base_url="http://x", api_key="k", model="m", client=c, sleep=sleeps.append, **kw)
    return p, c, sleeps


def test_success_returns_raw_and_usage():
    p, c, _ = provider([resp(tokens=120)])
    r = p.extract("invoice text")
    assert r.raw == '{"ok": true}' and r.usage["total_tokens"] == 120


def test_request_uses_strict_json_schema_temperature_zero_and_reasoning_effort():
    p, c, _ = provider([resp()], reasoning_effort="low")
    p.extract("t")
    kw = c.calls[0]
    assert kw["temperature"] == 0
    assert kw["response_format"]["json_schema"]["strict"] is True
    assert kw["response_format"]["json_schema"]["schema"] == wire_schema()
    assert kw["extra_body"] == {"reasoning_effort": "low"}
    assert "<invoice_text>" in kw["messages"][1]["content"]


def test_retry_after_header_is_honored_on_429():
    p, c, sleeps = provider([status_err(openai.RateLimitError, 429, {"retry-after": "7"}), resp()])
    p.extract("t")
    assert len(c.calls) == 2 and sleeps == [7.0]


def test_retry_after_zero_is_honored_not_treated_as_missing():
    p, c, sleeps = provider([status_err(openai.RateLimitError, 429, {"retry-after": "0"}), resp()])
    p.extract("t")
    assert sleeps == [0.0]


def test_very_long_retry_after_is_capped():
    p, c, sleeps = provider([status_err(openai.RateLimitError, 429, {"retry-after": "900"}), resp()])
    p.extract("t")
    assert sleeps == [60.0]


def test_429_exhausted_maps_to_rate_limited_error():
    p, c, _ = provider([status_err(openai.RateLimitError, 429)] * 3)
    with pytest.raises(ProviderError) as e:
        p.extract("t")
    assert e.value.code == ErrorCode.LLM_RATE_LIMITED and e.value.retryable and len(c.calls) == 3


def test_5xx_retries_then_succeeds():
    p, c, sleeps = provider([status_err(openai.InternalServerError, 500), status_err(openai.InternalServerError, 503), resp()])
    assert p.extract("t").raw and len(c.calls) == 3 and len(sleeps) == 2


def test_5xx_exhausted_is_unavailable():
    p, c, _ = provider([status_err(openai.InternalServerError, 500)] * 3)
    with pytest.raises(ProviderError) as e:
        p.extract("t")
    assert e.value.code == ErrorCode.LLM_UNAVAILABLE and len(c.calls) == 3


def test_timeout_and_connection_errors_are_retried():
    p, c, _ = provider([openai.APITimeoutError(request=REQ), openai.APIConnectionError(request=REQ), resp()])
    assert p.extract("t").raw and len(c.calls) == 3


@pytest.mark.parametrize("cls,code", [(openai.BadRequestError, 400), (openai.AuthenticationError, 401)])
def test_client_errors_are_not_retried(cls, code):
    p, c, sleeps = provider([status_err(cls, code), resp()])
    with pytest.raises(ProviderError) as e:
        p.extract("t")
    assert e.value.retryable is False and len(c.calls) == 1 and sleeps == []


def test_empty_content_is_output_invalid():
    p, _, _ = provider([resp(content="  ")])
    with pytest.raises(ProviderOutputInvalid):
        p.extract("t")


def test_truncated_output_is_output_invalid():
    p, _, _ = provider([resp(finish="length")])
    with pytest.raises(ProviderOutputInvalid):
        p.extract("t")


def test_throttle_waits_when_tokens_per_minute_would_be_exceeded():
    now = [0.0]
    sleeps = []

    def sleep(s):
        sleeps.append(s); now[0] += s

    c = FakeClient([resp(tokens=900), resp(tokens=900)])
    p = OpenAICompatibleProvider(base_url="x", api_key="k", model="m", client=c, sleep=sleep, clock=lambda: now[0],
                                 tokens_per_minute=1500, max_tokens=100)
    p.extract("a" * 30)
    assert p.last_wait_ms == 0
    p.extract("a" * 30)               # 900 used + estimate > 1500, so it must wait for the window to clear
    assert p.last_wait_ms > 0 and sum(sleeps) >= 59


def test_first_call_never_waits_even_if_estimate_exceeds_limit():
    p, _, sleeps = provider([resp()], tokens_per_minute=10)
    p.extract("t")
    assert sleeps == [] and p.last_wait_ms == 0


def test_wire_schema_is_strict_and_reference_free():
    import json
    s = wire_schema()
    blob = json.dumps(s)
    assert "$ref" not in blob and "$defs" not in blob
    assert s["additionalProperties"] is False and set(s["required"]) == set(s["properties"])
    assert s["properties"]["line_items"]["items"]["additionalProperties"] is False


def test_settings_repr_does_not_expose_api_key():
    from ap.config import Settings
    assert "SECRET-KEY-123" not in repr(Settings.from_env(api_key="SECRET-KEY-123"))
