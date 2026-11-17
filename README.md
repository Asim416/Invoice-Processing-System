# Invoice Checker: AP invoice exception handling

Checks a supplier invoice (PDF) against its purchase order and recommends **Approve**, **Needs review** or **Reject (hold)**,
with reasons in plain language and a draft email to the vendor. **The AI only reads the invoice; fixed rules decide; a person
records every decision. Nothing is ever paid or sent by the tool.**

> **Everything in this repository is synthetic.** The user (Priya), the vendors and every invoice are fictional, and no real user
> has used it. The surrounding safety net is thoroughly tested; **the AI model itself, the two baselines and a real user session
> have not yet been measured** (the tools to do so are built). See `docs/LIMITATIONS.md` for the exact list.

## Start it in three steps

1. Install Python 3.10 or newer (python.org; on Windows tick **Add to PATH**).
2. Open the project folder and run the launcher:
   - **Windows:** double-click `run.bat`
   - **Mac / Linux:** `bash run.sh`
3. A browser tab opens at http://localhost:8501. Pick a sample invoice, press **Check this invoice**.

The first start creates its own environment and sample data (about a minute). The application defaults to **live AI extraction**. Configure an LLM API key before processing invoices. Built-in samples remain available for testing, but in live mode they are also sent through the configured reader.

## Use your own invoices (live mode)

1. Copy `.env.example` to `.env` and set `LLM_API_KEY=...` (a Groq key, or a key for any compatible endpoint). `EXTRACTION_MODE=live` is the default. Never share `.env`.
2. `python scripts/check_llm.py` should print PASS.
3. Restart the app. The sidebar should show the configured live AI reader.

The web interface accepts multiple PDF files in one upload. Each invoice is processed separately and receives its own result, findings, and human decision controls. Batch processing is sequential to respect provider rate limits and keep failures isolated; one failed PDF does not prevent the remaining files from being processed.

Optional: Google Sheets for your purchase orders and history (`docs/day3/SETUP_GOOGLE_SHEETS.md`), Slack manager alerts (`docs/day3/SETUP_SLACK.md`).
Check any setup with `python -m ap.doctor`.

## Where to read next

`docs/INDEX.md` has a path for each reader. In short: users `docs/day3/USER_GUIDE.md`; operators `docs/OPERATOR_RUNBOOK.md`;
developers `docs/ARCHITECTURE.md` and `docs/DEVELOPER_GUIDE.md`; reviewers `docs/day5/EVALUATION_PACKAGE.md`.

## Prove it to yourself

```bash
pip install -r requirements.txt
python scripts/generate_data.py --stress --holdout   # 12 base + 36 harder + 12 held-out synthetic invoices
python -m pytest tests -q                            # all tests and regression gates, no accounts or keys needed
python scripts/stress_test.py                        # 18 kinds of simulated reader mistake x every document
python scripts/stress_test.py --holdout              # 7 more, on documents never used to design the fixes
python scripts/ablation.py                           # switch one safeguard off at a time
python scripts/robustness.py                         # perfect reader: does the document alone change the outcome?
```

These test the system around the model with simulated mistakes. They are **not** AI accuracy results.

To take the real measurements (needs your key and your time): `docs/day4/LIVE_EVALUATION_RUNBOOK.md`
(`scripts/evaluate.py`, `scripts/baseline_prompt.py`, `scripts/compare.py`). After deployment, `python scripts/adoption_report.py --days 14`.

## How it is built, in five lines

1. Read: PDF text, then one AI call that returns fixed fields (strict schema, retries, throttle, cache).
2. Check: arithmetic, grounding in the document, label anchoring, vendor-vs-PO, duplicates, tolerances. Deterministic code.
3. Decide: any problem leads to Needs review or Reject; **Approve must be earned**.
4. Say: templates write the note and the vendor email, and every number must trace to a verified fact.
5. A person decides and records; only that step changes what counts as a duplicate later.

## Layout

```
ap/            the program: schemas, extraction, validation, anchors, names, rules, decision, templates, storage,
               storage_sheets, notify, friendly, ui_logic, adoption, doctor, pipeline, cli
app.py         the web app          run.sh / run.bat   one-command start
config/        policy.yaml (tolerances and thresholds)       templates/   email and note text
evalkit/       fault injection, runner, metrics (used by the evaluation scripts and the tests)
scripts/       data generator, evaluation, ablation, baselines, comparison, reports, setup helpers
tests/         unit, integration, interface and regression-gate tests
data/          synthetic invoices, purchase orders, ground truth, expected results
docs/          index, architecture, operator runbook, developer guide, limitations, and the day-by-day record
results/       saved evidence (day4_*.csv), comparison and baseline templates
```

## Known limits

Text PDFs only (no OCR); no tax lines; one currency per invoice; one reviewer at a time; web interface never opened in a real
browser by the author; Windows launcher, Google Sheets, Slack and the CI workflow untested against the real services. Full list: `docs/LIMITATIONS.md`.
