# Day 2, Stage 1: Requirements Review, Gaps and Risks

Status: Stage 1 complete (design documents A to E). Nothing is implemented yet. Stage 2 builds the v0.

## 1. Requirements carried over from Day 1

| Item | Established on Day 1 |
|---|---|
| Workflow | Supplier invoice vs purchase order (PO) matching and exception handling |
| User | Priya, fictional sole finance person at a 30-person company, about 40 invoices/week (assumed), non-technical. No real user was interviewed |
| Job-to-be-done | Know quickly whether an invoice is safe to pay and, if not, why and what to tell the vendor |
| Bottleneck | Checking each invoice against its PO and writing up exceptions |
| Decision labels | Approve; Needs review; Reject (hold). The system recommends, a human decides |
| Policy | Total within 1% of PO; billed quantity not above PO quantity; unit price within 1%; PO exists and is open; currency equals PO currency; exact duplicate = same vendor and normalized invoice number already in the log; possible duplicate = same vendor, total and date with a different number |
| Targets (hypotheses) | Decision accuracy at least 11 of 12; extraction at least 95% on 5 critical fields; 0 critical misses; 0 false alarms on clean invoices; at most 2 min hands-on per invoice or 60% below baseline; at most 30 s latency; at most $0.10 per invoice; 0 unsupported facts in emails |
| Hard gates | Approving an exact duplicate; approving an over-tolerance amount or quantity; following instructions embedded in an invoice; inventing a value for an unreadable field |
| Non-goals | Payments, three-way matching, deep fraud detection, currency conversion, tax rules, handwritten scans, multi-user or ERP, learning over time, replacing human approval |
| Tests | TC01 to TC12 (3 clean, 9 exception cases) |
| v1 scope (Day 5) | Upload one invoice, extract, match with code, check duplicates, decide, draft output, require human confirmation, log every run |

## 2. Honest project state

| Exists | Does not exist yet |
|---|---|
| Day 1 package document; design tracker spreadsheet; these Stage 1 documents | Repository; generated invoices; PO data; processed-invoice log; `expected_results.csv`; any measured baseline (all `[MEASURE]`); a Groq key in my environment |

No baseline figure is quoted anywhere in the Day 2 documents. Baseline columns stay `[MEASURE]` until you run Baselines A and B.

## 3. Critical gaps and technical risks

| # | Gap or risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **My sandbox cannot reach the Groq API.** Its network allowlist does not include it | I cannot execute live extraction myself. I can run mock mode, ground-truth mode, the rules engine and the tests | Live runs are done by you with a documented command; you paste the output back. Nothing mock-produced is ever labeled live |
| 2 | **Groq free-tier limits are tight on tokens.** Published sample limits for the candidate model: 30 requests/min, 1,000 requests/day, 8,000 tokens/min, 200,000 tokens/day (verify on your console Limits page) | A 12-case x 3-run evaluation could take most of a day's token budget if prompts are large or retried often | Client-side throttle; extraction cache keyed by file hash and prompt version; `--no-cache` for evaluation; small prompt; low reasoning effort; mock mode for development |
| 3 | Model IDs and free-tier limits change | A hard-coded model could disappear | Model ID, base URL and limits live in config, not code |
| 4 | Strict structured output guarantees valid JSON shape, not correct values | The model can still misread a number | Grounding check: every extracted value must appear in the PDF text |
| 5 | **Circular ground truth.** I write the rules and I generate the invoices | Results may look better than real-world performance | State it in the case study; include at least 2 layouts and one adversarial case; add layouts on Day 4 |
| 6 | Synthetic layouts may be too easy for the LLM | Then a regex parser would work and AI would be unjustified | Keep the optional regex-parser comparator in the Day 4 plan |
| 7 | Grounding of dates and currency symbols is approximate | False "ungrounded" flags on valid dates | Component-based date check; documented limitation; failures route to review, never to approval |
| 8 | Duplicate checks against a log you re-run against | Re-processing a file in evaluation would flag it as a duplicate of itself | The processed-invoice log is written only by a human `confirm` step; evaluation uses an isolated copy of the seeded log |
| 9 | Tracker measures decision accuracy per run; Day 1 states "11 of 12" | Ambiguity | E document defines both: run-level (gated) and case-level stability (reported) |

## 4. Decisions I added beyond Day 1 (please confirm or change)

1. **LINE_NOT_ON_PO (Needs review).** Day 1 requires per-line quantity and price checks, which implies matching invoice lines to PO lines. A line that cannot be matched by normalized description goes to review rather than being guessed.
2. **Human `confirm` step in v0.** `process` never writes to the processed-invoice log. A separate `confirm <run_id> --decision ...` command does. This is the concrete human approval point and prevents duplicate-against-itself problems.
3. **No vendor-name mismatch rule.** Vendor on invoice vs vendor on PO is not in the Day 1 policy and is treated as fraud-adjacent scope. Open question below.
4. **The LLM returns no confidence score.** Self-reported confidence is unreliable. Confidence is derived from deterministic signals (grounding, retries, sum checks).
5. **Wire schema is separate from domain models.** The LLM schema uses plain JSON numbers and strings; Decimal money and date types are applied in code.

## 5. LLM provider decision

**Primary: Groq, model `openai/gpt-oss-120b`, strict JSON-schema output, low reasoning effort.**
**Offline and dev fallback: Ollama via the same OpenAI-compatible adapter.**

Why Groq over Ollama as primary:
- Free tier with no card required, and OpenAI-compatible API.
- Groq's structured-output docs list `gpt-oss-120b` under strict mode (constrained decoding); `gpt-oss-20b` is best-effort only.
- It runs without depending on your laptop's hardware, which I do not know.
- Fast enough to keep latency far under the 30 s target.

Why keep Ollama: no rate limits and no data leaving the machine, which is useful for development iterations and for the "LLM unavailable" fallback story. The cost is hardware dependence and typically weaker structured-output reliability from small local models, which is a Day 4 comparison opportunity.

Model name, base URL and limits are configuration only, so switching costs one line.

Sources: Groq rate-limits and structured-outputs documentation (console.groq.com/docs/rate-limits, console.groq.com/docs/structured-outputs). Sample limits were read through a third-party summary (benchlm.ai/free-tier/groq, read 2026-09-14); the authoritative numbers are on your Groq console Limits page.

## 6. Open questions for you

1. Do you have (or will you create) a free Groq account and API key? You will store it only in your local `.env`.
2. Optional: what laptop do you have (RAM, GPU)? That decides whether an Ollama dev loop is realistic.
3. Confirm decisions 1 to 5 in section 4, especially the vendor-mismatch exclusion.
4. Go-ahead for Stage 2 (implementation).

## 7. Stage plan

- Stage 1 (this): documents A to E.
- Stage 2: repository, synthetic data generator, v0 pipeline, unit tests.
- Stage 3: run TC03 end to end (mock here, live by you), run all 12 cases through the rules path with ground-truth extraction, document defects, final Day 2 report.
