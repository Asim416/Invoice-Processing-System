"""Assembles docs/day5/EVALUATION_PACKAGE.md from the saved data and result files (no hand-typed numbers).

  python scripts/build_evaluation_package.py
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evalkit.faults import FAULTS, HOLDOUT_FAULTS      # noqa: E402


def read(p: Path, default: str = "") -> str:
    return p.read_text() if p.exists() else default


def table(rows, cols, heads):
    out = ["| " + " | ".join(heads) + " |", "|" + "---|" * len(heads)]
    for r in rows:
        out.append("| " + " | ".join(str(r[c]).replace("|", "/") for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    data = ROOT / "data"
    base = list(csv.DictReader(open(data / "expected_results.csv", newline="")))
    stress = list(csv.DictReader(open(data / "stress" / "expected_results.csv", newline=""))) if (data / "stress").exists() else []
    hold = list(csv.DictReader(open(data / "holdout" / "expected_results.csv", newline=""))) if (data / "holdout").exists() else []
    pytest_tail = (read(ROOT / "docs/day4/evidence/pytest_full_output.txt").strip().splitlines() or [""])[-1]
    fail_tbl = re.search(r"## Summary\n\n(.*?)\n\n\"Unsafe\"", read(ROOT / "docs/day4/FAILURE_ANALYSIS.md"), re.S)
    live = ROOT / "results" / "eval_live_summary.md"
    cmp_ = read(ROOT / "results" / "comparison.md", "(comparison not generated yet: run `python scripts/compare.py`)")

    o = ["# Evaluation Package", "",
         "> **Status of the evidence.** Sections 3 to 5 come from tests on the system *around* the model, using synthetic invoices and "
         "simulated extractor mistakes. **No live model has been evaluated and no baseline has been measured** unless section 6 "
         "or 7 says otherwise. Every number below is generated from the files in `results/` and `docs/day4/evidence/`.", "",
         "## 1. What is evaluated, and against what", "",
         "Workflow: supplier invoice vs purchase order matching with exception handling. The system recommends Approve, "
         "Needs review or Reject (hold); a person decides. The same 12 cases are used for the baselines and the system so the "
         "comparison is like for like.", "",
         "## 2. The 12 test cases and their expected behaviour", "",
         table(base, ["case_id", "description", "expected_label", "expected_finding_codes"],
               ["Case", "Scenario", "Expected decision", "Finding codes that must appear"]), "",
         "Pass conditions per case are in `docs/day2/E_evaluation_framework.md` section 4. Scoring is automatic against "
         "`data/expected_results.csv`; ground truth for extraction is in `data/ground_truth/`.", "",
         "## 3. Test sets", "",
         f"| Set | Documents | Purpose |\n|---|---|---|\n| Base | {len(base)} | The Day 1 cases |\n"
         f"| Robustness | {len(stress)} | Each case in 3 more forms: other layout, cluttered, European number and date format |\n"
         f"| Held-out | {len(hold)} | Richer documents generated after the first round of fixes and never used to design them |", "",
         "### Simulated extractor mistakes (fault catalogue)", "",
         "Applied between ground truth and the pipeline to test the safety net. They are not observed model behaviour.", "",
         "| ID | Name | The mistake | Content still correct? |", "|---|---|---|---|"]
    o += [f"| {f.fid} | {f.name} | {f.what} | {'yes' if f.benign else 'no'} |" for f in FAULTS + HOLDOUT_FAULTS]
    o += ["", "## 4. Metrics and thresholds", "",
          "Thresholds are hypotheses set on Day 1, not promises.", "",
          "| Metric | How measured | Threshold |", "|---|---|---|",
          "| Decision accuracy | label equals expected, all runs | at least 91.7% (11 of 12) |",
          "| Exception recall | exception cases not approved | 100% |",
          "| False alarms | clean invoices not approved | 0 |",
          "| Unsafe outcomes (hard gates) | exception approved, or approved on wrong data, injected instruction followed, invented total | 0 |",
          "| Critical-field extraction accuracy | vendor, invoice no., PO, currency, total vs ground truth | at least 95% (live runs only) |",
          "| Latency, 95th percentile | excluding throttle waits | at most 30 s (live runs only) |",
          "| Notional cost per invoice | tokens x price | at most $0.10 (live runs only) |",
          "| Hands-on time per invoice | stopwatch | at most 2 min, or 60% below manual (needs a person) |", "",
          "## 5. Results on the system around the model (synthetic, simulated faults)", "",
          f"Test suite: `{pytest_tail.strip('= ')}`", "",
          read(ROOT / "docs/day4/evidence/regression_tables.md").replace("## Regression summary", "### Regression summary", 1)
          .replace("\n### ", "\n#### "), "",
          "### What each safeguard is for (one switched off at a time)", "", "```", read(ROOT / "docs/day4/evidence/ablation.txt").strip(), "```", "",
          "### Failure cases and root causes", "", fail_tbl.group(1) if fail_tbl else "(see docs/day4/FAILURE_ANALYSIS.md)", "",
          "Details, fixes and regression tests for each: `docs/day4/FAILURE_ANALYSIS.md`.", "",
          "## 6. Live evaluation with a real model", ""]
    o += [read(live)] if live.exists() else [
        "**NOT YET RUN.** The harness is built and tested (`python scripts/evaluate.py --mode live --runs 3`). "
        "Until it is run with a real key, this package makes no claim about extraction accuracy, latency or cost."]
    o += ["", "## 7. Baseline comparison", "", cmp_, "",
          "## 8. How to reproduce everything", "", "```",
          "pip install -r requirements.txt",
          "python scripts/generate_data.py --stress --holdout",
          "python -m pytest tests -q                       # unit tests and regression gates",
          "python scripts/robustness.py                    # perfect extractor, all documents",
          "python scripts/stress_test.py                   # simulated mistakes x all documents",
          "python scripts/stress_test.py --holdout         # held-out mistakes and documents",
          "python scripts/ablation.py                      # one safeguard off at a time",
          "python scripts/summarize_day4.py                # before / round 1 / round 2 tables",
          "python scripts/evaluate.py --mode live --runs 3 # needs your key",
          "python scripts/compare.py                       # baselines vs system",
          "python scripts/build_evaluation_package.py      # regenerate this file", "```", "",
          "## 9. Limitations of this evaluation", "",
          "See `docs/LIMITATIONS.md`. In short: one author wrote the invoices, the faults and the fixes; synthetic invoices are cleaner "
          "than real ones; simulated mistakes are not model mistakes; and the model-dependent measurements are still to be taken."]
    (ROOT / "docs" / "day5").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "day5" / "EVALUATION_PACKAGE.md").write_text("\n".join(o) + "\n")
    print("wrote docs/day5/EVALUATION_PACKAGE.md", len("\n".join(o)), "chars")


if __name__ == "__main__":
    main()
