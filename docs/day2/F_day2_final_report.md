# Day 2 Final Report: System Design and v0

Data origin everywhere below: **synthetic**. Extraction modes are always stated. **No live LLM call has been made by me** (my sandbox cannot reach Groq); the live path was exercised only against a local stub server, which is not a model.

## 1. What was designed

Documents A to E in this folder: architecture and data flow (A), data contracts (B), technology choices (C), safety design (D), evaluation framework (E), plus the Stage 1 summary with gaps and risks (00).

## 2. Final architecture and technology decisions

AI reads the invoice; code decides. One LLM call (field extraction into a strict JSON schema). Everything after it is deterministic Python: validation (schema, arithmetic, grounding in the PDF text), rules (PO lookup, tolerances, quantities, unit prices, currency, duplicates), decision, and template-based email and note. A human `confirm` step is the only write to the duplicate-check log.

Stack: Python, Pydantic v2, pdfplumber, an OpenAI-compatible adapter (Groq `openai/gpt-oss-120b` configured, Ollama possible), CSV and JSONL storage behind a `Storage` interface, argparse CLI, pytest, reportlab for synthetic data.

## 3. Important trade-offs

| Decision | Gain | Cost |
|---|---|---|
| LLM only extracts; no LLM wording | Zero invented facts; testable rules; structural injection defence | Emails read a little formulaic |
| Grounding check on every extracted value | Catches invented or misread values | Approximate for dates and currency; may over-route to review |
| Anything uncertain goes to Needs review | Safe | More human reviews than a looser system would produce |
| CSV storage, CLI only | Fast to build, trivially portable | Not what Priya will use; Day 3 adds UI and Sheets |
| Only over-billing is an exception (under-billing is info) | Matches partial deliveries | Under-billing beyond tolerance is not flagged |
| Mock and ground-truth modes | Whole pipeline runnable and testable offline | Passing them proves the code path, not extraction quality |

## 4. What was actually implemented

- `ap/` package: schemas, config, PDF text, injection scan, extraction layer (interface, OpenAI-compatible provider with retries, backoff, `retry-after` handling and a tokens-per-minute throttle, mock provider), validation, rules, decision, templates with a traceability check, storage, pipeline, CLI.
- `scripts/generate_data.py` (12 synthetic invoice PDFs in 3 layouts, 12 POs, seeded log, ground truth, `expected_results.csv`, a no-text PDF), `run_cases.py`, `check_llm.py` (for you to run), `stub_llm_server.py`.
- 122 automated tests.
- Documentation: README, `.env.example`, `config/policy.yaml`.

## 5. Evidence

All files are in `docs/day2/evidence/`.

| Evidence | Mode | Result |
|---|---|---|
| `pytest_full_output.txt` | n/a | 122 passed |
| `cases_ground_truth.txt` | ground_truth (known-correct extraction fed in) | 12 of 12 labels correct, 12 of 12 required finding codes present |
| `cases_mock.txt` | mock (fixture extraction, real PDF text, validation and grounding) | 12 of 12 labels correct, 12 of 12 codes present |
| `TC03_mock_summary.txt`, `TC03_mock_run.json` | mock | TC03 end to end: Needs review, two findings, vendor email drafted |
| `human_step_1..4_*.txt` | mock | Process, confirm, re-submit is an exact duplicate and is held, confirming twice is refused |
| `error_unsupported_file.txt`, `no_text_layer_result.txt` | mock | Defined error response; no-text PDF routed to review with no LLM call |
| Local stub runs (shown in chat, not stored) | live path, **stub server** | Strict JSON-schema request and bearer header received; 429 retried twice then succeeded; HTTP 500 on every call degraded to Needs review; missing key gave a clear error with exit code 2 |

**How to read the 12 of 12.** Ground truth, rules and invoices come from one author, and mock extraction is a fixture. The result shows the deterministic code, validation and pipeline behave as specified. It says nothing about how well an LLM will extract fields.

### Mutation check

To confirm the tests are not vacuous I deliberately broke the code five ways (tolerance off by one, approve despite low confidence, grounding disabled, injection scan disabled, duplicate check ignoring vendor). The suite failed for each; the first injection-scan attempt was a flawed mutation (it changed nothing) and was redone properly.

### Defects found during Stage 3 and fixed

1. **Date grounding too loose:** an invented date passed because stray digits matched. Now a full recognizable date format must appear in the text. Regression test added.
2. **Traceability check broke the fail-safe path:** a provider error message containing a digit (for example "after 3 attempts") blocked the result as INTERNAL_ERROR instead of Needs review. Diagnostics are now allowed in the internal note only; the vendor email is still checked against invoice facts. Regression test added.
3. **`retry-after: 0` treated as absent:** fixed; very long hints capped at 60 s. Tests added.
4. **Log handler held a stale stderr:** it now resolves the current stderr, which also made two log-related tests meaningful (they had passed vacuously).
5. **Quantity formatting:** integer quantities were serialized as `50.0`; now `50`.

### Difference between design example and actual TC03 output

Same label, same two findings, identical finding messages. Differences: email subject ("clarification needed" instead of "does not match PO-1023"), intro and closing wording, order of the two bullets, and money shown with two decimals. All are template choices.

