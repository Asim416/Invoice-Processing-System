## Regression summary: the same experiments on three versions of the code

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

### Unsafe outcomes by fault type (before / round 1 / round 2)

| Fault | Plain description | before | round 1 | round 2 |
|---|---|---|---|---|
| F05 vendor_is_customer | The customer (Bill To) is reported as the vendor | 5 | 0 | 0 |
| F06 invoice_no_is_po | The PO number is reported as the invoice number | 9 | 0 | 0 |
| F10 date_is_due_date | The due date is reported as the invoice date | 4 | 0 | 0 |
| H01 date_is_delivery_date | The delivery date is reported as the invoice date | 4 | 4 | 0 |
| H02 date_is_order_date | The order date is reported as the invoice date | 4 | 4 | 0 |
| H03 invoice_no_is_customer_ref | The customer's own reference is reported as the invoice number | 3 | 3 | 0 |
| H04 vendor_is_remit_to | The remit-to name is reported as the vendor | 5 | 0 | 0 |

### Latency of the deterministic pipeline (no LLM call), this machine

- Robustness set, 48 runs: median 10 ms, 95th percentile 20 ms, max 35 ms.
- Fault matrix, 724 runs: median 11 ms, 95th percentile 116 ms.
- These exclude the model call, which is typically the dominant cost. Real latency needs live runs.

### Confidence as a warning signal

- Day 3 code: 34 unsafe runs; confidence at the time: {'high': 34}
- Hardening round 1: 11 unsafe runs; confidence at the time: {'high': 11}
- Hardening round 2: 0 unsafe runs; confidence at the time: none
