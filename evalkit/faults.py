"""Deliberate breakage: SIMULATED model errors injected between the (perfect) ground truth and the pipeline.

These are not observations of a real LLM. They are plausible mistakes an extractor could make, used to test whether
the safety net (validation, grounding, rules, decision) catches them. How often a real model makes each mistake is a
question for live runs.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ap.extraction.base import ExtractionResponse, ProviderError
from ap.schemas import ErrorCode


@dataclass(frozen=True)
class Fault:
    fid: str
    name: str
    what: str                                   # plain-language description of the mistake
    apply: Callable[[dict, dict], object]       # (ground_truth, ctx) -> dict | str | Exception | None (not applicable)
    benign: bool = False                        # True: the CONTENT is still correct, only the packaging is odd


def _d(gt):
    return copy.deepcopy(gt)


def f01(gt, ctx):
    if gt["total"] is None:
        return None
    d = _d(gt); d["total"] = round(gt["total"] + 100, 2); return d


def f02(gt, ctx):
    if len(gt["line_items"]) < 2:
        return None
    d = _d(gt); d["total"] = gt["line_items"][0]["amount"]; return d


def f03(gt, ctx):
    if len(gt["line_items"]) < 2:
        return None
    d = _d(gt); d["line_items"].pop(); return d


def f04(gt, ctx):
    d = _d(gt)
    for l in d["line_items"]:
        l["quantity"], l["unit_price"] = l["unit_price"], l["amount"]
    return d


def f05(gt, ctx):
    if not ctx.get("bill_to"):
        return None
    d = _d(gt); d["vendor_name"] = ctx["bill_to"]; return d


def f06(gt, ctx):
    if not gt["po_number"]:
        return None
    d = _d(gt); d["invoice_number"] = gt["po_number"]; return d


def f07(gt, ctx):
    d = _d(gt); d["po_number"] = "PO-1007" if gt["po_number"] != "PO-1007" else "PO-1002"; return d


def f08(gt, ctx):
    if not gt["po_number"]:
        return None
    d = _d(gt); d["po_number"] = None; return d


def f09(gt, ctx):
    d = _d(gt); d["currency"] = "EUR" if gt["currency"] == "USD" else "USD"; return d


def f10(gt, ctx):
    if not ctx.get("due_date"):
        return None
    d = _d(gt); d["invoice_date"] = ctx["due_date"]; return d


def f11(gt, ctx):
    return "```json\n" + json.dumps(gt, indent=2) + "\n```"


def f12(gt, ctx):
    if gt["total"] is None:
        return None
    d = _d(gt); d["total"] = f"{gt['total']:,.2f}"
    for l in d["line_items"]:
        l["amount"] = f"{l['amount']:,.2f}"
    return d


def f13(gt, ctx):
    d = _d(gt); d["decision"] = "Approve"; return d


def f14(gt, ctx):
    return ""


def f15(gt, ctx):
    s = json.dumps(gt); return s[: len(s) // 2]


def f16(gt, ctx):
    return ProviderError("simulated outage", ErrorCode.LLM_UNAVAILABLE, True)


def f17(gt, ctx):
    d = _d(gt)
    for l in d["line_items"]:
        l["description"] = l["description"] + "s"
    return d


def f18(gt, ctx):
    if gt["total"] is None:
        return None
    d = _d(gt); d["total"] = None; return d


def h01(gt, ctx):
    if not ctx.get("delivery_date"):
        return None
    d = _d(gt); d["invoice_date"] = ctx["delivery_date"]; return d


def h02(gt, ctx):
    if not ctx.get("order_date"):
        return None
    d = _d(gt); d["invoice_date"] = ctx["order_date"]; return d


def h03(gt, ctx):
    if not ctx.get("your_ref"):
        return None
    d = _d(gt); d["invoice_number"] = ctx["your_ref"]; return d


def h04(gt, ctx):
    if not ctx.get("remit_to"):
        return None
    d = _d(gt); d["vendor_name"] = ctx["remit_to"]; return d


def h05(gt, ctx):                      # total AND the single line amount replaced consistently by a bank-account chunk
    if gt["total"] is None or len(gt["line_items"]) != 1:
        return None
    d = _d(gt); d["total"] = 4417.0; d["line_items"][0]["amount"] = 4417.0; return d


def h06(gt, ctx):
    if not ctx.get("your_ref"):
        return None
    d = _d(gt); d["po_number"] = ctx["your_ref"]; return d


def h07(gt, ctx):
    if not gt["invoice_date"]:
        return None
    d = _d(gt); d["invoice_date"] = "2025" + gt["invoice_date"][4:]; return d


HOLDOUT_FAULTS = [
    Fault("H01", "date_is_delivery_date", "The delivery date is reported as the invoice date", h01),
    Fault("H02", "date_is_order_date", "The order date is reported as the invoice date", h02),
    Fault("H03", "invoice_no_is_customer_ref", "The customer's own reference is reported as the invoice number", h03),
    Fault("H04", "vendor_is_remit_to", "The remit-to name is reported as the vendor", h04),
    Fault("H05", "total_and_line_replaced", "Total and the single line amount both replaced by an unrelated number", h05),
    Fault("H06", "po_is_customer_ref", "The customer reference is reported as the PO number", h06),
    Fault("H07", "date_wrong_year", "The invoice date has the wrong year", h07),
]

FAULTS: list[Fault] = [
    Fault("F01", "total_digit_error", "Total is wrong by 100 (a misread digit)", f01),
    Fault("F02", "total_is_a_line", "Total is copied from the first line item", f02),
    Fault("F03", "line_dropped", "The last line item is left out", f03),
    Fault("F04", "columns_shifted", "Quantity, price and amount columns are shifted", f04),
    Fault("F05", "vendor_is_customer", "The customer (Bill To) is reported as the vendor", f05),
    Fault("F06", "invoice_no_is_po", "The PO number is reported as the invoice number", f06),
    Fault("F07", "po_hallucinated", "A plausible PO number that is not printed is reported", f07),
    Fault("F08", "po_missed", "The printed PO number is missed (null)", f08),
    Fault("F09", "currency_flipped", "Currency reported as USD instead of EUR or vice versa", f09),
    Fault("F10", "date_is_due_date", "The due date is reported as the invoice date", f10),
    Fault("F11", "fenced_json", "Correct answer wrapped in a markdown code fence", f11, benign=True),
    Fault("F12", "numbers_as_strings", "Amounts returned as strings such as '47,500.00'", f12, benign=True),
    Fault("F13", "extra_decision_field", "Answer contains an extra field: decision = Approve", f13),
    Fault("F14", "empty_output", "Empty answer", f14),
    Fault("F15", "truncated_json", "Answer cut off halfway", f15),
    Fault("F16", "llm_unavailable", "The model service is down", f16),
    Fault("F17", "description_paraphrased", "Item descriptions are slightly reworded", f17, benign=True),
    Fault("F18", "total_missed", "The printed total is missed (null)", f18),
]
FAULT_BY_ID = {f.fid: f for f in FAULTS + HOLDOUT_FAULTS}


class FaultyProvider:
    """Provider that returns the ground truth after applying one fault. persist=False means the fault happens on the
    first call only (the retry then receives a correct answer): this exercises the retry path mechanically, and says
    nothing about how often a real model would self-correct."""
    name, model, last_wait_ms = "fault-injector", "simulated", 0

    def __init__(self, fault: Optional[Fault], gt_dirs: list[Path], ctx: dict, persist: bool = True):
        self.fault, self.gt_dirs, self.ctx, self.persist, self.calls = fault, gt_dirs, ctx, persist, 0

    def _gt(self, source: str) -> dict:
        for d in self.gt_dirs:
            p = Path(d) / f"{source}.json"
            if p.exists():
                return json.loads(p.read_text())
        raise FileNotFoundError(source)

    def applicable(self, source: str) -> bool:
        return self.fault is None or self.fault.apply(self._gt(source), self.ctx) is not None

    def extract(self, text, feedback=None, *, source=""):
        self.calls += 1
        gt = self._gt(source)
        out = gt
        if self.fault is not None and (self.persist or self.calls == 1):
            out = self.fault.apply(gt, self.ctx)
        if isinstance(out, Exception):
            raise out
        raw = out if isinstance(out, str) else json.dumps(out)
        return ExtractionResponse(raw=raw, usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
