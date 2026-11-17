"""Output rendering from per-exception templates. No LLM: text can only contain verified facts."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from string import Template
from typing import Optional

from ap.config import ROOT, Policy
from ap.fmt import money
from ap.schemas import ExtractedInvoice, Finding, FindingCode as C, Label, Severity, ValidationReport

TEMPLATE_DIR = ROOT / "templates"

# bullets that are safe and useful to send to a vendor (internal-only codes are excluded)
VENDOR_BULLETS = {
    C.AMOUNT_OVER_TOLERANCE: "The invoice total is {invoice_total} {cur} but the PO total is {po_total} {cur} (difference {difference}, {difference_pct:.2f}%).",
    C.UNIT_PRICE_MISMATCH: "Line '{line}': unit price {invoice_unit_price} on the invoice vs {po_unit_price} on the PO ({difference_pct:.2f}% {direction}).",
    C.QUANTITY_EXCEEDS_PO: "Line '{line}': invoice quantity {invoice_quantity} exceeds the PO quantity {po_quantity}.",
    C.LINE_NOT_ON_PO: "Line '{line}' does not appear on the purchase order.",
    C.CURRENCY_MISMATCH: "The invoice is in {invoice_currency} but the purchase order is in {po_currency}.",
    C.PO_NOT_FOUND: "We could not find purchase order {po_number}, which the invoice references.",
    C.PO_CLOSED: "Purchase order {po_number} is closed.",
    C.EXACT_DUPLICATE: "Our records show that invoice {invoice_number} was already received.",
    C.POSSIBLE_DUPLICATE: "This invoice has the same total and date as invoice {other_invoice_number}. Please confirm it is not a duplicate.",
}


def _load(name: str) -> Template:
    return Template((TEMPLATE_DIR / name).read_text())


def render_vendor_email(inv: Optional[ExtractedInvoice], findings: list[Finding], validation: ValidationReport) -> Optional[str]:
    """None unless extraction validated and there is at least one vendor-facing finding."""
    if inv is None or not validation.passed or not inv.vendor_name or not inv.invoice_number:
        return None
    if any(f.code == C.VENDOR_MISMATCH for f in findings):
        return None        # we are not sure who issued the invoice, so no message is addressed to anyone
    items = [f for f in findings if f.code in VENDOR_BULLETS]
    if not items:
        return None
    cur = inv.currency or ""
    bullets = "\n".join("- " + VENDOR_BULLETS[f.code].format(cur=cur, **f.evidence) for f in items)
    holding = any(f.severity == Severity.BLOCK for f in items)
    closing = ("We are holding this invoice until this is resolved." if holding
               else "Could you confirm the details or send a corrected invoice?")
    return _load("vendor_email.txt").substitute(
        invoice_number=inv.invoice_number, vendor_name=inv.vendor_name,
        date_clause=f" dated {inv.invoice_date.isoformat()}" if inv.invoice_date else "",
        bullets=bullets, closing=closing).strip()


def render_internal_note(label: Label, inv: Optional[ExtractedInvoice], findings: list[Finding],
                         validation: ValidationReport, policy: Policy) -> str:
    inv_no = inv.invoice_number if inv and inv.invoice_number else "(number not available)"
    vendor = inv.vendor_name if inv and inv.vendor_name else "(vendor not available)"
    po_ref = inv.po_number if inv and inv.po_number else "no PO number"
    block = "Findings:\n" + "\n".join(f"- [{f.severity.value}] {f.code.value}: {f.message}" for f in findings) \
        if findings else "No exceptions found; all checks passed."
    if validation.issues:
        block += "\nValidation issues:\n" + "\n".join(f"- {i}" for i in validation.issues)
    esc = ""
    thr = Decimal(str(policy.manager_escalation_threshold))
    if label != Label.APPROVE and inv and inv.total is not None and inv.total > thr:
        esc = f"Escalation: total exceeds {money(thr)}; manager approval is assumed to be required."
    return _load("internal_note.txt").substitute(
        label_upper=label.value.upper(), invoice_number=inv_no, vendor_name=vendor, po_ref=po_ref,
        confidence=validation.confidence, findings_block=block, escalation=esc).strip()


# ---------- traceability: every number in generated text must come from verified facts ----------
_NUM = re.compile(r"\d[\d,]*\.?\d*")


def _nums(text: str) -> set[Decimal]:
    out = set()
    for t in _NUM.findall(text):
        try:
            out.add(Decimal(t.rstrip(",.").replace(",", "")))
        except InvalidOperation:
            pass
    return out


def untraceable_numbers(texts: list[Optional[str]], inv: Optional[ExtractedInvoice], findings: list[Finding],
                        policy: Policy, extra_facts: tuple[str, ...] = ()) -> set[Decimal]:
    """Numbers in `texts` that are not backed by verified facts. `extra_facts` carries system-generated diagnostics
    (validation issues, error messages) and is used only for the internal note, never for vendor-facing text."""
    facts = [inv.model_dump_json() if inv else "", str(policy.manager_escalation_threshold),
             str(policy.amount_tolerance_pct), str(policy.unit_price_tolerance_pct), *extra_facts]
    for f in findings:
        facts.append(f.message)
        facts.extend(str(v) for v in f.evidence.values() if v is not None)
    allowed = _nums(" ".join(facts))
    used: set[Decimal] = set()
    for t in texts:
        if t:
            used |= _nums(t)
    return used - allowed
