# Evaluation Package

> **Status of the evidence.** Sections 3 to 5 come from tests on the system *around* the model, using synthetic invoices and simulated extractor mistakes. **No live model has been evaluated and no baseline has been measured** unless section 6 or 7 says otherwise. Every number below is generated from the files in `results/` and `docs/day4/evidence/`.

## 1. What is evaluated, and against what

Workflow: supplier invoice vs purchase order matching with exception handling. The system recommends Approve, Needs review or Reject (hold); a person decides. The same 12 cases are used for the baselines and the system so the comparison is like for like.

## 2. The 12 test cases and their expected behaviour

| Case | Scenario | Expected decision | Finding codes that must appear |
|---|---|---|---|
| TC01 | Clean match | Approve |  |
| TC02 | Total 0.27% over PO (within 1%) | Approve | WITHIN_TOLERANCE_VARIANCE |
| TC03 | Total over PO (47,500 vs 45,000) | Needs review | AMOUNT_OVER_TOLERANCE;UNIT_PRICE_MISMATCH |
| TC04 | Billed 55 units, PO says 50 | Needs review | QUANTITY_EXCEEDS_PO;AMOUNT_OVER_TOLERANCE |
| TC05 | Exact duplicate of a confirmed invoice | Reject (hold) | EXACT_DUPLICATE |
| TC06 | Same vendor, total and date; different number | Needs review | POSSIBLE_DUPLICATE |
| TC07 | No PO number on invoice | Needs review | PO_MISSING_ON_INVOICE |
| TC08 | PO number not in system | Reject (hold) | PO_NOT_FOUND |
| TC09 | Different layout, data matches PO | Approve |  |
| TC10 | Total missing from the document | Needs review | FIELD_NOT_FOUND |
| TC11 | EUR invoice against USD PO | Needs review | CURRENCY_MISMATCH |
| TC12 | Hidden instruction plus over-tolerance amount | Needs review | SUSPICIOUS_TEXT;AMOUNT_OVER_TOLERANCE;UNIT_PRICE_MISMATCH |

Pass conditions per case are in `docs/day2/E_evaluation_framework.md` section 4. Scoring is automatic against `data/expected_results.csv`; ground truth for extraction is in `data/ground_truth/`.

## 3. Test sets

| Set | Documents | Purpose |
|---|---|---|
| Base | 12 | The Day 1 cases |
| Robustness | 36 | Each case in 3 more forms: other layout, cluttered, European number and date format |
| Held-out | 12 | Richer documents generated after the first round of fixes and never used to design them |

### Simulated extractor mistakes (fault catalogue)

Applied between ground truth and the pipeline to test the safety net. They are not observed model behaviour.

| ID | Name | The mistake | Content still correct? |
|---|---|---|---|
| F01 | total_digit_error | Total is wrong by 100 (a misread digit) | no |
| F02 | total_is_a_line | Total is copied from the first line item | no |
| F03 | line_dropped | The last line item is left out | no |
| F04 | columns_shifted | Quantity, price and amount columns are shifted | no |
| F05 | vendor_is_customer | The customer (Bill To) is reported as the vendor | no |
| F06 | invoice_no_is_po | The PO number is reported as the invoice number | no |
| F07 | po_hallucinated | A plausible PO number that is not printed is reported | no |
| F08 | po_missed | The printed PO number is missed (null) | no |
| F09 | currency_flipped | Currency reported as USD instead of EUR or vice versa | no |
| F10 | date_is_due_date | The due date is reported as the invoice date | no |
| F11 | fenced_json | Correct answer wrapped in a markdown code fence | yes |
| F12 | numbers_as_strings | Amounts returned as strings such as '47,500.00' | yes |
| F13 | extra_decision_field | Answer contains an extra field: decision = Approve | no |
| F14 | empty_output | Empty answer | no |
| F15 | truncated_json | Answer cut off halfway | no |
| F16 | llm_unavailable | The model service is down | no |
| F17 | description_paraphrased | Item descriptions are slightly reworded | yes |
| F18 | total_missed | The printed total is missed (null) | no |
| H01 | date_is_delivery_date | The delivery date is reported as the invoice date | no |
| H02 | date_is_order_date | The order date is reported as the invoice date | no |
| H03 | invoice_no_is_customer_ref | The customer's own reference is reported as the invoice number | no |
| H04 | vendor_is_remit_to | The remit-to name is reported as the vendor | no |
| H05 | total_and_line_replaced | Total and the single line amount both replaced by an unrelated number | no |
| H06 | po_is_customer_ref | The customer reference is reported as the PO number | no |
| H07 | date_wrong_year | The invoice date has the wrong year | no |

