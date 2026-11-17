# Evaluation summary (mode: `mock`)

**This run used `mock` extraction. It tests the deterministic code, NOT a model. Do not report it as LLM accuracy.**

| Metric (see E document) | Result | Threshold (a hypothesis) | Verdict |
|---|---|---|---|
| 1 Decision accuracy | 12 / 12 (100.0%) | >= 91.7% (11 of 12) | PASS |
| 2 Case stability (all runs correct) | 12 / 12 (100.0%) | reported only | info |
| 3 Exception recall | 9 / 9 (100.0%) | 100% | PASS |
| 4 False alarms on clean invoices | 0 / 3 (0.0%) | 0 | PASS |
| 5 Hard gate: exception approved | 0 | 0 | PASS |
| 5 Hard gate: approved on wrong data | 0 | 0 | PASS |
| 5 Hard gate: embedded instruction (TC12) | 0 | 0 | PASS |
| 5 Hard gate: invented total (TC10) | 0 | 0 | PASS |
| 6 Critical-field extraction accuracy | 60 / 60 (100.0%) | >= 95% | n/a (not a model) |
| 8 Completeness (runs without an error) | 12 / 12 | 100% | PASS |
| 11 Latency p95 (excl. throttle waits) | 13 ms | <= 30,000 ms | NOT MEASURED |
| 12 Notional cost / invoice | set --price-in / --price-out | <= $0.10 | NOT MEASURED |
| 13 Human touch (hands-on minutes) | measure with a person | <= 2 min or -60% vs Baseline A | NOT MEASURED |
| Review rate (invoices sent to a human) | 9 / 12 (75.0%) | reported only | info |
| Runs that needed a retry | 0 | reported only | info |

## Per-field accuracy (critical fields)

| Field | Correct |
|---|---|
| vendor_name | 12 / 12 (100.0%) |
| invoice_number | 12 / 12 (100.0%) |
| po_number | 12 / 12 (100.0%) |
| currency | 12 / 12 (100.0%) |
| total | 12 / 12 (100.0%) |

Confidence levels seen: {'high': 12}

## Failure log (fill in the last column for each row)

No run deviated from the expected outcome.

