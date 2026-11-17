# Day 4 Report: Evaluate, Break and Harden

Data origin everywhere: **synthetic**. Extractor behaviour in sections 3 to 6: **simulated faults or a perfect extractor, never a real LLM**. No live Groq call, no baseline measurement and no proxy-user session has happened yet; those parts are prepared, not done, and are marked as such.

## 1. The question Day 4 asks

> Can you explain quality and failure across multiple conditions, not just one successful example?

Short answer, kept honest: **for the deterministic safety net around the model, yes, and with evidence. For the model itself, not yet.** Section 10 gives the reasoning.

## 2. What was possible here, and what was not

| Day 4 goal | Status | Why |
|---|---|---|
| Full test-set results | **Done for the code** (60 documents, 25 fault types, 3 code versions). **Not done for a live model** | The sandbox cannot reach Groq. The live harness is built and tested; you run it |
| Baseline comparison | **Tools ready, results `[MEASURE]`** | Baseline A needs a person with a stopwatch; Baseline B needs a model. `scripts/compare.py` builds the table from the files you fill in |
| Quality, latency, cost, manual-touch metrics | Quality and deterministic latency **measured**; model latency, tokens, cost and human time **not measured** | Same reason |
| At least three failure cases with root cause | **Done: seven** (`FAILURE_ANALYSIS.md`), plus seven process failures of my own | Found by fault injection, held-out testing and mutation checks |
| Retries, fallbacks, validation, confidence, human approval | **Done and evidenced**, see section 7 | |
| Before-and-after regression results | **Done** for three code versions on identical experiments | |
| Feedback from the target or proxy user | **Not available.** A usability review by me produced two changes (labelled as such) | Needs a real person |

## 3. The test set grew from 12 to 60 documents, plus deliberate breakage

| Set | What it is | Size |
|---|---|---|
| Base | The 12 Day 1 test cases | 12 documents |
| Robustness | Each base case again in 3 more forms: a different layout, a cluttered document (customer block, due date, bank details, contact lines), and European number and date format | 36 documents |
| Held-out | 12 richer documents (order date, delivery date, customer reference, remit-to name) **generated after the round-1 fixes and never used to design them** | 12 documents |
| Fault injection | 18 types of simulated extractor mistake (misread total, dropped line, shifted columns, wrong vendor, PO number as invoice number, wrong date, empty or truncated answer, service outage, and more) applied to every applicable document | 724 runs |
| Held-out faults | 7 further fault types applied to the held-out documents | 78 runs |
| First-attempt-only faults | The 724 runs repeated with faults on the first attempt only, to test the retry path | 724 runs |

Ground truth is exact because I generate the invoices. That is also the weakness (section 11).

## 4. Results: the same experiments on three versions of the code

Generated from the saved CSV files by `scripts/summarize_day4.py` (full tables in `docs/day4/evidence/regression_tables.md`).

| Experiment | Measure | Day 3 code | Round 1 | Round 2 |
|---|---|---|---|---|
| Fault matrix (724 runs) | Unsafe: approved wrongly, or approved on wrong data | **18** | 0 | **0** |
| | Unsafe runs that carried "high" confidence | 18 | 0 | 0 |
| | False alarms (clean invoice flagged for no reason) | 36 | 0 | **0** |
| Held-out faults (78 runs) | Unsafe | **16** | **11** | **0** |
| | False alarms | 0 | 0 | 0 |
| Perfect extractor, 48 documents | Handled exactly as expected | 39 / 48 | 48 / 48 | **48 / 48** |
| | European-format documents correct | 3 / 12 | 12 / 12 | 12 / 12 |
| Unit and regression tests | Passing | 181 | 181 | **232** |

Reading the table:

- **Confidence did not warn.** Every one of the 34 unsafe outcomes on the Day 3 code was reported with "high" confidence. Confidence here comes from grounding, retries and arithmetic; it cannot see a plausible value in the wrong place. The fix was new checks, not a better confidence label.
- **Round 1 did not generalize.** The middle column is the finding I value most: after round 1 everything I had tested was perfect, yet 11 held-out runs were still unsafe. Round 2 fixed the root cause (a value must sit next to the right label), and the held-out set went to 0. See `FAILURE_ANALYSIS.md`, A3.
- **Zero is not proof.** Round 2's zero is on faults and documents I designed. It means "the failures I could think of are covered", not "none exist".