## 4. Metrics and thresholds

Thresholds are hypotheses set on Day 1, not promises.

| Metric | How measured | Threshold |
|---|---|---|
| Decision accuracy | label equals expected, all runs | at least 91.7% (11 of 12) |
| Exception recall | exception cases not approved | 100% |
| False alarms | clean invoices not approved | 0 |
| Unsafe outcomes (hard gates) | exception approved, or approved on wrong data, injected instruction followed, invented total | 0 |
| Critical-field extraction accuracy | vendor, invoice no., PO, currency, total vs ground truth | at least 95% (live runs only) |
| Latency, 95th percentile | excluding throttle waits | at most 30 s (live runs only) |
| Notional cost per invoice | tokens x price | at most $0.10 (live runs only) |
| Hands-on time per invoice | stopwatch | at most 2 min, or 60% below manual (needs a person) |

## 5. Results on the system around the model (synthetic, simulated faults)

Test suite: `244 passed in 45.18s`

### Regression summary: the same experiments on three versions of the code

All runs use synthetic invoices. Fault-injection runs use SIMULATED model errors; robustness runs use a perfect extractor.

| Experiment | Measure | Day 3 code | Hardening round 1 | Hardening round 2 |
|---|---|---|---|---|
| Fault matrix (18 fault types x 48 documents) | runs | 724 | 724 | 724 |
| Fault matrix (18 fault types x 48 documents) | unsafe (approved wrongly or on wrong data) | 18 | 0 | 0 |
| Fault matrix (18 fault types x 48 documents) |   of which carried 'high' confidence | 18 | 0 | 0 |
| Fault matrix (18 fault types x 48 documents) | false alarms (clean invoice flagged for no reason) | 36 | 0 | 0 |
| Fault matrix (18 fault types x 48 documents) | detected (clean invoice flagged because data was corrupted) | 147 | 162 | 162 |
| Fault matrix (18 fault types x 48 documents) | under-flag (Reject downgraded to Needs review) | 86 | 78 | 78 |
| Held-out faults (7 new types x 12 richer documents) | runs | 78 | 78 | 78 |
| Held-out faults (7 new types x 12 richer documents) | unsafe (approved wrongly or on wrong data) | 16 | 11 | 0 |
| Held-out faults (7 new types x 12 richer documents) |   of which carried 'high' confidence | 16 | 11 | 0 |
| Held-out faults (7 new types x 12 richer documents) | false alarms (clean invoice flagged for no reason) | 0 | 0 | 0 |
| Held-out faults (7 new types x 12 richer documents) | detected (clean invoice flagged because data was corrupted) | 6 | 9 | 18 |
| Held-out faults (7 new types x 12 richer documents) | under-flag (Reject downgraded to Needs review) | 3 | 3 | 10 |
| Robustness (perfect extractor, 48 documents) | documents handled exactly as expected | 39 / 48 | 48 / 48 | 48 / 48 |
| Robustness | European-format documents correct | 3 / 12 | 12 / 12 | 12 / 12 |

#### Unsafe outcomes by fault type (before / round 1 / round 2)

| Fault | Plain description | before | round 1 | round 2 |
|---|---|---|---|---|
| F05 vendor_is_customer | The customer (Bill To) is reported as the vendor | 5 | 0 | 0 |
| F06 invoice_no_is_po | The PO number is reported as the invoice number | 9 | 0 | 0 |
| F10 date_is_due_date | The due date is reported as the invoice date | 4 | 0 | 0 |
| H01 date_is_delivery_date | The delivery date is reported as the invoice date | 4 | 4 | 0 |
| H02 date_is_order_date | The order date is reported as the invoice date | 4 | 4 | 0 |
| H03 invoice_no_is_customer_ref | The customer's own reference is reported as the invoice number | 3 | 3 | 0 |
| H04 vendor_is_remit_to | The remit-to name is reported as the vendor | 5 | 0 | 0 |

#### Latency of the deterministic pipeline (no LLM call), this machine

- Robustness set, 48 runs: median 10 ms, 95th percentile 20 ms, max 35 ms.
- Fault matrix, 724 runs: median 11 ms, 95th percentile 116 ms.
- These exclude the model call, which is typically the dominant cost. Real latency needs live runs.

#### Confidence as a warning signal

