"""One-call smoke test of your configured LLM (run this yourself with your own key).

  python scripts/check_llm.py [data/invoices/TC03.pdf]

Reads LLM_* settings from .env, sends ONE extraction request, and reports: whether the provider accepted the strict
JSON schema, whether the answer validated and was grounded in the PDF text, token usage and latency.
Prints no secrets. Paste the output back into the chat.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ap.config import Policy, Settings                                   # noqa: E402
from ap.extraction.base import ProviderError, ProviderOutputInvalid      # noqa: E402
from ap.extraction.factory import build_provider                         # noqa: E402
from ap.pdf_text import extract_text                                     # noqa: E402
from ap.validation import validate                                       # noqa: E402


def main() -> int:
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/invoices/TC03.pdf")
    s = Settings.from_env()
    print(f"provider={s.provider} model={s.model} base_url={s.base_url} key_set={bool(s.api_key)} "
          f"reasoning_effort={s.reasoning_effort or '(none)'}")
    if not s.api_key:
        print("FAIL: LLM_API_KEY is not set (copy .env.example to .env and add your key)."); return 2
    text = extract_text(pdf)
    prov = build_provider(s, "live")
    t0 = time.perf_counter()
    try:
        r = prov.extract(text, source=pdf.stem)
    except ProviderError as e:
        print(f"FAIL: provider error [{e.code.value}] retryable={e.retryable}: {e}")
        print("Hint: 400 usually means the model name or the strict schema was rejected; 401 means the key is wrong."); return 1
    except ProviderOutputInvalid as e:
        print(f"FAIL: model answered but output unusable: {e}"); return 1
    ms = int((time.perf_counter() - t0) * 1000)
    print(f"call ok in {ms} ms, tokens={r.usage}, waited={prov.last_wait_ms} ms")
    o = validate(r.raw, text, Policy.load())
    print("schema + arithmetic + grounding:", "PASS" if o.passed else f"FAIL {o.issues}", "| ungrounded:", o.ungrounded)
    print("extracted JSON:"); print(json.dumps(json.loads(r.raw), indent=2))
    return 0 if o.passed else 1


if __name__ == "__main__":
    sys.exit(main())
