# Adoption and quality report

**READ THIS FIRST: every run in this window is synthetic or used demo-mode extraction (data origin {'synthetic': 12}, modes {'mock': 12}). These figures describe test traffic, NOT real adoption or real quality. Do not quote them as results.**

Window: 2026-11-16T04:10:08.322950+00:00 to now

## Adoption

| Metric | Value |
|---|---|
| Invoices checked | 12 |
| Days with at least one check | 1 |
| Checks per active day | 12.0 |
| Decisions recorded (follow-through) | 8 of 12 checks that could be recorded (67%) |
| Time from check to recorded decision (median / 90th pct, minutes; includes idle time) | 0.1 / 0.1 (n=8) |
| Manager escalations sent / failed | 0 / 0 |

## Recommendations vs people

| Metric | Value | How to read it |
|---|---|---|
| Recommendation mix | {'Approve': 3, 'Needs review': 7, 'Reject (hold)': 2} | Share sent to a human is the review burden |
| 'Approve' recommendations that a person overrode | 0 of 3 | Possible missed exceptions the person caught. Review every one |
| 'Reject (hold)' recommendations that a person approved | 1 of 2 | False alarms, or a person error. Review every one |
| How people resolved 'Needs review' | {'hold': 3} | |

## Value

- Possible or exact duplicates flagged: 2
- Total value held or rejected after a flag (by currency): {'USD': 52620.0}
- Most common reasons for review: {'AMOUNT_OVER_TOLERANCE': 3, 'UNIT_PRICE_MISMATCH': 2, 'QUANTITY_EXCEEDS_PO': 1, 'EXACT_DUPLICATE': 1, 'POSSIBLE_DUPLICATE': 1, 'PO_MISSING_ON_INVOICE': 1}

## Reliability

- Runs with an error or degraded result: 0.0% 
- Runs needing an extraction retry: 0.0%
- Confidence levels: {'high': 12}

## Not measurable from logs (do these by hand)

- **Hands-on time saved**: time 10 invoices a week with a stopwatch and compare with Baseline A.
- **Wrongful approvals**: a second person re-checks a random sample of approved invoices every week.
- **Who used it**: the tool records no user identity by design.

