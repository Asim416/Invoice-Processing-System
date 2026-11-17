# Operator Runbook

For whoever keeps the Invoice Checker running (IT, finance operations, or the person who installed it). Users have their own
guide (`docs/day3/USER_GUIDE.md`); developers have `docs/DEVELOPER_GUIDE.md`.

Everything here refers to commands and files that exist. Where I could not test something (Windows, a real Google Sheet, a
real Slack workspace, a live model) it says so.

## 1. What you are responsible for

| Responsibility | How often |
|---|---|
| Keep the purchase-order list current (it is the reference the tool matches against) | As POs are raised or closed |
| Check the tool is healthy | Daily at first, then weekly |
| Read the adoption and quality report and review every override | Weekly |
| Audit a sample of approved invoices with a second person | Weekly |
| Rotate secrets, apply updates | Quarterly, or after any suspected leak |

## 2. Where everything lives

| What | Where | Notes |
|---|---|---|
| The program | the project folder | Started with `run.bat` (Windows) or `bash run.sh` |
| Settings and secrets | `.env`, `secrets/` | Git-ignored. Never email or share them |
| Business rules | `config/policy.yaml` | Tolerances, currencies, manager threshold |
| Purchase orders and history | `data/` (local) or your Google Sheet | Choose in `.env` with `STORAGE_BACKEND` |
| Logs | `logs/runs.jsonl`, `logs/events.jsonl` | Local copy even with Google Sheets |

## 3. Starting, stopping, checking health

- **Start:** `run.bat` (Windows, double-click) or `bash run.sh`. The first start sets itself up (about a minute).
- **Stop:** close the black window, or press Ctrl+C.
- **Health check:** `python -m ap.doctor` (add `--online` to test the Google Sheet, `--send-test` to send one test message to Slack). It prints OK, WARN or FAIL with the fix. It never calls the AI provider (that would use quota); for that run `python scripts/check_llm.py`.
- **In the app:** the sidebar shows the mode (demo or live), the data source and whether manager alerts are on; "Check my setup" runs the same checks.

## 4. Routine tasks

| Task | How |
|---|---|
| Add a purchase order | Local: add a row to `data/pos.csv` and one row per item to `data/po_lines.csv`. Sheets: add rows to `POs` and `PO_Lines`. Status must be `open` or `closed`; currency is a 3-letter code. The tool re-reads POs about once a minute |
| Close a purchase order | Change its `status` to `closed` |
| Change a tolerance or the manager threshold | Edit `config/policy.yaml`, restart the app, then run the regression gates (section 8) before relying on it |
| Switch to live AI reading | In `.env`: `EXTRACTION_MODE=live`, `LLM_API_KEY=...`; run `python scripts/check_llm.py` first |
| Turn on Google Sheets / Slack | `docs/day3/SETUP_GOOGLE_SHEETS.md`, `docs/day3/SETUP_SLACK.md` |
| See usage and quality | `python scripts/adoption_report.py --days 14` (section 7) |

## 5. Undoing a mistaken decision

A recorded decision makes the same invoice show up as a duplicate later. If someone recorded the wrong decision:

1. Open `data/processed_invoices.csv` (or the `Processed` tab) and find the row by invoice number or run id.
2. Change its `human_decision` to `void`. **Do not delete the row**: the history is the audit trail.
3. Add a short reason in the `note` column and your name or initials.
4. The next check of that invoice ignores the voided row. (Covered by an automated test.)

There is no button for this by design: it should be a deliberate, visible act by an operator.

## 6. Incidents

