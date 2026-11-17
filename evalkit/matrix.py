"""The fault-injection matrix as a reusable function (used by stress_test.py, ablation.py and the tests)."""
from __future__ import annotations

import json
from pathlib import Path

from evalkit.faults import FAULTS, HOLDOUT_FAULTS, FaultyProvider
from evalkit.runner import load_expected, run_one


def _cases(data: Path, holdout: bool):
    if holdout:
        hd = data / "holdout"
        return [dict(r, _pdf=data / r["invoice_file"], _gt=hd / "ground_truth") for r in load_expected(hd / "expected_results.csv")]
    base = [dict(r, base_case=r["case_id"], variant="base", _pdf=data / r["invoice_file"], _gt=data / "ground_truth")
            for r in load_expected(data / "expected_results.csv")]
    st = data / "stress"
    extra = [dict(r, _pdf=data / r["invoice_file"], _gt=st / "ground_truth") for r in load_expected(st / "expected_results.csv")] \
        if st.exists() else []
    return base + extra


def run_matrix(data: Path, *, holdout: bool = False, transient: bool = False, only: set[str] | None = None,
               policy=None) -> list[dict]:
    mdir = data / ("holdout" if holdout else "stress")
    meta = json.loads((mdir / "meta.json").read_text()) if (mdir / "meta.json").exists() else {}
    rows = []
    for f in (HOLDOUT_FAULTS if holdout else FAULTS):
        if only and f.fid not in only:
            continue
        for c in _cases(data, holdout):
            gt_dirs = [c["_gt"], data / "ground_truth"]
            prov = FaultyProvider(f, gt_dirs, meta.get(c["case_id"], {}), persist=not transient)
            if not prov.applicable(c["case_id"]):
                continue
            truth = json.loads(next(d / f"{c['case_id']}.json" for d in gt_dirs if (d / f"{c['case_id']}.json").exists()).read_text())
            rows.append(run_one(c, c["_pdf"], truth, data, provider=prov, mode="live", policy=policy,
                                tag={"fault": f.fid, "fault_name": f.name, "variant": c["variant"],
                                     "base_case": c["base_case"], "transient": transient},
                                fault_applied=True, benign=f.benign))
    return rows


UNSAFE = ("CRITICAL_MISS", "WRONG_DATA_APPROVED")


def unsafe(rows):
    return [r for r in rows if r["outcome"] in UNSAFE]
