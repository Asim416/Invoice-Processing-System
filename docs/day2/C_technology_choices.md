# C. Model, Tools, Storage and Interface Selection

> **Historical design document (Day 2).** Parts of it are superseded by later work (label anchoring, vendor-vs-PO check, number-format handling, void, run history). For how the system works now, read `docs/ARCHITECTURE.md`.


Selection rule: free or open-source, few dependencies, demonstrable in the time available, and nothing that exists only to look impressive.

## 1. Summary

| Layer | Choice | Main alternative | Why the choice won |
|---|---|---|---|
| LLM provider | Groq, model `openai/gpt-oss-120b`, via an OpenAI-compatible adapter | Ollama (local) | Free tier, no hardware dependency, strict structured output. Ollama kept as fallback through the same adapter |
| Structured output | JSON schema with `strict: true`, plus Pydantic validation | Free-text JSON parsed with regex | Constrained decoding removes most format errors; Pydantic catches the rest |
| PDF text | `pdfplumber` | PyMuPDF | MIT-licensed, pure Python install, enough for text-layer PDFs. PyMuPDF has a more restrictive license that I would need to check before recommending |
| Validation and contracts | Pydantic v2 | `dataclasses` plus hand-written checks | Schema generation for the wire contract, clear errors, one source of truth |
| Rules | Plain Python with `Decimal`, thresholds in `config/policy.yaml` | A rules-engine library | Rules are a dozen comparisons; a library adds overhead and hides logic |
| Fuzzy matching | `difflib` (standard library) | `rapidfuzz` | No new dependency; only needed for PO candidate suggestions |
| Storage (v0) | CSV and JSON-lines files behind a `Storage` interface | SQLite | Priya works in spreadsheets, and Day 3 needs a Google Sheets adapter. The interface keeps the choice reversible |
| Interface (v0) | CLI with `argparse` | Streamlit now | Smallest thing that proves the flow end to end. Streamlit is Day 3 |
| Orchestration | Plain function pipeline | LangChain or similar | One LLM call does not need an orchestration framework |
| Logging | Standard `logging` with JSON formatter and `run_id` | A logging or tracing service | Free, local, no sensitive data in logs |
| Config and secrets | `.env` loaded with `python-dotenv`; `.env.example` committed | Hard-coded config | Required by the brief; keys never in code or logs |
| Test data | `reportlab` to build PDFs from structured records | Public invoice samples only | Exact ground truth. Public samples added later for layout variety |
| Tests | `pytest` | `unittest` | Less boilerplate, parameterized cases map to TC01 to TC12 |

## 2. LLM provider and model in detail

**Used for:** extracting invoice fields into the wire schema (the only AI step).

**Chosen:** Groq with `openai/gpt-oss-120b`, `response_format` of type `json_schema` with `strict: true`, low reasoning effort, temperature 0.

**Why suitable**
- Groq's structured-outputs documentation lists `gpt-oss-120b` among the models supporting strict mode (constrained decoding). `gpt-oss-20b` supports best-effort mode only.
- Free plan with no card required. Sample limits published for this model: 30 requests/min, 1,000 requests/day, 8,000 tokens/min, 200,000 tokens/day. These are organization-level and may differ on your account; the console Limits page is authoritative.
- OpenAI-compatible API, so the same adapter can talk to Ollama.
- Extraction is a reading task. A large model with constrained output is more reliable than a small one, and speed is not a concern at this volume.

**Token budget estimate (to be measured, not a result):** an invoice text of roughly 400 to 900 tokens, plus instructions and schema, plus output and reasoning, suggests about 1.5K to 3K tokens per call. 36 evaluation runs (12 cases x 3) would then use roughly 55K to 110K tokens against a 200K daily allowance. The 8K tokens/minute limit means about 3 to 5 calls per minute, so a full evaluation takes on the order of 10 minutes with throttling. Stage 2 logs real usage so these estimates get replaced by measurements.

