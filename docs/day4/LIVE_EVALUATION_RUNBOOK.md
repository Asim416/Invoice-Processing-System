# Live Evaluation Runbook (what only you can do)

The sandbox I work in cannot reach Groq, and I cannot time a person with a stopwatch. Everything below needs your key, your
hands, or another human. The tools are built and tested against stand-ins; **none of the numbers they will produce exist yet.**

Rule for the case study: quote only what these steps actually produce, with the model name and the date.

## 0. Before you start (5 minutes)

1. Put your key in `.env` (copy `.env.example`): `EXTRACTION_MODE=live`, `LLM_API_KEY=...`. Never paste the key anywhere else.
2. On the Groq console **Limits** page, note your real limits. The free-tier figures I quoted earlier were from a third-party summary and may not match your account.
3. `python scripts/check_llm.py` must print `PASS`. If it fails, send me the output (it contains no secrets) before doing anything else.

## 1. Baseline A: you doing it by hand (about 1 hour)

```
python scripts/compare.py --init            # creates results/baseline_A_manual.csv
```

For each of the 12 invoices (`data/invoices/TC01.pdf` to `TC12.pdf`), use **only** a spreadsheet, a PDF viewer and a calculator
(open `data/pos.csv` and `data/po_lines.csv` for the purchase orders, `data/processed_invoices.csv` for what was already
processed). Time yourself from opening the invoice to having a decision, write the minutes and the decision
(`Approve`, `Needs review` or `Reject (hold)`) in the CSV. You know the planted errors, so your times are optimistic; say so in the case study.

## 2. Baseline B: a plain chat assistant, no system (about 1 hour)

Either paste the prompts yourself (best, it is exactly what a user would do):

```
python scripts/baseline_prompt.py --print    # writes results/baseline_B_prompts.md
```

or let the script call your model (3 runs of 12 prompts; mind the daily token limit, use `--runs 1` if unsure):

```
python scripts/baseline_prompt.py --call --runs 3     # writes results/baseline_B_responses.csv
```

Then open `results/baseline_B_responses.csv` (if you pasted manually, create the same columns) and fill in for each answer:
`your_label` (what decision the answer amounts to), `invented_facts` (`yes` or `no`), `vendor_message_score`
(0 wrong or invented, 1 usable but vague, 2 accurate and specific), `minutes_hands_on`.

## 3. The live evaluation of the system (about 15 to 30 minutes of waiting)

```
python scripts/evaluate.py --mode live --runs 3 --price-in <$ per 1M input tokens> --price-out <$ per 1M output tokens>
```

Take the two prices from your provider's price page on the day; on the free tier the real cost is $0 and the notional price
shows what the same workload would cost. The harness throttles itself to your tokens-per-minute setting
(`LLM_TOKENS_PER_MINUTE` in `.env`; lower it if you see rate-limit errors).

Token budget, as an **estimate** (replace it with the measured figure the first run prints): about 36 calls of roughly 1.5 to 3
thousand tokens each. Baseline B with `--call --runs 3` adds another 36. Together with `check_llm.py` this can approach a free-tier
daily limit of 200,000 tokens, so do them on different days or reduce the runs.

Output: `results/eval_live_runs.csv` and `results/eval_live_summary.md`. The summary lists every metric against its threshold,
marks the ones that cannot be measured by a script as `NOT MEASURED`, and ends with a **failure log** with an empty root-cause column.

Optional, harder documents (60 instead of 12 documents; only 1 run, about 5 times the tokens):

```
python scripts/evaluate.py --mode live --include-stress --runs 1
```

## 4. Time the human review of the system's output

Start the app (`bash run.sh` or `run.bat`), switch the app to live mode in `.env`, and for each of the 12 invoices time how long
it takes you to read the result and make your decision. Save as `results/system_review_times.csv` with columns
`case_id,minutes_hands_on`. This is the "manual touch" metric; the target is at most 2 minutes, or 60% below Baseline A.

## 5. Compare

```
python scripts/compare.py                    # writes results/comparison.md
```

Anything not yet measured stays `[MEASURE]`. The script warns if the system column came from a local or stand-in endpoint.

## 6. Failure loop (the point of Day 4)

For every non-`CORRECT` row in the failure log:

1. Read the finding codes and the confidence. Was the extraction wrong (`ok_*` columns in the CSV), or were the rules wrong?
2. Write one row in `docs/day4/FAILURE_ANALYSIS.md`, section D: root cause, fix, re-test.
3. Add a test that fails without your fix. Re-run `python -m pytest tests -q` and the whole evaluation. Keep the before and after numbers.
4. If a fix only helps the examples you saw, test it on a case you did not use to design it (as the held-out set did for me).

## 7. Proxy-user test

Follow `docs/day3/PROXY_USER_TEST.md`, then add the findings to the table at the end of `docs/day4/DAY4_REPORT.md` (section 9) with
the change you made and whether you re-tested it.

## What a good result looks like, and what to do if you do not get one

- Decision accuracy and extraction accuracy are hypotheses (91.7% and 95%), not promises. If the model falls short, **report the
  real figure and explain it**; the brief rewards honesty about where improvement was not achieved.
- Zero unsafe outcomes is the one number that must not be negotiated. If a real run approves something it should not, that is
  your most valuable finding: write it up first.
- If many clean invoices go to review, look at the finding codes: `LOW_CONFIDENCE_EXTRACTION` after a retry and anchoring
  failures are the likely causes. Decide whether the trade-off (more reviews) is acceptable, and say so.
