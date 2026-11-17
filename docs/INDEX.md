# Documentation Index

Start with the row that matches who you are.

| If you are... | Read |
|---|---|
| A **user** (finance staff) | `docs/day3/USER_GUIDE.md` |
| An **operator** (keeps it running) | `docs/OPERATOR_RUNBOOK.md`, then `docs/day3/SETUP_GOOGLE_SHEETS.md` and `docs/day3/SETUP_SLACK.md` |
| A **developer** (changes it) | `docs/ARCHITECTURE.md`, then `docs/DEVELOPER_GUIDE.md` |
| A **reviewer** (judges it) | `docs/day5/EVALUATION_PACKAGE.md`, `docs/LIMITATIONS.md`, the case study, `docs/day5/AI_COLLABORATION_NOTE.md` |
| **Taking the live measurements** | `docs/day4/LIVE_EVALUATION_RUNBOOK.md` |
| **Preparing the submission** | `docs/day5/SUBMISSION_CHECKLIST.md`, `docs/day5/DEMO_SCRIPT.md` |

## By topic

| Topic | Document |
|---|---|
| How it works now | `docs/ARCHITECTURE.md` |
| Why the AI is used in one place only | `docs/ARCHITECTURE.md` section 1; `docs/day2/C_technology_choices.md` (historical) |
| The test sets, faults and results | `docs/day5/EVALUATION_PACKAGE.md` |
| What broke and why | `docs/day4/FAILURE_ANALYSIS.md`, `docs/day4/DAY4_REPORT.md` |
| What is not proven | `docs/LIMITATIONS.md` |
| First two weeks and next iteration | `docs/day5/TWO_WEEK_PLAN.md` |
| Day-by-day record | `docs/day2/` to `docs/day4/` reports; Day 1 lives in the Day 1 package document |

## Quick commands

```
bash run.sh                        # or double-click run.bat on Windows: sets up and starts the app
python -m ap.doctor                # is everything set up? (add --online to test Google Sheets)
python -m pytest tests -q          # all tests and regression gates
python scripts/adoption_report.py --days 14
python scripts/evaluate.py --mode live --runs 3     # needs your key
```

## Status of the evidence in one paragraph

The system around the AI model is thoroughly tested on synthetic data with simulated mistakes. The real model, the two baselines,
real users and real invoices have **not** been measured; the tools to measure them are built, and `docs/LIMITATIONS.md` lists each gap.