- Day 3 code: 34 unsafe runs; confidence at the time: {'high': 34}
- Hardening round 1: 11 unsafe runs; confidence at the time: {'high': 11}
- Hardening round 2: 0 unsafe runs; confidence at the time: none


### What each safeguard is for (one switched off at a time)

```
configuration               unsafe (main)  unsafe (held-out)  total runs   which faults become unsafe
all safeguards on                       0                  0         802   
no grounding                            8                  0         802   F07x4, F09x4
no arithmetic                           4                  0         802   F02x4
no cross-field checks                   0                  0         802   
no label anchoring                      0                 11         802   H01x4, H02x4, H03x3
no vendor-vs-PO check                   3                  3         802   F05x3, H04x3
no confidence gate                      0                  0         802
```

### Failure cases and root causes

| # | Failure | Found by | Unsafe runs before | After | Fixed in |
|---|---|---|---|---|---|
| A1 | The customer or remit-to name reported as the vendor | Fault injection (F05) and held-out (H04) | 5 + 5 | 0 | Round 1 |
| A2 | The PO number reported as the invoice number | Fault injection (F06) | 9 | 0 | Round 1 |
| A3 | Another printed date reported as the invoice date (due, delivery, order) | Fault injection (F10) and held-out (H01, H02) | 4 + 4 + 4 | 0 | Round 1 for due date only; **round 2** for the rest |
| A4 | The customer's own reference reported as the invoice number | Held-out (H03) | 3 | 0 | Round 2 |
| A5 | European number format (`1.234,56`) | Robustness set, perfect extractor | 12 of 12 European invoices wrongly rejected as unreadable | 0 | Round 1 |
| A6 | Harmless packaging quirks (code fence, string numbers, reworded descriptions) | Fault injection (F11, F12, F17) | 36 false alarms | 0 | Round 1 |
| A7 | A subtotal printed before "Total" accepted as the total | My own regression test, before release | n/a | n/a | Round 2 |

Details, fixes and regression tests for each: `docs/day4/FAILURE_ANALYSIS.md`.

## 6. Live evaluation with a real model

**NOT YET RUN.** The harness is built and tested (`python scripts/evaluate.py --mode live --runs 3`). Until it is run with a real key, this package makes no claim about extraction accuracy, latency or cost.

## 7. Baseline comparison

# Baseline vs system comparison

Cells that say [MEASURE] have not been measured yet. Nothing here is estimated.

Sources found: Baseline A no (template not filled), Baseline B no (scored rows: 0), live system runs no, system review times no.

| Metric | Baseline A: manual | Baseline B: simple prompt | System (live run) |
|---|---|---|---|
| Decisions correct (of 12, averaged per run) | [MEASURE] | [MEASURE] | [MEASURE] |
| Exceptions caught (of 9) | [MEASURE] | [MEASURE] | [MEASURE] |
| Clean invoices wrongly flagged (of 3) | [MEASURE] | [MEASURE] | [MEASURE] |
| Critical misses (an exception approved) | [MEASURE] | [MEASURE] | [MEASURE] |
| Average hands-on minutes per invoice | [MEASURE] | [MEASURE] | [MEASURE] (timed review of system output) |
| Hands-on time change vs Baseline A | n/a | - | - |
| Cases with invented facts (per run) | n/a | [MEASURE] | 0 by construction (templates), verified by an automated check |
| Average vendor message score (0 to 2) | [MEASURE] (you score what you wrote) | [MEASURE] | [MEASURE] (score the template emails) |


## 8. How to reproduce everything

```
pip install -r requirements.txt
python scripts/generate_data.py --stress --holdout
python -m pytest tests -q                       # unit tests and regression gates
python scripts/robustness.py                    # perfect extractor, all documents
python scripts/stress_test.py                   # simulated mistakes x all documents
python scripts/stress_test.py --holdout         # held-out mistakes and documents
python scripts/ablation.py                      # one safeguard off at a time
python scripts/summarize_day4.py                # before / round 1 / round 2 tables
python scripts/evaluate.py --mode live --runs 3 # needs your key
python scripts/compare.py                       # baselines vs system
python scripts/build_evaluation_package.py      # regenerate this file
```

## 9. Limitations of this evaluation

See `docs/LIMITATIONS.md`. In short: one author wrote the invoices, the faults and the fixes; synthetic invoices are cleaner than real ones; simulated mistakes are not model mistakes; and the model-dependent measurements are still to be taken.
