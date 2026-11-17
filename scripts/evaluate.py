"""Full-test-set evaluation with the metrics from the evaluation framework (E document).

  python scripts/evaluate.py --mode live --runs 3 --price-in 0.15 --price-out 0.75      # YOU run this (needs LLM_API_KEY)
  python scripts/evaluate.py --mode mock                                                 # deterministic code only
  python scripts/evaluate.py --mode live --include-stress --runs 1                       # also the 48 harder documents

--price-in / --price-out are dollars per MILLION tokens from your provider's price page (look it up on the day;
free-tier usage is $0 but the notional price shows what the same workload would cost).
Each run uses an isolated copy of the seeded data, no cache, and the free-tier throttle built into the provider.
Results: results/eval_<mode>_runs.csv and results/eval_<mode>_summary.md
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ap.config import Settings                                  # noqa: E402
from ap.extraction.factory import build_provider                # noqa: E402
from ap.extraction.mock import MockProvider                     # noqa: E402
from evalkit.metrics import markdown, summarize                 # noqa: E402
from evalkit.runner import load_expected, run_one               # noqa: E402


def case_sets(data: Path, include_stress: bool):
    sets = [(r, data / r["invoice_file"], data / "ground_truth") for r in load_expected(data / "expected_results.csv")]
    if include_stress:
        for sub in ("stress", "holdout"):
            f = data / sub / "expected_results.csv"
            if f.exists():
                sets += [(r, data / r["invoice_file"], data / sub / "ground_truth") for r in load_expected(f)]
    return sets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["live", "mock", "ground_truth"], default="mock")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--data", default="data")
    ap.add_argument("--include-stress", action="store_true")
    ap.add_argument("--price-in", type=float)
    ap.add_argument("--price-out", type=float)
    a = ap.parse_args()
    data = Path(a.data)
    settings = Settings.from_env()
    if a.mode == "live":
        if not settings.api_key:
            print("LLM_API_KEY is not set (put it in .env). Use --mode mock to test without a key."); return 2
        provider = build_provider(settings, "live")
    sets = case_sets(data, a.include_stress)
    print(f"{len(sets)} documents x {a.runs} run(s), mode={a.mode}, model={settings.model if a.mode == 'live' else 'n/a'}")
    rows = []
    for run in range(1, a.runs + 1):
        for r, pdf, gtdir in sets:
            truth = json.loads((gtdir / f"{r['case_id']}.json").read_text())
            if a.mode == "live":
                prov, override, m = provider, None, "live"
            elif a.mode == "mock":
                prov, override, m = MockProvider(gtdir), None, "mock"
            else:
                prov, override, m = None, truth, "mock"
            row = run_one(r, pdf, truth, data, provider=prov, mode=m, override=override,
                          tag={"run": run, "base_case": r.get("base_case", r["case_id"]), "variant": r.get("variant", "base"),
                               "source": a.mode, "endpoint": settings.base_url if a.mode == "live" else "",
                               "model": settings.model if a.mode == "live" else ""})
            rows.append(row)
            print(f"  run {run} {row['case']:<16} expected={row['expected']:<13} got={row['got']:<13} {row['outcome']:<20} conf={row['confidence']}")
    stem = f"eval_{a.mode}"
    (ROOT / "results").mkdir(exist_ok=True)
    with open(ROOT / "results" / f"{stem}_runs.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=sorted({k for r in rows for k in r})); w.writeheader(); w.writerows(rows)
    m = summarize(rows, a.price_in, a.price_out)
    md = markdown(m, a.mode, rows, endpoint=settings.base_url if a.mode == "live" else "", model=settings.model if a.mode == "live" else "")
    (ROOT / "results" / f"{stem}_summary.md").write_text(md)
    print("\n" + md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
