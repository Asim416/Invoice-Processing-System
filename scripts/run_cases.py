"""Run TC01-TC12 through the pipeline and compare with expected_results.csv.

--mode ground_truth : feeds the known-correct extraction straight in (tests rules/decisions/templates; NOT an extraction test)
--mode mock         : reads the fixture extraction but runs real PDF text, validation and grounding (still NOT an LLM test)
--mode live         : calls the configured LLM (run this yourself; needs LLM_API_KEY)

Each run uses an isolated copy of the seeded data and a fresh log, so duplicate checks cannot be polluted.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ap.config import Policy, Settings                      # noqa: E402
from ap.extraction.factory import build_provider            # noqa: E402
from ap.pipeline import Pipeline                            # noqa: E402
from ap.schemas import ErrorResponse                        # noqa: E402
from ap.storage import CsvStorage                           # noqa: E402


def run(mode: str, data: Path, runs: int = 1, no_cache: bool = True):
    expected = list(csv.DictReader(open(data / "expected_results.csv", newline="")))
    out = []
    for r in range(1, runs + 1):
        for row in expected:
            with tempfile.TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                shutil.copytree(data, tmp / "data")
                settings = Settings.from_env(data_dir=tmp / "data", logs_dir=tmp / "logs",
                                             cache_dir=tmp / "cache")
                storage = CsvStorage(tmp / "data", tmp / "logs")
                provider = build_provider(settings, "live" if mode == "live" else "mock", data / "ground_truth") \
                    if mode != "ground_truth" else None
                pipe = Pipeline(settings, Policy.load(), storage, provider, "live" if mode == "live" else "mock")
                pdf = tmp / "data" / row["invoice_file"]
                override = None
                if mode == "ground_truth":
                    override = json.loads((tmp / "data" / "ground_truth" / f"{row['case_id']}.json").read_text())
                res = pipe.process_file(pdf, use_cache=not no_cache, extraction_override=override)
            if isinstance(res, ErrorResponse):
                out.append(dict(case=row["case_id"], run=r, expected=row["expected_label"], got="ERROR",
                                label_ok=False, codes_ok=False, codes="", error=res.error_code.value, ms=0))
                continue
            got_codes = {f.code.value for f in res.findings}
            exp_codes = set(filter(None, row["expected_finding_codes"].split(";")))
            out.append(dict(case=row["case_id"], run=r, expected=row["expected_label"], got=res.label.value,
                            label_ok=res.label.value == row["expected_label"], codes_ok=exp_codes <= got_codes,
                            codes=";".join(sorted(got_codes)), error=res.error.error_code.value if res.error else "",
                            ms=res.timings_ms["total"], tokens=(res.token_usage or {}).get("total_tokens", ""),
                            wait_ms=res.timings_ms["rate_limit_wait"], mode=res.extraction_mode,
                            confidence=res.validation.confidence, email=bool(res.vendor_email)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["ground_truth", "mock", "live"], default="ground_truth")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--data", default="data")
    ap.add_argument("--csv", help="write per-run results to this CSV")
    a = ap.parse_args()
    rows = run(a.mode, Path(a.data), a.runs)
    print(f"{'case':5} {'run':3} {'expected':14} {'got':14} label codes conf   email  ms")
    for r in rows:
        print(f"{r['case']:5} {r['run']:<3} {r['expected']:14} {r['got']:14} "
              f"{'PASS' if r['label_ok'] else 'FAIL'}  {'PASS' if r['codes_ok'] else 'FAIL'}  "
              f"{str(r.get('confidence','')):6} {str(r.get('email','')):5} {r['ms']}")
    n = len(rows)
    print(f"\nlabel correct: {sum(r['label_ok'] for r in rows)}/{n}   required codes present: {sum(r['codes_ok'] for r in rows)}/{n}")
    if a.csv:
        Path(a.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r})); w.writeheader(); w.writerows(rows)
    return 0 if all(r["label_ok"] and r["codes_ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
