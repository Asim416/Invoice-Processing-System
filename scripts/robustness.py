"""Robustness set with a PERFECT extractor: does the document alone (layout, clutter, number format) change the outcome?

  python scripts/robustness.py --tag after

Any non-CORRECT result here is caused by the pipeline (PDF text, grounding, rules), not by a model.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from evalkit.runner import load_expected, run_one   # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()
    data = Path(a.data)
    rows = []
    sets = [(r, data / r["invoice_file"], data / "ground_truth", "base") for r in load_expected(data / "expected_results.csv")]
    st = data / "stress"
    sets += [(r, data / r["invoice_file"], st / "ground_truth", r["variant"]) for r in load_expected(st / "expected_results.csv")]
    for r, pdf, gtdir, variant in sets:
        truth = json.loads((gtdir / f"{r['case_id']}.json").read_text())
        rows.append(run_one(r, pdf, truth, data, provider=None, mode="ground_truth", override=truth,
                            tag={"variant": variant, "base_case": r.get("base_case", r["case_id"])}))
    out = ROOT / "results" / f"day4_{a.tag}_robustness.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r})); w.writeheader(); w.writerows(rows)
    by = defaultdict(Counter)
    for r in rows:
        by[r["variant"]][r["outcome"]] += 1
    classes = sorted({o for c in by.values() for o in c})
    print(f"{'variant':<12}" + "".join(f"{c[:14]:>16}" for c in classes) + "   runs")
    for v in ["base", "altlayout", "noisy", "eu"]:
        print(f"{v:<12}" + "".join(f"{by[v][c]:>16}" for c in classes) + f"   {sum(by[v].values())}")
    bad = [r for r in rows if r["outcome"] != "CORRECT" or not r["codes_ok"]]
    print(f"\nnot fully correct: {len(bad)} of {len(rows)}")
    for r in bad[:50]:
        print(f"  {r['case']:<16} {r['outcome']:<22} expected={r['expected']:<13} got={r['got']:<13} conf={r['confidence']:<6} codes={r['codes']}")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
