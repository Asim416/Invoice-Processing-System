# First Two Weeks After Deployment, and the Next Iteration

**Status: a plan, not results.** No deployment has happened and no adoption data exists. The figures below are thresholds
to *review*, set before any data, so that "good enough" is decided in advance and not after seeing the numbers. The report
tool (`scripts/adoption_report.py`) is built and tested; its only example output is on synthetic traffic and says so in its first line.

## 1. Goal of the first two weeks

Answer, with evidence, three questions: **Is it used? Is it right? Does it save time without adding risk?** And decide
whether to expand, adjust or stop.

## 2. Rollout

| When | Mode | What happens | Exit check |
|---|---|---|---|
| Before day 1 | Preparation | Run the live evaluation and baselines (`docs/day4/LIVE_EVALUATION_RUNBOOK.md`); set up Google Sheets and Slack; load current POs; run `python -m ap.doctor --online`; run the proxy-user test with one non-developer | Doctor shows no FAIL; live evaluation has zero unsafe outcomes; the proxy user completed the tasks |
| Days 1 to 5 | **Shadow**: the person processes every invoice the old way and also checks it in the tool | Compare decisions daily; record every disagreement | No approved invoice later found wrong; disagreements understood |
| Days 6 to 10 | **Assisted**: the tool's result is the starting point; the person still decides and records | Normal use; weekly audit | Metrics below within thresholds |
| Days 11 to 14 | Assisted, plus review | Compile the report, hold the review meeting, decide: expand, adjust, or stop | Written decision |

At no point does the tool pay, send or change anything on its own.

## 3. Metrics

Source `log` means `python scripts/adoption_report.py --days 14`, computed from the tool's own records. Source `person` means someone must measure it.

### Adoption

| Metric | Definition | Source | Threshold to review |
|---|---|---|---|
| Invoices checked | Runs in the window | log | Roughly the real weekly volume (about 40 a week was the assumption; replace with the true figure) |
| Active days | Days with at least one check | log | Used on most working days |
| Follow-through | Decisions recorded / checks that could be recorded | log | At least 90%. A low value means people check but do not record, which hides duplicates from the log |
| Time to decision | Median minutes from check to recorded decision (includes idle time) | log | Trending down; investigate the 90th percentile |
| Escalations | Manager alerts sent and failed | log | Failed = 0 |

### Quality

| Metric | Definition | Source | Threshold to review |
|---|---|---|---|
| **Wrongful approvals** | Approved invoices found wrong on a second person's re-check (10 random per week) | person | **0.** Any occurrence is an incident (operator runbook, section 6) |
| Approve overridden | Recommendations of Approve that a person recorded as hold or reject | log | Each one reviewed individually; a rate above 5% means the checks miss things |
| Hold approved | Recommendations of Reject (hold) that a person approved | log | Each one reviewed; frequent cases mean the rules are too strict or a person is overriding too easily |
| Review rate | Share of checks sent to a person | log | Compare with the real exception rate. The ~18% exception rate in the Day 1 package is a figure published by a vendor, not a measurement of this business |
| Error rate | Checks with a degraded result (reader unavailable, bad file) | log | Below 5% |
| Retry rate and confidence mix | Share needing an extraction retry; high / medium / low | log | Retry rate below 10%; if higher, revisit the model or prompt |
| Duplicates flagged and value held | Count and sum of amounts held or rejected after a flag | log | Reported, not thresholded: this is the main value claim, so check a sample by hand |

### Efficiency

| Metric | Definition | Source | Threshold to review |
|---|---|---|---|
| Hands-on time per invoice | Stopwatch on 10 invoices a week, whole check to decision | person | At most 2 minutes, or 60% below the manual baseline. The brief's before-and-after claim depends on this |
| Live latency | Median and 95th percentile of a check, excluding throttle waits | log | 95th percentile at most 30 seconds |
| Tokens and cost | Tokens per invoice; notional cost at the provider's price | log | At most $0.10 per invoice notional |

