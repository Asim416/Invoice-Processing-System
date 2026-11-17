import json
from types import SimpleNamespace

from ap.extraction.openai_compatible import OpenAICompatibleProvider
from ap.pdf_render import render_pdf_pages


def _payload(vendor="Acme GmbH", total=119.0, line_items=None):
    return {
        "vendor_name": vendor,
        "invoice_number": "INV-100",
        "invoice_date": "2026-11-01",
        "po_number": None,
        "currency": "EUR",
        "line_items": line_items or [],
        "total": total,
        "subtotal": 100.0,
        "tax_total": 19.0,
        "additional_charges": None,
        "discount_total": None,
    }


class FakeClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raw = self.outputs.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(raw)), finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )


def test_vision_request_sends_images_and_uses_strict_json_schema():
    client = FakeClient([_payload()])
    provider = OpenAICompatibleProvider(base_url="https://api.groq.com/openai/v1", api_key="test",
                                        model="qwen/qwen3.8-27b", client=client, sleep=lambda _: None)
    result = provider.extract_visual([b"jpeg-bytes"])
    request = client.calls[0]
    parts = request["messages"][1]["content"]
    assert len(parts) == 2 and parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert request["response_format"]["json_schema"]["strict"] is True
    assert request["temperature"] == 1.0 and request["top_p"] == 0.95
    assert json.loads(result.raw)["vendor_name"] == "Acme GmbH"


def test_vision_sends_one_page_per_request_and_merges_line_items():
    one = _payload(line_items=[{"description": "Part A", "quantity": 1, "unit_price": 50, "amount": 50}])
    two = _payload(line_items=[{"description": "Part B", "quantity": 1, "unit_price": 50, "amount": 50}])
    client = FakeClient([one, two, one, two])
    sleeps = []
    provider = OpenAICompatibleProvider(base_url="https://api.groq.com/openai/v1", api_key="test",
                                        model="qwen/qwen3.8-27b", client=client, sleep=sleeps.append)
    result = provider.extract_visual([b"a", b"b", b"c", b"d"])
    assert [len(c["messages"][1]["content"]) - 1 for c in client.calls] == [1, 1, 1, 1]
    assert sleeps == [60, 60, 60]
    assert len(json.loads(result.raw)["line_items"]) == 4
    assert result.usage["total_tokens"] == 60


def test_conflicting_scalar_values_are_withheld_not_guessed():
    merged = OpenAICompatibleProvider._merge_page_extractions([_payload(total=119), _payload(total=120)])
    assert merged["total"] is None


def test_pdf_pages_render_as_jpeg_bytes(tmp_path):
    import fitz
    path = tmp_path / "one-page.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "INVOICE TOTAL EUR 119.00")
    doc.save(path)
    doc.close()
    pages = render_pdf_pages(path)
    assert len(pages) == 1 and pages[0][:2] == b"\xff\xd8"


def test_pipeline_uses_vision_for_scanned_pdf(make_pipeline, workdir):
    from ap.extraction.base import ExtractionResponse
    from tests.conftest import truth

    class VisionOnlyProvider:
        name = "groq"
        model = "qwen/qwen3.8-27b"
        last_wait_ms = 0

        def __init__(self):
            self.page_count = 0

        def extract(self, text, feedback=None, *, source=""):
            raise AssertionError("Live vision path should not call text extraction")

        def extract_visual(self, pages, feedback=None, *, source=""):
            self.page_count = len(pages)
            return ExtractionResponse(raw=json.dumps(truth(workdir, "TC01")), usage={"total_tokens": 10})

    provider = VisionOnlyProvider()
    result = make_pipeline(provider, mode="live").process_file(
        workdir / "data" / "invoices" / "no_text_layer.pdf", use_cache=False)
    assert provider.page_count >= 1
    assert result.extracted is not None
    assert result.validation.confidence == "medium"
    assert result.label.value == "Needs review"


def test_rate_limit_delay_uses_retry_after_header():
    exc = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "7.5"}), body={})
    assert OpenAICompatibleProvider._rate_limit_delay(exc, 1) == 7.75


def test_rate_limit_delay_parses_token_reset_header():
    exc = SimpleNamespace(response=SimpleNamespace(headers={"x-ratelimit-reset-tokens": "1m2.5s"}), body={})
    assert OpenAICompatibleProvider._rate_limit_delay(exc, 1) == 62.75


def test_parse_duration_supports_long_reset_windows():
    assert OpenAICompatibleProvider._parse_duration("1d2h") == 93600


def test_provider_retries_429_using_retry_after(monkeypatch):
    import ap.extraction.openai_compatible as provider_module

    class FakeRateLimitError(Exception):
        def __init__(self):
            super().__init__("rate limited")
            self.response = SimpleNamespace(headers={"retry-after": "1"})

    class FlakyClient(FakeClient):
        def create(self, **kwargs):
            if not self.calls:
                self.calls.append(kwargs)
                raise FakeRateLimitError()
            return super().create(**kwargs)

    monkeypatch.setattr(provider_module.openai, "RateLimitError", FakeRateLimitError, raising=False)
    sleeps = []
    client = FlakyClient([_payload()])
    provider = OpenAICompatibleProvider(base_url="https://api.groq.com/openai/v1", api_key="test",
                                        model="qwen/qwen3.8-27b", client=client, sleep=sleeps.append)
    result = provider.extract_visual([b"jpeg-bytes"])

    assert json.loads(result.raw)["vendor_name"] == "Acme GmbH"
    assert len(client.calls) == 2
    assert sleeps == [1.25]
