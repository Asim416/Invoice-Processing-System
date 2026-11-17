# Developer Guide: understand, change, extend

Read `docs/ARCHITECTURE.md` first (10 minutes). This guide is about changing the code without breaking what is already proven.

## 1. Rules that must never be broken

1. **The model never decides.** It returns fields. Labels, reasons and emails come from code and templates. If you ever feel tempted to let the model "explain" or "decide", read `docs/day4/FAILURE_ANALYSIS.md` first.
2. **Approve must be earned.** `ap/decision.py` returns Approve only when there are no block or review findings, and the extraction validated with high confidence. Every new failure path must end in Needs review or Reject (hold).
3. **Fail safe, not silent.** A new dependency (a service, a file) that can fail needs a plain-language message and a safe result, not a stack trace.
4. **No invented facts in output.** Any number in a generated email or note must appear in verified facts (`ap/templates.py: untraceable_numbers` enforces this and blocks the result).
5. **The human step is the only write that changes future behaviour** (`confirm` writes the duplicate-check log).
6. **No secrets in code, logs, error messages or the packaged repo.** There are tests for this; keep them passing.
7. **Never describe demo (mock) output as AI output.** Every result records its `extraction_mode`.

## 2. Setting up and running the tests

```
pip install -r requirements.txt
python scripts/generate_data.py --stress --holdout
python -m pytest tests -q          # about a minute; needs no keys, network or accounts
```

Python 3.10 or newer. **Avoid syntax that only works on 3.12** (for example reusing the same quote character inside an f-string
expression). A scan for it is easy: `grep -rn` your diff, and the CI matrix runs 3.10, 3.11 and 3.12.

## 3. Map of the code

| Area | Files | One-line purpose |
|---|---|---|
| Contracts | `ap/schemas.py` | Every data shape: model output, domain objects, findings, errors, the run result |
| Reading | `ap/pdf_text.py`, `ap/extraction/` | PDF text; the only AI call (`openai_compatible.py`), a mock, the prompt |
| Checking | `ap/validation.py`, `ap/anchors.py`, `ap/names.py` | Schema, arithmetic, grounding, label anchoring, vendor names |
| Deciding | `ap/rules.py`, `ap/decision.py`, `config/policy.yaml` | Matching rules and the label |
| Saying | `ap/templates.py`, `templates/`, `ap/friendly.py` | Emails, notes, plain-language text for users |
| Doing | `ap/pipeline.py` | Orchestration only |
| Keeping | `ap/storage.py`, `ap/storage_sheets.py` | CSV and Google Sheets behind one interface |
| Telling | `ap/notify.py` | Slack, console, off |
| Using | `app.py`, `ap/ui_logic.py`, `ap/cli.py` | Web app (no logic of its own), command line |
| Operating | `ap/doctor.py`, `ap/adoption.py`, `scripts/` | Setup check, usage metrics, evaluation tools |
| Proving | `evalkit/`, `tests/`, `scripts/stress_test.py` and friends | Fault injection, metrics, regression gates |

## 4. Add a new matching rule (worked example)

Example: *flag invoices dated more than 90 days before the check*.

1. **Contract.** Add `STALE_INVOICE = "STALE_INVOICE"` to `FindingCode` in `ap/schemas.py`.
2. **Rule.** In `ap/rules.py: evaluate`, add a `Finding(code=..., severity=Severity.REVIEW, message=..., evidence={...})`. Build the message from evidence with `ap/fmt.py` helpers. Put any threshold in `config/policy.yaml` and `ap/config.py: Policy`, not in the code.
3. **Plain language.** Add an entry to `FINDINGS` in `ap/friendly.py` (title, meaning, next step). A test fails until you do (`test_every_finding_and_error_code_has_friendly_text`).
4. **Vendor email.** Decide whether the finding is something to tell the vendor. If yes, add a line to `VENDOR_BULLETS` in `ap/templates.py`; if not, leave it out (internal-only findings are the default).
5. **Tests.** Unit tests at the boundary (exactly at the limit, just over, just under) in `tests/test_rules.py` style. If the check could wrongly flag a good invoice, add a clean case.
6. **System tests.** Add a case to `scripts/generate_data.py` (`CASES`) with its expected label and codes; regenerate data; run the gates (section 6).
7. **Docs.** Update `docs/ARCHITECTURE.md` and, if users will see it, `docs/day3/USER_GUIDE.md`.