## 6. Input and output examples

Input `data/invoices/TC03.pdf` (synthetic, layout A). Output in `evidence/TC03_mock_summary.txt` and `evidence/TC03_mock_run.json`:

> RESULT: NEEDS REVIEW. UNIT_PRICE_MISMATCH: Line 'Laptop 15 inch': unit price 850.00 vs PO 800.00 (6.25% higher). AMOUNT_OVER_TOLERANCE: Invoice total 47,500.00 USD exceeds PO total 45,000.00 USD by 2,500.00 (5.56%). Vendor email drafted, not sent. Human confirmation required.

## 7. Evaluation rubric status (document E)

| Metric (E, section 3) | Status after Day 2 |
|---|---|
| 3 Exception recall, 4 False alarms, 5 gates 1 to 3 | Checked in ground_truth and mock modes only (all pass); live status unknown |
| 5 gate 4 (no invented value) | Covered by test: a model that returns an unprinted total is rejected by grounding and ends in Needs review |
| 8 Completeness, 9 Rule compliance, 10 Unsupported facts, 14 Error handling, 15 Reproducibility | Covered by automated tests (all pass) |
| 1 Decision accuracy, 6 Extraction accuracy, 11 Latency, 12 Cost, 13 Human touch | **Not measured.** Need live runs (Day 4) and your baselines |
| Baselines A and B | Still `[MEASURE]`. Nothing has been measured or claimed |

## 8. Known limitations and unresolved issues

**Unverified (needs you):**
- A real Groq call. Unknown: whether Groq accepts the strict schema with null unions, whether the `reasoning_effort` parameter is accepted as sent, current model availability, real token use, real latency, and whether the free-tier limits match the estimates. `python scripts/check_llm.py` answers all of these in one call.

**Design limits:**
- Text-layer PDFs only; no tax lines; one currency per invoice; under-billing is not an exception; repeated PO line descriptions match the first line; date and currency grounding are format-based approximations; the vendor-name mismatch rule is deliberately absent (open question from Stage 1).
- Synthetic invoices are cleaner than real ones, and the same author wrote data and rules (circular ground truth).
- Fuzzy vendor matching was not needed: vendors are compared after normalization, so `difflib` from the plan was not used.
- The Stage 1 confirmations (LINE_NOT_ON_PO, confirm step, no vendor-mismatch rule, no self-reported confidence) were implemented as proposed; you did not object.

## 9. Files

Created: everything under `ap/`, `scripts/`, `tests/`, `config/`, `templates/`, `data/` (generated), `docs/day2/` (00, A to F, `evidence/`), `README.md`, `requirements.txt`, `.env.example`, `.gitignore`, `results/*.csv`.
The Day 1 package document and the design tracker spreadsheet were not modified.

## 10. What Day 3 needs

1. **You:** run `python scripts/check_llm.py` with your Groq key and paste the output back. Fix anything it reveals before building more.
2. **You:** run Baselines A and B on the 12 cases (Day 1, section 5) so the comparison is real.
3. Streamlit interface for a non-developer, including a clear confirm button.
4. Two real integrations: Google Sheets adapter for POs and logs, plus a manager notification (Slack webhook or email).
5. A proxy user running it without you present, with their feedback recorded.
6. Add a second and third real-world layout, ideally from a public dataset, so extraction is genuinely tested.

## 11. AI collaboration log entries for Day 2 (add to the log)

| Task delegated | How verified | Accepted, changed or rejected | Decision you owned |
|---|---|---|---|
| Drafted the prompt tailoring for Day 2 | Read against the brief | Accepted with provider choice filled in | Choosing Groq |
| Designed architecture, contracts, safety, evaluation (A to E) | Executed the schema code; arithmetic-checked the example | Three finding codes added during the build | Confirming Stage 1 decisions |
| Wrote the v0 code, data generator and 122 tests | Ran everything; mutation-tested the suite | Five defects found by testing and fixed; one flawed mutation redone | Go-ahead for implementation |
| Claimed results | Labeled each result with its mode | Nothing described as live LLM output | What to claim in the case study |

## 12. Can this design become a repeatable system rather than a one-time generation?

**Partly proven, partly not.**

What the implementation and evidence show:
- The deterministic core is repeatable: running the same invoice twice gives identical decision JSON (tested on TC01, TC03, TC05 and TC12), and all 12 cases give the specified labels in two modes.
- The process is separated from the people running it: configuration and secrets are in `.env` and `policy.yaml`, state is in files behind an interface, every run is logged, a human step guards the duplicate log, and the tests (122, mutation-checked) catch regressions.
- Failure handling is designed and exercised: an unavailable LLM, malformed output, an invented value, a missing PO source, bad files and a missing key each end in a defined, safe result, never an Approve.

What it does not yet show:
- That live extraction is repeatable. An LLM is nondeterministic, and I have not run one. The design contains that risk (strict schema, grounding, one retry, fail to review), but how often it triggers is unknown until live runs on Day 4.
- That it works on real-world invoices, or for a real user.

So the design is a repeatable system in the parts that must be, and it has been built so that the one non-repeatable part can be measured and constrained. Whether that part performs well is the main open question, and the first step toward answering it is your `check_llm.py` run.
