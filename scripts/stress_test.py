"""Fault-injection matrix: break the extractor on purpose and see what the safety net does.

  python scripts/stress_test.py --tag after            # all faults x base + robustness set
  python scripts/stress_test.py --tag before --transient  # also repeat each fault as first-attempt-only

Everything here is SIMULATED model error on SYNTHETIC invoices; it measures the code's safety net, not an LLM.
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
from ap.config import Policy                        # noqa: E402
from evalkit.faults import FAULTS, HOLDOUT_FAULTS, FaultyProvider   # noqa: E402
from evalkit.matrix import run_matrix                # noqa: E402

CLASSES = ["CORRECT", "DETECTED", "FALSE_ALARM", "UNDER_FLAG", "OVER_FLAG", "CRITICAL_MISS", "WRONG_DATA_APPROVED", "ERROR"]


def holdout_cases(data: Path):
    hd = data / "holdout"
    return [dict(r, _pdf=data / r["invoice_file"], _gt=hd / "ground_truth") for r in load_expected(hd / "expected_results.csv")]


def cases(data: Path):
    base = [dict(r, base_case=r["case_id"], variant="base", _pdf=data / r["invoice_file"],
                 _gt=data / "ground_truth") for r in load_expected(data / "expected_results.csv")]
    st = data / "stress"
    extra = []
    if st.exists():
        extra = [dict(r, _pdf=data / r["invoice_file"], _gt=st / "ground_truth")
                 for r in load_expected(st / "expected_results.csv")]
    return base + extra


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--transient", action="store_true", help="faults on the first attempt only (tests the retry path)")
    ap.add_argument("--no-stress-set", action="store_true")
    ap.add_argument("--only-faults", default="")
    ap.add_argument("--holdout", action="store_true", help="run the HELD-OUT faults on the HELD-OUT documents")
    a = ap.parse_args()
    data = Path(a.data)
    wanted = set(filter(None, a.only_faults.split(",")))
    rows = run_matrix(data, holdout=a.holdout, transient=a.transient, only=wanted)
    out = ROOT / "results" / f"day4_{a.tag}_{'holdout' if a.holdout else 'faults'}{'_transient' if a.transient else ''}.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r})); w.writeheader(); w.writerows(rows)
    by = defaultdict(Counter)
    for r in rows:
        by[(r["fault"], r["fault_name"])][r["outcome"]] += 1
    print(f"{'fault':<30}" + "".join(f"{c[:10]:>11}" for c in CLASSES) + "   runs")
    tot = Counter()
    for (fid, name), cnt in sorted(by.items()):
        print(f"{fid + ' ' + name:<30}" + "".join(f"{cnt[c]:>11}" for c in CLASSES) + f"   {sum(cnt.values())}")
        tot.update(cnt)
    print(f"{'TOTAL':<30}" + "".join(f"{tot[c]:>11}" for c in CLASSES) + f"   {sum(tot.values())}")
    unsafe = [r for r in rows if r["outcome"] in ("CRITICAL_MISS", "WRONG_DATA_APPROVED")]
    print(f"\nUNSAFE runs (approved what must not be, or approved on wrong data): {len(unsafe)}"
          f"   confidence at the time: {dict(Counter(r['confidence'] for r in unsafe))}")
    for r in unsafe[:60]:
        print(f"  {r['fault']} {r['case']:<16} {r['outcome']:<20} expected={r['expected']:<13} got={r['got']:<9} conf={r['confidence']}")
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