## 5. Turn a real failure into a test (the most valuable thing you can do)

When a real invoice is mishandled:

1. Reproduce it without the real document if it contains private data: write an equivalent synthetic invoice in `scripts/generate_data.py`, or build the text and extraction by hand in a unit test (see `tests/test_day4_hardening.py`).
2. Write the test first and watch it fail.
3. Find the root cause by asking *why did no safeguard catch this?* (one of: schema, arithmetic, grounding, anchoring, vendor, rules, or none of them). Fix the cause, not the example. Round 1 of the Day 4 hardening fixed examples and missed the cause; a held-out set exposed it.
4. Check the fix on cases you did not use to design it.
5. Record it in `docs/day4/FAILURE_ANALYSIS.md` section D.

## 6. The regression gates (run before every merge)

```
python -m pytest tests -q               # includes the whole fault matrix as pass/fail gates
python scripts/robustness.py            # every document variant handled as expected
python scripts/stress_test.py           # unsafe outcomes must be 0
python scripts/stress_test.py --holdout # unsafe outcomes must be 0
python scripts/ablation.py              # sanity: each safeguard still has a job
```

A change that makes any unsafe count non-zero is not mergeable, however good it looks elsewhere.

## 7. Add a fault to the fault catalogue

In `evalkit/faults.py`: write a function `(ground_truth, ctx) -> dict | str | Exception | None` (None means "not applicable to this
document"), register it as a `Fault(...)` (set `benign=True` only if the content stays correct), and add it to `FAULTS` or `HOLDOUT_FAULTS`.
`test_gate_every_fault_is_actually_exercised` fails if a registered fault never runs. Keep a held-out list: a fault you
designed a fix for is no longer a fair test of that fix.

## 8. Change the AI model, prompt or provider

- Model, base URL and limits are configuration (`.env`), so another OpenAI-compatible provider needs no code change.
- The prompt is `SYSTEM_PROMPT` in `ap/extraction/base.py`; bump `PROMPT_VERSION` in `ap/schemas.py` when you change it (it is part of the cache key).
- After any change: `python scripts/check_llm.py`, then `python scripts/evaluate.py --mode live --runs 3`, and compare with the previous run. Strict JSON-schema support differs between providers; the pipeline's own validation does not depend on it.

## 9. Add a storage backend or notifier

Implement the `Storage` protocol in `ap/storage.py` (or `Notifier` in `ap/notify.py`), add it to `ap/services.py`, and copy the
fake-based tests in `tests/test_sheets.py` or `tests/test_notify_ui.py`. Requirements that tests will enforce: retries with
backoff, friendly errors, no secrets in messages, append-only writes for history.

## 10. Pitfalls we hit (so you do not)

- A blanket text replace changed more than intended (an enum value landed in two classes; a function name rewrote its own definition). Review diffs, and prefer targeted edits.
- A test that passes even with the safeguard deleted is worthless. Break the code on purpose (mutation check) once for any safeguard you add.
- Do not put the web interface's logic in `app.py`; keep it in `ap/ui_logic.py` where it can be tested.
- `ap/validation.py: validate()` takes per-safeguard switches for the ablation. Production code must call it with all safeguards on.
- Mock and ground-truth modes test code paths, not AI quality; never report them as model results.

## 11. Definition of done

- [ ] Unit tests and, if behaviour changed, a regression test that fails without the change
- [ ] All gates in section 6 pass; unsafe outcomes are 0
- [ ] A mutation check for any new safeguard (delete it; a test must fail)
- [ ] Plain-language text for any new user-visible finding or error
- [ ] No secret, no invoice text, no personal data in logs, errors or fixtures
- [ ] Docs updated (architecture, user guide, operator runbook as relevant)
- [ ] Python 3.10 compatible
