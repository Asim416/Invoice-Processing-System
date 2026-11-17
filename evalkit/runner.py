"""Run one invoice through the pipeline in isolation and describe the outcome."""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from ap.config import Policy, Settings
from ap.pipeline import Pipeline
from ap.schemas import ErrorResponse
from ap.storage import CsvStorage
from ap.validation import norm

RANK = {"Approve": 0, "Needs review": 1, "Reject (hold)": 2}
REFERENCE_FILES = ("pos.csv", "po_lines.csv", "processed_invoices.csv")
CRITICAL = ("vendor_name", "invoice_number", "po_number", "currency", "total")


def load_expected(path: Path) -> list[dict]:
    return list(csv.DictReader(open(path, newline="")))


def classify(expected: str, got: str, codes_ok: bool, *, data_ok: bool = True, fault_applied: bool = False,
             benign: bool = False) -> str:
    """Outcome classes. Unsafe ones are CRITICAL_MISS (approved what must not be) and WRONG_DATA_APPROVED
    (approved while the extracted data was wrong, even if the label happens to match).
      CORRECT        label as expected
      DETECTED       a fault corrupted the data and the system flagged a clean invoice (the desired behaviour)
      FALSE_ALARM    a clean invoice was flagged although nothing was wrong (avoidable review work)
      UNDER_FLAG     less strict than expected but still not Approve (Reject -> Needs review)
      OVER_FLAG      stricter than expected (Needs review -> Reject)
    """
    if got == "ERROR":
        return "ERROR"
    if got == "Approve":
        if expected != "Approve":
            return "CRITICAL_MISS"
        return "CORRECT" if data_ok else "WRONG_DATA_APPROVED"
    if got == expected:
        return "CORRECT"
    if expected == "Approve":
        return "DETECTED" if (fault_applied and not benign) else "FALSE_ALARM"
    return "UNDER_FLAG" if RANK[got] < RANK[expected] else "OVER_FLAG"


def field_accuracy(extracted, truth: dict) -> dict:
    """Per-field correctness of the 5 critical fields against ground truth (None extraction = all wrong)."""
    exp = {"vendor_name": truth["vendor_name"], "invoice_number": truth["invoice_number"],
           "po_number": truth["po_number"], "currency": truth["currency"],
           "total": None if truth["total"] is None else Decimal(str(truth["total"])).quantize(Decimal("0.01"))}
    out = {}
    for k in CRITICAL:
        got = getattr(extracted, k, None) if extracted is not None else "<<none>>"
        if k in ("vendor_name", "invoice_number", "po_number"):
            ok = (got is None and exp[k] is None) or (got not in (None, "<<none>>") and exp[k] is not None
                                                      and norm(str(got)) == norm(str(exp[k])))
        else:
            ok = got == exp[k] if got != "<<none>>" else False
        out[k] = bool(ok)
    return out


def run_one(row: dict, pdf: Path, truth: dict, data_root: Path, *, provider, mode: str, override: Optional[dict] = None,
            policy: Optional[Policy] = None, tag: dict | None = None, fault_applied: bool = False, benign: bool = False) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "data").mkdir()
        for f in REFERENCE_FILES:
            shutil.copy(data_root / f, tmp / "data" / f)
        settings = Settings.from_env(data_dir=tmp / "data", logs_dir=tmp / "logs", cache_dir=tmp / "cache",
                                     extraction_mode=mode, api_key="not-a-real-key")
        pipe = Pipeline(settings, policy or Policy.load(), CsvStorage(tmp / "data", tmp / "logs"), provider, mode)
        res = pipe.process_file(pdf, use_cache=False, extraction_override=override)
    base = {"case": row["case_id"], "expected": row["expected_label"], **(tag or {})}
    if isinstance(res, ErrorResponse):
        return {**base, "got": "ERROR", "outcome": "ERROR", "codes": "", "codes_ok": False, "error": res.error_code.value,
                "confidence": "", "attempts": "", "ms": 0, "wait_ms": 0, "tokens": 0, "email": False}
    got_codes = {f.code.value for f in res.findings}
    exp_codes = set(filter(None, row["expected_finding_codes"].split(";")))
    codes_ok = exp_codes <= got_codes
    acc = field_accuracy(res.extracted, truth)
    date_ok = res.extracted is not None and ((res.extracted.invoice_date.isoformat() if res.extracted.invoice_date else None)
                                              == truth["invoice_date"])
    data_ok = all(acc.values()) and date_ok
    return {**base, "got": res.label.value, "data_ok": data_ok, "ok_invoice_date": date_ok,
            "outcome": classify(row["expected_label"], res.label.value, codes_ok, data_ok=data_ok,
                                fault_applied=fault_applied, benign=benign),
            "codes": ";".join(sorted(got_codes)), "codes_ok": codes_ok,
            "error": res.error.error_code.value if res.error else "", "confidence": res.validation.confidence,
            "attempts": res.validation.attempts, "ms": res.timings_ms["total"], "wait_ms": res.timings_ms["rate_limit_wait"],
            "tokens": (res.token_usage or {}).get("total_tokens", 0),
            "tokens_in": (res.token_usage or {}).get("prompt_tokens", 0),
            "tokens_out": (res.token_usage or {}).get("completion_tokens", 0), "email": bool(res.vendor_email),
            "extracted_none": res.extracted is None, **{f"ok_{k}": v for k, v in acc.items()},
            "total_value": str(res.extracted.total) if res.extracted is not None and res.extracted.total is not None else "",
            "suspicious": "SUSPICIOUS_TEXT" in got_codes}
