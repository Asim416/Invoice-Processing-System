"""Ablation: switch ONE safeguard off at a time and count the unsafe outcomes the fault matrix produces.
A safeguard that matters shows up as unsafe outcomes when it is removed. Simulated faults, synthetic data.

  python scripts/ablation.py
"""
from __future__ import annotations

import functools
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import ap.pipeline as pl                                   # noqa: E402
import ap.rules as rules                                   # noqa: E402
from ap import decision                                    # noqa: E402
from ap.schemas import FindingCode, Label                  # noqa: E402
from evalkit.matrix import run_matrix, unsafe              # noqa: E402

DATA = ROOT / "data"
ORIG_VALIDATE, ORIG_EVALUATE, ORIG_DECIDE = pl.validate, pl.rules.evaluate, pl.decide


def configure(name: str):
    pl.validate, pl.rules.evaluate, pl.decide = ORIG_VALIDATE, ORIG_EVALUATE, ORIG_DECIDE
    flags = {"no grounding": "check_grounding", "no arithmetic": "check_arithmetic",
             "no cross-field checks": "check_consistency", "no label anchoring": "check_anchoring"}
    if name in flags:
        pl.validate = functools.partial(ORIG_VALIDATE, **{flags[name]: False})
    elif name == "no vendor-vs-PO check":
        pl.rules.evaluate = lambda inv, st, pol: [f for f in ORIG_EVALUATE(inv, st, pol) if f.code != FindingCode.VENDOR_MISMATCH]
    elif name == "no confidence gate":
        def lenient(findings, validation):
            validation = validation.model_copy(update={"confidence": "high", "passed": True})
            return ORIG_DECIDE(findings, validation)
        pl.decide = lenient


def main():
    configs = ["all safeguards on", "no grounding", "no arithmetic", "no cross-field checks", "no label anchoring",
               "no vendor-vs-PO check", "no confidence gate"]
    print(f"{'configuration':<26}{'unsafe (main)':>15}{'unsafe (held-out)':>19}{'total runs':>12}   which faults become unsafe")
    for name in configs:
        configure(name)
        a = run_matrix(DATA)
        b = run_matrix(DATA, holdout=True)
        faults = Counter(r["fault"] for r in unsafe(a) + unsafe(b))
        detail = ", ".join(f"{k}x{v}" for k, v in sorted(faults.items()))
        print(f"{name:<26}{len(unsafe(a)):>15}{len(unsafe(b)):>19}{len(a) + len(b):>12}   {detail}")
    configure("all safeguards on")


if __name__ == "__main__":
    main()