| What you see | Most likely cause | What to do | How to confirm it is fixed |
|---|---|---|---|
| "The invoice reader is not available" | AI provider down, wrong or expired key, or no internet | `python scripts/check_llm.py`; check the key in `.env` and the provider's status page. Users can still read invoices manually: results fall back to **Needs review**, never Approve | `check_llm.py` prints PASS |
| "The invoice reader is busy" | Free-tier rate limit | Wait a minute. If frequent, lower `LLM_TOKENS_PER_MINUTE` in `.env` or move to a paid plan | The message stops |
| Many clean invoices go to review with "reading not fully certain" | Retries are frequent, or the AI answers are failing the checks | Open the technical details of a run; read `docs/day4/FAILURE_ANALYSIS.md`; run the live evaluation (`docs/day4/LIVE_EVALUATION_RUNBOOK.md`) | Review rate falls |
| "Google denied access" or "spreadsheet not found" | Sheet not shared with the service account, or wrong id | `python -m ap.doctor --online` and follow its fix | Doctor shows connected |
| The app will not start: "data source is not available" | Sheets unreachable at startup | As above; to keep working meanwhile set `STORAGE_BACKEND=csv` (note: local data will not match the Sheet) | App opens |
| "Send to manager" says the message was not sent | Wrong webhook, revoked app, or Slack outage | `python -m ap.doctor --send-test`; contact the manager another way (the invoice result is saved) | Test message arrives |
| An invoice is flagged as a duplicate but is not | A wrong decision was recorded earlier, or two real invoices share a number | Check the matching row; void it if it was a mistake (section 5) | Re-check shows no duplicate |
| An invoice that should have been caught was approved | A gap in the checks | **Treat as a priority incident**: keep the run record (`logs/runs.jsonl`, `Runs` tab), reconstruct what the PDF said, and give it to a developer to add as a test case (developer guide, section 5) | A new test fails before the fix and passes after |
| "Python was not found" on Windows | Python missing or not on PATH | Install Python 3.10+ from python.org with "Add to PATH" | `python --version` works |

## 7. Weekly review

```
python scripts/adoption_report.py --days 7
```

The report (from the tool's own logs) shows how many invoices were checked, how many decisions were recorded, how often a
person disagreed with a recommendation, how long decisions took, duplicates flagged, value held, error and retry rates, and
live latency and tokens. It prints a warning at the top if all the data is test traffic.

Then, every week:

1. **Read every override**: each "Approve overridden" is a possible missed exception the person caught; each "Reject (hold) approved" is a false alarm or a person error. Write down what happened.
2. **Audit a sample**: a second person re-checks 10 random invoices that were approved. Record how many were wrong. This is the only way to measure wrongful approvals, because the logs cannot see them.
3. **Time 10 invoices** with a stopwatch to keep the time-saved figure honest (the logs cannot measure hands-on time).
4. Compare with the targets in `docs/day5/TWO_WEEK_PLAN.md`.

## 8. Before you change anything

A change to policy, to the AI model or provider, to the prompt, or to code must pass the regression gates:

```
python -m pytest tests -q                     # all tests, including the fault-matrix gates
python scripts/robustness.py                  # perfect extractor: every document variant must be handled as expected
python scripts/stress_test.py                 # simulated mistakes: unsafe runs must be 0
python scripts/stress_test.py --holdout       # held-out mistakes: unsafe runs must be 0
```

If you change the AI model or the prompt, also re-run the live evaluation (`python scripts/evaluate.py --mode live --runs 3`) and
compare with the previous run. A model that is cheaper but approves one wrong invoice is not an upgrade.

## 9. Security and privacy

- **Secrets:** `.env` and everything in `secrets/` stay on the machine. If one leaks: revoke it at the provider (Groq key, Google service account key, Slack webhook), create a new one, update `.env`.
- **Data sent out:** invoice text goes to the AI provider in live mode. The data in this repository is synthetic. Before using real invoices, read the provider's data-retention terms, and consider a local model (Ollama) for sensitive invoices.
- **Data minimisation:** the tool does not extract bank details, tax IDs or addresses, and logs record codes and hashes, not invoice text.
- **Least privilege:** share the Google Sheet with the service account only; the Slack webhook posts to one channel only; there is no payment, email-sending or ERP access anywhere.
- **User identity:** the tool records none. If you need to know who recorded a decision, that is a Day-6 feature (see the plan).

## 10. Backup and recovery

- With Google Sheets, use File > Version history; download a copy of the sheet monthly.
- Locally, back up `data/processed_invoices.csv`, `data/pos.csv`, `data/po_lines.csv` and `logs/`.
- Everything else can be rebuilt: `bash run.sh` recreates the environment and `python scripts/generate_data.py` the sample data.
- If the processed log is lost, duplicate detection restarts from zero: warn users that the first checks cannot see earlier invoices.

## 11. What you must never do

- Disable a check to make an invoice pass.
- Edit `data/ground_truth/` or the expected results to make a test pass (fix the cause).
- Delete rows from the processed log or the run history (void them).
- Put a key in a file that is committed or shared.
- Describe a demo-mode result as AI output.

## 12. Not verified by me

`run.bat` on Windows, the Google Sheets and Slack setup against real accounts, the GitHub Actions workflow, and everything that
needs a live AI model. The first time you do each, tell the developer what actually happened so this runbook can be corrected.
