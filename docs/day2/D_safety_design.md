# D. Human Approval, Fallbacks, Privacy and Permissions

> **Historical design document (Day 2).** Parts of it are superseded by later work (label anchoring, vendor-vs-PO check, number-format handling, void, run history). For how the system works now, read `docs/ARCHITECTURE.md`.


Governing rule: **the system fails safely.** When context is insufficient it says so and routes to a human. It never invents a value, and it never produces `Approve` unless every check has passed.

## 1. What is automated and what stays human

| Action | Automated | Human | Notes |
|---|---|---|---|
| Read fields from the invoice | Yes | Reviews | LLM step, validated by code |
| Compare to PO, check duplicates, apply tolerances | Yes | | Deterministic rules |
| Recommend a label with reasons | Yes | | Recommendation only |
| Draft vendor email or internal note | Yes | Reads, edits, sends | The system never sends anything |
| Confirm the decision (approve, hold, reject) | | **Yes** | `ap confirm`; the only action that writes the duplicate-check log |
| Pay an invoice | Never | Outside the system | Non-goal; no payment integration exists |
| Contact a vendor | Never | **Yes** | Drafts only |
| Change policy thresholds | | **Yes** | Edit `config/policy.yaml`, then update tests |
| Override a recommendation | | **Yes** | Confirm accepts any of the three decisions |

Escalation assumption from Day 1: exceptions above an assumed $5,000 go to the manager. v0 only displays this as a note; notification is Day 3.

## 2. When the system must ask for more information

| Situation | Behavior |
|---|---|
| No PO number on the invoice | Needs review with `PO_MISSING_ON_INVOICE`. Lists candidate POs (same vendor, total within tolerance) with the reason each was suggested. Never selects one itself |
| A critical field is null | Needs review with `FIELD_NOT_FOUND` naming the field |
| Invoice line cannot be matched to a PO line | Needs review with `LINE_NOT_ON_PO` |
| Currency differs from the PO | Needs review with `CURRENCY_MISMATCH`; no conversion |
| Possible duplicate | Needs review with a pointer to the matching record |

## 3. When the system must refuse to generate an output

| Condition | What is refused | What is produced instead |
|---|---|---|
| File is not a PDF, too large, or will not open | Any run | `ErrorResponse`; no run created |
| No text layer (scanned image) | Extraction and any vendor email | Needs review with `EXTRACTION_UNAVAILABLE`; internal note says the file needs manual reading (OCR is a non-goal) |
| Extraction invalid after one retry | Vendor email, and `Approve` | Needs review with `EXTRACTION_INVALID`; internal note lists which checks failed |
| LLM unavailable after retries | Vendor email, and `Approve` | Needs review with `EXTRACTION_UNAVAILABLE`; error populated |
| PO source unreadable | `Approve` | Needs review with `PO_SOURCE_UNAVAILABLE` |
| Final output fails schema or traceability validation | The whole result | `ErrorResponse` with `INTERNAL_ERROR`; nothing released |

Rule behind the refusals: **no unverified data is put into a message addressed to a vendor.**

## 4. Confidence and uncertainty

The LLM is not asked how confident it is, because self-reported confidence is unreliable. Confidence is derived from checks the system can verify:

| Level | Condition |
|---|---|
| high | First attempt valid; all extracted values grounded in the PDF text; line sums match the total |
| medium | Needed one corrective retry |
| low | A non-critical field could not be grounded |
| none | No usable extraction |

Only `high` can lead to `Approve`. `medium` and `low` always route to Needs review with the reason shown.

Unreadable or absent values are `null`, never estimated. TC10 specifically checks that a missing total stays `null`.

## 5. Retry and fallback behavior

| Failure | Retries | Backoff | Final fallback |
|---|---|---|---|
| HTTP 429 (rate limited) | Up to 3, honoring `retry-after` when present | Exponential with jitter | `EXTRACTION_UNAVAILABLE`, retryable error |
| HTTP 5xx or timeout | Up to 3 | Exponential with jitter | `EXTRACTION_UNAVAILABLE`, retryable error |
| HTTP 400 or 401 (bad request or key) | None | | Configuration error message; no retries burn quota |
| Output fails schema or validation | One corrective retry with the error text | None | `EXTRACTION_INVALID` |
| Cache hit | Not applicable | | Reuses prior extraction (logged as cached) |
| Client-side throttle | Waits before sending to stay under the tokens-per-minute limit | | Wait time recorded separately from latency |

Fallback chain: live LLM, then manual review. A secondary provider (Ollama) can be configured as an optional second hop once Day 3 testing shows it is worth the complexity. v0 does not silently switch providers; the provider used is always recorded.

## 6. Input and output validation

- **Input:** file exists, `.pdf`, size limit, opens as PDF, run registered with SHA-256.
- **Extraction:** wire schema, domain conversion, line arithmetic, sum check, grounding (see B, section 6).
- **Output:** `RunResult` validates against its schema; `label` is consistent with the findings (re-derived and compared); every number and identifier in the vendor email and internal note exists in the findings or the extracted data (so templates cannot drift from facts).

## 7. Prompt injection defense

1. **Architecture:** the LLM output is a data record. It has no field or channel through which it can set the label, skip a rule, or write a reason.
2. **Prompt:** invoice text is passed as quoted data; the instructions say to ignore any directives found inside it.
3. **Detection:** regex heuristics for phrases such as instructions to approve, skip or ignore checks, or text resembling system or assistant roles produce a `SUSPICIOUS_TEXT` finding that forces review.
4. **Grounding:** an injected value that does not appear in the visible text fails the grounding check.

TC12 tests all four together. This does not defend against an adversary who forges plausible-looking figures in the visible invoice; that falls under deep fraud detection, which is a non-goal.

## 8. Privacy and sensitive-data handling

- v0 data is **synthetic only**. No real invoices, names, bank details or personal data are used.
- Data minimization by design: the schema does not extract bank account numbers, tax IDs, addresses or contact people.
- Logs record hashes, codes and field names, not invoice text or amounts at info level.
- API keys live only in `.env` (git-ignored); logs and documentation never contain them.
- Before any real-data use: review the provider's data-retention terms, consider redaction before sending text to a hosted model, and consider a local model for sensitive invoices.

## 9. Permissions and least privilege

| Resource | v0 permission | Day 3 plan |
|---|---|---|
| PO data | Read-only | Google Sheet shared as Viewer with a service account |
| Processed-invoice log | Append only, via `confirm` | Same sheet or a separate one, Editor on that tab only |
| Run log | Append only | Same |
| LLM API | One key, inference only, no other scopes | Same |
| Network | Only the configured LLM endpoint | Plus the Sheets API and one notification webhook |
| Email | None (drafts are text on screen) | Still none; sending stays human |
| Payments or banking | None, no integration exists | Same |

## 10. Irreversible or sensitive actions

None are executed by the system. The only write that changes future behavior (adding to the duplicate-check log) requires an explicit human `confirm` command. Everything else is a recommendation or a draft.