**Alternatives considered**

| Alternative | Pros | Cons for this sprint |
|---|---|---|
| Ollama (local model) | No rate limits, data stays local, free | Depends on your hardware; small local models are typically less reliable at strict structured output; slower on CPU. Kept as a dev and fallback option |
| Other free-tier hosted APIs (for example Gemini) | Possibly larger free allowances | Different SDK and schema dialect; not researched in depth; adds a second integration to learn |
| Paid frontier APIs | Strong accuracy | Cost and key management for a hiring assessment; unnecessary for a reading task |

**Risks:** model IDs and limits change; the free tier is shared at organization level. Mitigation: model, base URL and limits are configuration; extraction results are cached by file hash, model and prompt version; mock mode needs no network.

**Privacy note:** v0 uses synthetic data only, so sending text to a hosted API carries no privacy cost. Real invoices would require reviewing the provider's data terms first.

## 3. Prompting approach

- One system prompt, versioned (`PROMPT_VERSION`), stored in the repo.
- The invoice text is passed inside delimiters and described as data, not instructions.
- The prompt states: extract only what is printed in the text; use `null` when a value is not present; do not calculate or infer values.
- No few-shot examples in v0 (keeps tokens low); added only if Day 4 failures justify it.
- No chain-of-thought requested; reasoning effort set low.
- The prompt version is recorded in every `RunResult` and in the cache key.

## 4. Extraction modes

| Mode | Source of extracted fields | Used for | Labeled in output |
|---|---|---|---|
| `live` | Configured LLM endpoint | Real extraction evaluation | `extraction_mode: live`, provider, model |
| `mock` | Deterministic fixture file per invoice | Development without a key or network; demonstrating the pipeline | `extraction_mode: mock` |
| `ground_truth` | The test case's known correct fields | Testing rules, decisions and templates in isolation (12-case rules test) | `extraction_mode: ground_truth` |

Only `live` results may be described as model output.

## 5. Storage

| Data | Store | Notes |
|---|---|---|
| POs | `data/pos.csv` and `data/po_lines.csv` | Synthetic; read-only to the pipeline |
| Confirmed invoices | `data/processed_invoices.csv` | Written only by `confirm`; duplicate-check source |
| Run audit log | `logs/runs.jsonl` | One `RunResult` per line |
| Extraction cache | `cache/extractions/*.json` | Key: SHA-256 + model + prompt version |

All access via a `Storage` interface; Day 3 adds a Google Sheets adapter behind the same interface.

## 6. Logging and monitoring

- JSON log lines with `run_id`, step name, duration, outcome and finding or error codes.
- Never logged: invoice text, extracted vendor or amounts at info level, API keys, request bodies.
- Per-run metrics recorded in `RunResult`: timings by stage, token usage, validation attempts.
- "Monitoring" in v0 means the run log plus the evaluation summary; no external service.

## 7. Configuration and secrets

`.env.example` (committed):

```
# Provider: groq or ollama
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=your-key-here
LLM_MODEL=openai/gpt-oss-120b
LLM_REASONING_EFFORT=low
LLM_TIMEOUT_SECONDS=30
LLM_MAX_TOKENS=1500
LLM_TOKENS_PER_MINUTE=6000
EXTRACTION_MODE=mock
MAX_FILE_MB=10
```

For Ollama the same variables change to `LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://localhost:11434/v1`, a placeholder key, and the locally pulled model name. Whether Ollama's OpenAI-compatible endpoint honors the same JSON-schema `response_format` is to be verified on your machine when you test it; the pipeline's own validation does not depend on it.

`.env` is in `.gitignore`. The default `EXTRACTION_MODE=mock` means a fresh clone runs without any key.

## 8. Dependencies (v0)

`pydantic`, `pdfplumber`, `reportlab` (data generation), `openai` (client for OpenAI-compatible endpoints), `python-dotenv`, `pyyaml`, `pytest`. No framework, no database server, no paid service.
