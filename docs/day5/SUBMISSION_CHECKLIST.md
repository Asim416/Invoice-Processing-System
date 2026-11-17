# Submission Checklist

The submission form asks for five items. This maps each to a file, says how ready it is, and lists what only you can do.

## 1. The five items

| Form item | Deliverable | Where | Readiness |
|---|---|---|---|
| **Working System** (GitHub link) | The repository | The whole `ap-invoice-system` folder | **Ready to push.** Runs from a clean copy; tests pass. CI workflow and Windows launcher are untested |
| **Evaluation Package** | Test cases, baseline vs system, pass/fail, failure analysis, metrics | `docs/day5/EVALUATION_PACKAGE.md` (+ `docs/day4/FAILURE_ANALYSIS.md`, `results/`) | **Partly ready.** Code-level evidence is complete. Live model results and both baselines are **missing** until you run the runbook |
| **Case Study** | Portfolio write-up | The Claude Doc made on Day 5 (export to PDF or Word if the form wants a file) | **Ready as a draft.** Bracketed items need your real numbers |
| **AI Collaboration Note** | Tools, delegation, verification, corrections, your decisions | `docs/day5/AI_COLLABORATION_NOTE.md` | **Needs your input.** The `[YOU: ...]` items are attestations only you can make |
| **Demo Video** (Loom link) | Five-minute screen recording | Script: `docs/day5/DEMO_SCRIPT.md` | **Not recorded.** I cannot record video |

## 2. Do these, in this order

1. **Take the live measurements** (`docs/day4/LIVE_EVALUATION_RUNBOOK.md`): `check_llm.py`, Baseline A, Baseline B, the live evaluation, system review times, `compare.py`. This is the biggest gap between what is built and what you can claim.
2. **Run the proxy-user session** (`docs/day3/PROXY_USER_TEST.md`). Record the findings in `docs/day4/DAY4_REPORT.md` section 9 and fix what you can.
3. **Rebuild the generated documents:** `python scripts/build_evaluation_package.py`. Then fill the bracketed numbers in the case study.
4. **Finish the AI Collaboration Note**: replace every `[YOU: ...]`, delete the grey box at the top.
5. **Record the demo** with `docs/day5/DEMO_SCRIPT.md`.
6. **Run the placeholder search** (section 3) and fix everything it finds.
7. **Create the GitHub repository** (section 4) and add the links to the form.

## 3. Final honesty search

From the project folder:

```
grep -rn "\[MEASURE\]\|\[YOU\|\[ADD\|NOT YET RUN\|not yet measured" docs README.md results/comparison.md
```

(Windows PowerShell: `Select-String -Path docs\*,README.md -Pattern "\[MEASURE\]|\[YOU|\[ADD|NOT YET RUN" -Recurse`.)
Every hit must be either filled in or deliberately left, with the sentence around it still true. Leaving "not yet measured" is
acceptable if it is honest; presenting an unmeasured number as measured is not.

## 4. GitHub repository

1. Create an empty private repository.
2. Copy the project folder contents into it. `.gitignore` already excludes `.env`, `secrets/`, caches, local logs and the virtual environment. **Check with `git status` that no `.env` and nothing from `secrets/` is staged.**
3. Result CSVs under `results/` named `day4_*.csv` are kept so the evaluation can be reproduced; other generated CSVs are ignored.
4. Push. Open the **Actions** tab: the `tests` workflow should go green on Python 3.10, 3.11 and 3.12. It has never run, so a failure there is information, not a surprise.
5. Make sure the README's top lines (what it is, three-step start, "everything here is synthetic") are the first thing a reviewer sees.
6. Share access in the way the form expects (private submissions are accepted).

## 5. What a reviewer can verify without you

| They want to know | They can |
|---|---|
| Does it run? | `bash run.sh` or `run.bat`; one command, about a minute |
| Do the claims hold? | `python -m pytest tests -q`, then the five commands in `docs/day5/EVALUATION_PACKAGE.md` section 8 |
| Is it safe to try? | It uses synthetic data, never pays or sends, and needs no key in demo mode |
| What is missing? | `docs/LIMITATIONS.md` section 1, listed with how to close each gap |

## 6. Scoring rubric self-check

| Criterion (weight) | Your honest position |
|---|---|
| Problem leverage and scope (15%) | A real, recurring, measurable problem; synthetic persona and data stated plainly; non-goals listed. Weak spot: no real user |
| Architecture and engineering (20%) | Strong: layered safeguards with evidence for each, fault-injection evaluation, mutation-checked tests |
| Working product and reliability (20%) | Strong on the code path and failure handling. Weak spot: live model path unproven until you run it |
| Evaluation and learning loop (20%) | Strong on method and honesty (held-out round, root causes). Weak spot: baselines and live results are `[MEASURE]` until you run them |
| Non-developer UX and adoption (15%) | Designed and tested headlessly; one-command start; user guide and runbook. Weak spot: no real person has used it |
| Ownership and communication (10%) | Depends on your note, demo and case study being true in your own words, and on you being able to explain the code |
