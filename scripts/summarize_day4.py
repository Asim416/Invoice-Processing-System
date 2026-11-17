"""Builds the before / round 1 / round 2 comparison tables from the saved result CSVs (no hand-typed numbers)."""
from __future__ import annotations

import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"
STAGES = [("before", "Day 3 code"), ("round1", "Hardening round 1"), ("round2", "Hardening round 2")]
UNSAFE = ("CRITICAL_MISS", "WRONG_DATA_APPROVED")


def load(stage, kind):
    p = R / f"day4_{stage}_{kind}.csv"
    return list(csv.DictReader(open(p, newline=""))) if p.exists() else None


def pct(a, b):
    return f"{a} / {b}" if b else "n/a"


def pctile(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))] if vals else float("nan")


def main():
    out = []
    w = out.append
    w("## Regression summary: the same experiments on three versions of the code\n")
    w("All runs use synthetic invoices. Fault-injection runs use SIMULATED model errors; robustness runs use a perfect extractor.\n")
    w("| Experiment | Measure | " + " | ".join(n for _, n in STAGES) + " |")
    w("|---|---|" + "---|" * len(STAGES))
    for kind, label in (("faults", "Fault matrix (18 fault types x 48 documents)"), ("holdout", "Held-out faults (7 new types x 12 richer documents)")):
        data = [load(s, kind) for s, _ in STAGES]
        if not all(data):
            continue
        for name, f in (("runs", lambda r: len(r)),
                        ("unsafe (approved wrongly or on wrong data)", lambda r: sum(x["outcome"] in UNSAFE for x in r)),
                        ("  of which carried 'high' confidence", lambda r: sum(x["outcome"] in UNSAFE and x["confidence"] == "high" for x in r)),
                        ("false alarms (clean invoice flagged for no reason)", lambda r: sum(x["outcome"] == "FALSE_ALARM" for x in r)),
                        ("detected (clean invoice flagged because data was corrupted)", lambda r: sum(x["outcome"] == "DETECTED" for x in r)),
                        ("under-flag (Reject downgraded to Needs review)", lambda r: sum(x["outcome"] == "UNDER_FLAG" for x in r))):
            w(f"| {label} | {name} | " + " | ".join(str(f(d)) for d in data) + " |")
    rob = [load(s, "robustness") for s, _ in STAGES]
    if all(rob):
        w("| Robustness (perfect extractor, 48 documents) | documents handled exactly as expected | " +
          " | ".join(pct(sum(x["outcome"] == "CORRECT" and x["codes_ok"] == "True" for x in d), len(d)) for d in rob) + " |")
        for v in ("eu",):
            w(f"| Robustness | European-format documents correct | " +
              " | ".join(pct(sum(x["variant"] == v and x["outcome"] == "CORRECT" and x["codes_ok"] == "True" for x in d),
                             sum(x["variant"] == v for x in d)) for d in rob) + " |")
    out.append("")
    w("### Unsafe outcomes by fault type (before / round 1 / round 2)\n")
    w("| Fault | Plain description | before | round 1 | round 2 |")
    w("|---|---|---|---|---|")
    from evalkit.faults import FAULT_BY_ID
    counts = {}
    for kind in ("faults", "holdout"):
        for s, _ in STAGES:
            d = load(s, kind)
            if d:
                for x in d:
                    if x["outcome"] in UNSAFE:
                        counts[(x["fault"], s)] = counts.get((x["fault"], s), 0) + 1
    for fid in sorted({k[0] for k in counts}):
        w(f"| {fid} {FAULT_BY_ID[fid].name} | {FAULT_BY_ID[fid].what} | " + " | ".join(str(counts.get((fid, s), 0)) for s, _ in STAGES) + " |")
    out.append("")
    r2 = load("round2", "robustness")
    f2 = load("round2", "faults")
    if r2:
        ms = [float(x["ms"]) for x in r2]
        w("### Latency of the deterministic pipeline (no LLM call), this machine\n")
        w(f"- Robustness set, {len(ms)} runs: median {statistics.median(ms):.0f} ms, 95th percentile {pctile(ms, .95):.0f} ms, max {max(ms):.0f} ms.")
    if f2:
        ms = [float(x["ms"]) for x in f2]
        w(f"- Fault matrix, {len(ms)} runs: median {statistics.median(ms):.0f} ms, 95th percentile {pctile(ms, .95):.0f} ms.")
        w("- These exclude the model call, which is typically the dominant cost. Real latency needs live runs.\n")
    w("### Confidence as a warning signal\n")
    for s, n in STAGES:
        d = (load(s, "faults") or []) + (load(s, "holdout") or [])
        u = [x for x in d if x["outcome"] in UNSAFE]
        w(f"- {n}: {len(u)} unsafe runs; confidence at the time: {dict(Counter(x['confidence'] for x in u)) or 'none'}")
    print("\n".join(out))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()