Side effects worth knowing about: the held-out set shows 10 `UNDER_FLAG` runs (a duplicate or missing-PO case sent to review instead of hold) and 7 `OVER_FLAG` runs (review became hold). Both are safe directions; they cost reviewer time and slightly blur the difference between "review" and "hold".

## 5. Which safeguard does what (ablation)

| Safeguard removed | Unsafe runs (main / held-out) | What gets through |
|---|---|---|
| None | 0 / 0 | |
| Grounding in the document text | 8 / 0 | Hallucinated PO number, flipped currency |
| Arithmetic checks | 4 / 0 | Total copied from a line item |
| Label anchoring | 0 / 11 | Delivery date, order date or customer reference taken for the invoice date or number |
| Vendor-vs-PO check | 3 / 3 | Customer or remit-to name taken for the vendor |
| Cross-field checks | 0 / 0 | Nothing: redundant on this data |
| Confidence gate | 0 / 0 | Nothing: not needed on this data |

The last two rows are a limit on what I can claim: they have no demonstrated unique value on this test set.

## 6. Metrics: what was measured and what was not

| Metric (evaluation framework, E document) | Day 4 status |
|---|---|
| Decision accuracy, exception recall, false alarms, critical misses | Measured on the code (ground truth and mock modes: 60 of 60 correct; 0 unsafe). **Not measured for a live model** |
| Extraction accuracy (critical fields) | **Not measured.** Needs a live run. The harness reports it per field |
| Completeness | 0 errors in 802 fault runs; every result carries label, reasons and note |
| Rule compliance | Boundary tests for every tolerance, all passing |
| Unsupported facts in outputs | Automated traceability check on every generated email and note; 0 violations released |
| Latency | Deterministic pipeline only: median about 10 ms, 95th percentile 20 ms (robustness set) and 116 ms (fault matrix) on this machine. These vary run to run and **exclude the model call**, the likely dominant cost |
| Tokens and cost | **Not measured.** The harness records real token counts and computes a notional cost from the prices you supply |
| Human touch (manual-touch time) | **Not measured.** Needs a person (runbook step 4). On the synthetic set the review rate is fixed by the test mix (9 of 12 are exceptions), so it says nothing about a real workload |
| Reproducibility | Same input gives identical decision JSON (tested on 4 cases, Day 2) |

## 7. How failures are handled: the combination of mechanisms

| Condition | Mechanism | Evidence |
|---|---|---|
| Model service down, rate-limited, timing out | Retries with backoff and `Retry-After`; then a safe result: needs review, no vendor email | Provider tests; fault F16 in 48 documents: 0 unsafe |
| Malformed, truncated, empty or wrongly formatted output | Tolerant parsing of harmless quirks (code fence, US-style number strings); strict schema rejection of everything else; one corrective retry with the reason sent back; then review | F11 to F15: 0 unsafe, 0 false alarms |
| A plausible value that is not in the document | Grounding against the PDF text (numbers in both conventions, dates in many formats) | Ablation: 8 unsafe runs without it |
| Internally inconsistent numbers | Arithmetic: quantity x price = amount, lines sum to total | Ablation: 4 unsafe runs without it |
| A real value in the wrong place | Label anchoring and the vendor-vs-PO check | Ablation: 11 and 6 unsafe runs without them |
| Uncertainty that checks cannot resolve | Confidence: any retried or partly unverified reading cannot be approved | 432 first-attempt-only faults recovered by the retry; **all 432** were routed to a person |
| Anything irreversible | Human approval: the system only recommends; recording a decision is the only write that affects future checks; nothing is paid or sent | By design; tested |
| Injected instructions in the document | The model has no channel to influence the label; heuristics flag the wording | TC12 in every layout and variant |

**A trade-off you should decide about.** Any invoice that needed a retry goes to a person, even though the second answer passed every check. In the first-attempt-fault experiment there were 198 runs on clean invoices; 162 of them ended in review, and 123 of those 162 did so *only* because a retry had been needed. This is the cautious choice. With real data, measure the retry rate and the accuracy after a retry, then decide whether to relax it. Note also that in these tests the second attempt is correct *by construction*, so they prove the retry path works mechanically, not that a real model corrects itself.

## 8. Comparison with the baselines

`results/comparison.md` is generated by `scripts/compare.py`. Today every cell reads `[MEASURE]`, which is correct: nothing has been measured. After you complete runbook steps 1 to 5 it will show decisions correct, exceptions caught, false alarms, critical misses, hands-on minutes, invented facts and vendor message scores for manual, simple-prompt and system side by side.

