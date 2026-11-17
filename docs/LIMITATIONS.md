# Limitations, Non-Goals and What Is Still Unverified

Written so a reviewer, an operator or a future developer can see exactly where the evidence stops. If something here
contradicts another document, this one is the more cautious and should win.

## 1. What has not been verified (and how to verify it)

| Not verified | Why | How to verify | Where the result goes |
|---|---|---|---|
| Extraction accuracy, latency, tokens and cost of a **real model** | The development sandbox could not reach the AI provider | `python scripts/check_llm.py`, then `python scripts/evaluate.py --mode live --runs 3` | `results/eval_live_summary.md`; `docs/day4/FAILURE_ANALYSIS.md` section D |
| Baseline A (manual) and Baseline B (plain chat) numbers | Need a person with a stopwatch and a model | `docs/day4/LIVE_EVALUATION_RUNBOOK.md`, steps 1 and 2 | `results/comparison.md` |
| Hands-on time saved | Needs a person | Runbook step 4 | Same |
| A real person using the tool unaided | No proxy user has run it | `docs/day3/PROXY_USER_TEST.md` | Day 4 report, section 9 |
| Real Google Sheets and Slack connections | No access to real accounts | `python -m ap.doctor --online`, `--send-test` | Operator runbook |
| `run.bat` on Windows | Only Linux was available | Double-click it on Windows | Operator runbook |
| The GitHub Actions workflow | Written without access to GitHub | First push | CI result |
| Behaviour on real invoices | Only synthetic invoices exist | A privacy-reviewed sample of real invoices (`docs/day5/TWO_WEEK_PLAN.md`) | New test cases |
| Setup guides for Google and Slack | Written from general knowledge, not tested against current screens | Follow them once | Correct the guides |

## 2. Non-goals (deliberately out of scope)

Paying invoices or any bank integration; three-way matching with goods receipts; deep fraud detection (forged but
plausible figures, bank-detail changes); currency conversion; tax rules; scanned or handwritten invoices (no OCR); multi-page
invoices as a supported input; multi-user accounts and roles; ERP integration; learning from past decisions; replacing human approval.

## 3. Known limitations of the system

| Area | Limitation | Consequence |
|---|---|---|
| Documents | Text-layer PDFs only | A scanned invoice gets "Needs review" with a clear message |
| Tax lines | Not supported: lines must sum to the total | Such invoices go to review (tested) rather than being mis-read |
| Currency | One per invoice; no conversion | A currency different from the PO's goes to review |
| Under-billing | Billing below the PO total is shown as information, not an exception | Under-billing beyond tolerance is not flagged |
| Duplicate detection | Same vendor and number, or same vendor, total and date | A re-keyed invoice with a different number, total and date is not caught |
| Label anchoring | Applies only if the document has a familiar label (Invoice No, Bill No, Total, Amount due, Invoice Date, Issued) | Unfamiliar wording gets no anchoring; grounding and arithmetic still apply |
| Vendor check | Needs a PO. Look-alike threshold (0.95) was chosen by reasoning, not tuned | No PO means no vendor cross-check; a legitimately different issuer goes to review |
| Number reading | Both US and European conventions are accepted | Grounding is slightly more permissive for ambiguous numbers such as `1.234` |
| Repeated PO items | Items with identical descriptions match the first PO line | A PO with two identical lines is mis-matched |
| Retries | A retried extraction is always sent to a person | More reviews if the model needs retries often (a deliberate trade-off to revisit with real data) |
| Concurrency | One reviewer at a time is assumed | Two people recording the same invoice at once could both pass the duplicate check |
| Identity | The tool records no user identity | You cannot see who recorded a decision |
| Undo | Voiding is a manual edit | Deliberately visible, but not user-friendly |
| Scale | Built for tens of invoices a day | Not tested beyond that; Google Sheets API quotas apply |
| Browser | The web interface was driven by scripts, never opened in a real browser by me | Layout and feel are unverified |

## 4. Limits of the evidence

- **One author.** The same person (and AI assistant) wrote the invoices, the simulated faults, the fixes and the tests. The held-out round reduces this bias but was also designed after seeing earlier failures.
- **Synthetic documents** are cleaner than real ones: no scanning noise, few layouts, no tax lines, no multi-page.
- **Simulated mistakes are not model mistakes.** The ablation says which layer handles which kind of mistake, not how often a model makes each.
- **Zero unsafe outcomes** means the failures that were thought of are covered, not that none exist.
- **Small samples**: 12 base cases and three runs each; results indicate direction, not statistical significance.
- **Two safeguards** (the cross-field checks and the confidence gate) showed no unique contribution on the test set; they are kept as redundancy, not as proven necessities.
- **Estimates** about token budgets and rate limits are estimates, and the free-tier figures came from a third-party summary.

## 5. Privacy and security notes

- All data in the repository is synthetic. Real invoices contain personal and commercial data: review the provider's retention terms, minimise what is sent, and consider a local model first.
- Invoice text is sent to the AI provider in live mode; manager alerts contain vendor, number, total and reasons only.
- The Sheets integration needs one service account with Editor access to one spreadsheet; nothing wider.
- Prompt-injection defence is structural (the model cannot set a label) plus wording heuristics. It does not defend against a skilfully forged but plausible invoice.

## 6. Things that would change my mind about the design

- Live runs showing the model rarely needs retries, and accurate retried answers: relax the "retry means review" rule.
- Real invoices with labels the anchoring does not know: widen the label lists, guided by a sample.
- Frequent legitimate vendor-name differences: add a vendor alias list owned by finance.
- Evidence that the cross-field checks never fire in real traffic: simplify them away.