## 4. How decisions will be made

| After week 1 | After week 2 |
|---|---|
| **Stop and fix** if any approved invoice was wrong, or the tool crashed on a normal invoice | **Expand** only if wrongful approvals = 0, follow-through is at least 90%, and hands-on time is at or below the threshold |
| **Adjust** if reviews are far above the real exception rate (loosen nothing without a test; first find why) | **Adjust** if quality is good but time saved is small (usually a usability problem) |
| Otherwise continue | **Stop** if unsafe outcomes appear that a test cannot reproduce |

## 5. What we will not conclude from two weeks

- A low override rate does not prove the tool is right: people may be accepting recommendations without looking (automation bias). That is why the weekly second-person audit exists.
- A high review rate is not necessarily bad: it may be the real exception rate.
- Fewer than about 100 invoices is too few to speak of percentages; report counts.
- Anything measured in shadow week is not the tool's effect on payment accuracy.

## 6. Ongoing cadence

| Who | When | Task |
|---|---|---|
| Operator | Daily (week 1), then weekly | `python -m ap.doctor`; read errors |
| Operator and reviewer | Weekly | Adoption report; read every override; audit 10 approvals; time 10 invoices |
| Developer | After any incident | Reproduce as a test, fix the root cause, run the gates |
| Everyone | End of week 2 | Review meeting and written decision |

## 7. Next iteration (weeks 3 and 4), in priority order

Each item says what evidence would justify it, so the backlog follows data, not enthusiasm.

| Priority | Item | Why | Evidence needed first | Done when |
|---|---|---|---|---|
| P0 | Take the live measurements and publish them honestly | Everything model-related is currently unmeasured | None: just do it | Live evaluation, both baselines, hands-on times in the Evaluation Package |
| P0 | Build a small evaluation set from **real** (privacy-reviewed) invoices | Synthetic data is clean and written by one author | Permission and a redaction method | At least 30 real invoices with expected outcomes, all gates passing on them |
| P1 | Review real failures and add each as a test | The highest-value learning source | Shadow-week disagreements | Every disagreement has a root cause and a test |
| P1 | Tax lines and subtotals | Common on real invoices; currently routed to review | Share of real invoices with tax | Subtotal, tax and total reconciled; tests for subtotal-as-total |
| P1 | Scanned invoices (OCR) | Currently unreadable | Share of real invoices that are scans | Measured accuracy of OCR plus the same safeguards |
| P1 | Relax or keep "retry means review" | It adds reviews | Real retry rate and post-retry accuracy | A decision with numbers |
| P2 | Void button and user identity in the audit trail | Voiding is a manual edit; nobody can see who decided | Operator feedback | Recorded user on each decision; undo with a reason |
| P2 | Vendor alias list owned by finance | Legitimate name differences go to review | Count of false vendor mismatches | Aliases honoured; look-alike protection kept |
| P2 | Concurrency safety for the duplicate check | Two reviewers at once could both pass | More than one regular user | A write-time duplicate re-check |
| P3 | Multi-page invoices and multi-currency | Out of scope today | Real frequency | Per-case decision |
| P3 | ERP or accounting-system integration | Reduces double entry | Proven quality over weeks | Read-only first |

## 8. Risks to watch

| Risk | Early sign | Response |
|---|---|---|
| Automation bias (people stop checking) | Near-zero overrides, very short decision times, audit finds errors | Raise audit sample; show the reasons more prominently; retrain |
| Unknown layouts defeat anchoring | Frequent "not printed next to a label" reviews | Add labels from a real sample, with tests |
| Free-tier limits | Rate-limit messages at busy times | Lower the token setting, spread work, or move to a paid plan |
| Data leaves the company in live mode | Policy concern | Local model (Ollama) or redaction before sending |
| Duplicate log gets out of sync | Missed duplicates | Single source of truth (the Google Sheet), voiding instead of deleting |