## 9. Feedback from the proxy user

**None collected.** The test protocol (`docs/day3/PROXY_USER_TEST.md`) is ready and its results table is blank.

What I did instead, clearly labelled as an **expert review by me, not user feedback**: I walked through the six proxy-test tasks in the app and found two gaps.

| Gap I saw | Change | Test |
|---|---|---|
| After recording a decision there was no obvious way to start over | "Check another invoice" button that clears the screen | `test_check_another_invoice_resets_the_screen` |
| The demo-mode limit was explained only after pressing Check | The warning appears as soon as an unknown file is chosen | `test_demo_warning_rule` |

When you run the real session, record each observation here:

| Observation (what the person did or said) | Change made | Re-tested? |
|---|---|---|
| | | |

## 10. Answering the key question

**What I can explain, with evidence.** Across 60 document variants, 25 kinds of simulated extractor error, three versions of the code and a held-out round, I can say which situations the safety net catches, which layer catches each, what it costs in reviewer time, what slipped through before the fixes and why, and which of my own assumptions were wrong. The result is reproducible: the experiments are scripts, the gates are in the test suite (232 tests, mutation-checked), and the numbers in this report are generated from saved files.

**What I cannot yet explain.** How the real model behaves. I do not know its extraction accuracy, how often it makes any of the 25 mistakes, whether it self-corrects when asked to retry, how long a call takes, what it costs, or how long a person takes to review its output. I also cannot say whether real invoices contain failure modes I did not think of. Everything in the safety net is built to make those unknowns *safe* (a wrong reading ends in review, never approval) and *measurable* (the harness reports them), but they are not yet *measured*.

So the honest position is: quality and failure are explained for the system around the model, and the model-dependent half is a short, specific list of measurements to take (the runbook).

## 11. Limits of this evidence

- **I wrote the faults, the fixes and the documents.** The held-out round reduces this bias; it does not remove it, because I also designed the held-out set after seeing round 1's results.
- **Synthetic invoices are clean.** Real ones have scanning noise, odd labels, tax lines, multiple pages and languages. Label anchoring is skipped for unfamiliar wording and offers no protection there.
- **Simulated errors are not model errors.** The real distribution of mistakes is unknown; the ablation says which layer handles which kind, not how often each kind occurs.
- **Look-alike vendors:** the 0.95 similarity threshold was chosen by reasoning, not tuned on data.
- **Remaining non-goals:** scanned images, tax lines, currency conversion, multi-page invoices.

## 12. Contract and code changes made on Day 4

New finding code `VENDOR_MISMATCH`; `ValidationReport.repairs`; `validate()` now has per-safeguard switches used only for ablation; new modules `ap/names.py` and `ap/anchors.py`; tolerant number strings on the wire model (the JSON schema is unchanged); the web app gains "Check another invoice" and an early demo-mode warning. New tooling: `evalkit/` (faults, runner, matrix, metrics) and `scripts/` `stress_test.py`, `robustness.py`, `ablation.py`, `summarize_day4.py`, `evaluate.py`, `baseline_prompt.py`, `compare.py`.

## 13. AI collaboration log entries for Day 4

| Task delegated | How verified | Accepted, changed or rejected | Decision you own |
|---|---|---|---|
| Designed the fault catalogue, held-out round and ablation | Ran everything; confirmed the held-out round failed round 1 before fixing | Round-1 fixes judged too narrow; round 2 added | Which risks matter and which fixes to keep |
| Wrote the hardening and 51 new tests | Mutation-checked: 10 deliberate breaks, one initially survived and the test was redesigned | Seven defects of mine found and fixed (`FAILURE_ANALYSIS.md`, section C) | Accepting the review-on-retry trade-off |
| Wrote the live evaluation harness, baseline tools, comparison script | Exercised against a local stand-in; found it overclaimed "real model" and fixed it | Stand-in leftovers deleted | Running them with your key, and what to quote |
| Wrote this report | Every number traced to a saved file | Statements about the real model deliberately left out | What goes in the case study |

## 14. Handoff to Day 5

1. Run the runbook (`LIVE_EVALUATION_RUNBOOK.md`) and add real numbers to this report and to `FAILURE_ANALYSIS.md` section D.
2. Run the proxy-user session and fill section 9.
3. Day 5 packaging: README, runbook, demo script, case study and the 2-week adoption plan; this report's sections 4, 5, 7 and 10 are the raw material for the case study's "failures, changes, results, limitations".
