"""Before-and-after comparison: Baseline A (manual) vs Baseline B (simple prompt) vs the system.

  python scripts/compare.py --init     # writes the blank Baseline A template and explains Baseline B
  python scripts/compare.py            # reads whatever you have filled in; anything missing stays [MEASURE]

Inputs (all optional):
  results/baseline_A_manual.csv       case_id, minutes_hands_on, decision, notes          (you, doing it by hand)
  results/baseline_B_responses.csv    filled by you after scripts/baseline_prompt.py
  results/eval_live_runs.csv          from: python scripts/evaluate.py --mode live
  results/system_review_times.csv     case_id, minutes_hands_on  (your timed review of the system's output)
Output: results/comparison.md
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"
LABELS = {"approve": "Approve", "needs review": "Needs review", "reject (hold)": "Reject (hold)", "reject": "Reject (hold)",
          "hold": "Reject (hold)", "review": "Needs review"}
M = "[MEASURE]"


def read(p: Path):
    return list(csv.DictReader(open(p, newline=""))) if p.exists() else None


def norm_label(x: str):
    return LABELS.get((x or "").strip().lower())


def num(x):
    try:
        return float(str(x).replace(",", "."))
    except ValueError:
        return None


def score(pairs, per_run: int = 1):
    """pairs: list of (expected, got). Returns the four decision metrics averaged per run of the 12 cases."""
    pairs = [(e, g) for e, g in pairs if g]
    if not pairs:
        return None
    n = len(pairs) / per_run
    ok = sum(e == g for e, g in pairs) / per_run
    exc = [(e, g) for e, g in pairs if e != "Approve"]
    cln = [(e, g) for e, g in pairs if e == "Approve"]
    return {"correct": ok, "n": n, "caught": sum(g != "Approve" for _, g in exc) / per_run, "exc_n": len(exc) / per_run,
            "false": sum(g != "Approve" for _, g in cln) / per_run, "cln_n": len(cln) / per_run,
            "critical": sum(g == "Approve" for _, g in exc) / per_run}


def fmt(sc, key, nkey=None):
    if sc is None:
        return M
    v = sc[key]
    base = f"{v:.1f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return f"{base} / {int(sc[nkey])}" if nkey else base


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--init", action="store_true"); ap.add_argument("--data", default="data")
    a = ap.parse_args()
    data = Path(a.data)
    exp = {r["case_id"]: r["expected_label"] for r in csv.DictReader(open(data / "expected_results.csv", newline=""))}
    R.mkdir(exist_ok=True)
    if a.init:
        p = R / "baseline_A_manual.csv"
        if not p.exists():
            with open(p, "w", newline="") as fh:
                w = csv.writer(fh); w.writerow(["case_id", "minutes_hands_on", "decision", "notes"])
                for c in exp:
                    w.writerow([c, "", "", ""])
        print("Baseline A template: results/baseline_A_manual.csv. For each invoice: open it, use ONLY a spreadsheet, a PDF viewer and "
              "a calculator, time yourself from opening the invoice to having a decision (and a vendor note if needed), "
              "and write down Approve / Needs review / Reject (hold).\nBaseline B: python scripts/baseline_prompt.py --print")
        return 0

    A = read(R / "baseline_A_manual.csv"); B = read(R / "baseline_B_responses.csv")
    S = read(R / "eval_live_runs.csv"); T = read(R / "system_review_times.csv")
    a_sc = score([(exp[r["case_id"]], norm_label(r["decision"])) for r in A or [] if r["case_id"] in exp]) if A else None
    b_rows = [r for r in B or [] if norm_label(r.get("your_label", ""))]
    runs_b = len({r["run"] for r in b_rows}) or 1
    b_sc = score([(exp[r["case_id"]], norm_label(r["your_label"])) for r in b_rows if r["case_id"] in exp], runs_b) if b_rows else None
    s_sc, warn = None, []
    if S:
        base = [r for r in S if r["case"] in exp]
        local = any(h in (r.get("endpoint") or "") for r in base[:1] for h in ("127.0.0.1", "localhost"))
        not_live = base and base[0].get("source") not in ("live",)
        runs_s = len({r.get("run", "1") for r in base}) or 1
        s_sc = score([(r["expected"], r["got"]) for r in base], runs_s)
        if not_live:
            warn.append("results/eval_live_runs.csv was not produced by a live run: it must not be used as LLM evidence.")
        if local:
            warn.append("The system column comes from a LOCAL endpoint (a stand-in server or a local model). Only report it as "
                        "LLM accuracy if it was a real local model such as Ollama.")
    mins = lambda rows, col="minutes_hands_on": (statistics.mean(v for v in (num(r.get(col)) for r in rows) if v is not None)
                                                  if rows and any(num(r.get(col)) is not None for r in rows) else None)
    ma, mb, mt = mins(A or []), mins(b_rows), mins(T or [])
    inv = [r for r in b_rows if (r.get("invented_facts") or "").strip().lower() in ("yes", "no")]
    inv_n = sum((r["invented_facts"].strip().lower() == "yes") for r in inv) / runs_b if inv else None
    vs = lambda rows: (statistics.mean(v for v in (num(r.get("vendor_message_score")) for r in rows) if v is not None)
                       if any(num(r.get("vendor_message_score")) is not None for r in rows) else None)
    f1 = lambda v: M if v is None else f"{v:.1f}"
    red = "-" if (ma is None or mt is None or ma == 0) else f"{100 * (ma - mt) / ma:.0f}%"
    out = ["# Baseline vs system comparison\n"] + [f"**WARNING: {w}**\n" for w in warn] + [
           "Cells that say [MEASURE] have not been measured yet. Nothing here is estimated.\n",
           f"Sources found: Baseline A {'yes' if a_sc else 'no (template not filled)'}, Baseline B {'yes' if b_rows else 'no'} (scored rows: {len(b_rows)}), "
           f"live system runs {'yes' if S else 'no'}, system review times {'yes' if T else 'no'}.\n",
           "| Metric | Baseline A: manual | Baseline B: simple prompt | System (live run) |", "|---|---|---|---|",
           f"| Decisions correct (of 12, averaged per run) | {fmt(a_sc, 'correct', 'n')} | {fmt(b_sc, 'correct', 'n')} | {fmt(s_sc, 'correct', 'n')} |",
           f"| Exceptions caught (of 9) | {fmt(a_sc, 'caught', 'exc_n')} | {fmt(b_sc, 'caught', 'exc_n')} | {fmt(s_sc, 'caught', 'exc_n')} |",
           f"| Clean invoices wrongly flagged (of 3) | {fmt(a_sc, 'false', 'cln_n')} | {fmt(b_sc, 'false', 'cln_n')} | {fmt(s_sc, 'false', 'cln_n')} |",
           f"| Critical misses (an exception approved) | {fmt(a_sc, 'critical')} | {fmt(b_sc, 'critical')} | {fmt(s_sc, 'critical')} |",
           f"| Average hands-on minutes per invoice | {f1(ma)} | {f1(mb)} | {f1(mt)} (timed review of system output) |",
           f"| Hands-on time change vs Baseline A | n/a | {'-' if (ma is None or mb is None or ma == 0) else f'{100 * (ma - mb) / ma:.0f}%'} | {red} |",
           f"| Cases with invented facts (per run) | n/a | {f1(inv_n)} | 0 by construction (templates), verified by an automated check |",
           f"| Average vendor message score (0 to 2) | {M} (you score what you wrote) | {f1(vs(b_rows))} | {M} (score the template emails) |"]
    (R / "comparison.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
