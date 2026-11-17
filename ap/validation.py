"""Validation of extracted fields: schema, domain conversion, arithmetic, cross-field consistency, and grounding in
the PDF text. Everything here is deterministic; the LLM never sees these checks' results except as retry feedback."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import ValidationError

from ap import anchors
from ap.config import Policy
from ap.fmt import d2
from ap.schemas import ExtractedInvoice, InvoiceLine, LLMExtraction

CRITICAL_FIELDS = ("vendor_name", "invoice_number", "currency", "total")  # po_number is critical when non-null
SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP"}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
_NUM = re.compile(r"\d(?:[\d.,]*\d)?")
_DUE_WORDS = ("due", "pay by", "payable by", "payment by")


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _candidates(tok: str) -> set[Decimal]:
    """Every sensible numeric reading of a printed number. '1.234,56' (European) and '1,234.56' (US) both yield
    1234.56. Ambiguous tokens such as '1.234' yield both readings, so grounding is slightly permissive by design."""
    out: set[Decimal] = set()
    for variant in (tok.replace(",", ""), tok.replace(".", "").replace(",", ".") if "," in tok else None):
        if variant:
            try:
                out.add(Decimal(variant))
            except InvalidOperation:
                pass
    return out


def number_set(text: str) -> set[Decimal]:
    out: set[Decimal] = set()
    for tok in _NUM.findall(text):
        out |= _candidates(tok)
    return out


@dataclass
class Outcome:
    passed: bool
    extracted: Optional[ExtractedInvoice] = None
    ungrounded: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    repairs: list[str] = field(default_factory=list)


def _to_domain(w: LLMExtraction) -> ExtractedInvoice:
    lines = [InvoiceLine(description=l.description,
                         quantity=(Decimal(int(l.quantity)) if float(l.quantity).is_integer() else Decimal(str(l.quantity))),
                         unit_price=d2(l.unit_price), amount=d2(l.amount)) for l in w.line_items]
    return ExtractedInvoice(
        vendor_name=w.vendor_name, invoice_number=w.invoice_number,
        invoice_date=date.fromisoformat(w.invoice_date) if w.invoice_date else None,
        po_number=w.po_number, currency=w.currency.strip().upper() if w.currency else None,
        line_items=lines, total=d2(w.total) if w.total is not None else None,
        subtotal=d2(w.subtotal) if w.subtotal is not None else None,
        tax_total=d2(w.tax_total) if w.tax_total is not None else None,
        additional_charges=d2(w.additional_charges) if w.additional_charges is not None else None,
        discount_total=d2(w.discount_total) if w.discount_total is not None else None)


def _date_forms(d: date) -> set[str]:
    """Every common way a date can be printed (day-first and month-first), lowercase, commas removed."""
    forms = {d.isoformat()}
    for dd in {f"{d.day}", f"{d.day:02d}"}:
        for mm in {f"{d.month}", f"{d.month:02d}"}:
            for sep in "/.-":
                forms.add(f"{dd}{sep}{mm}{sep}{d.year}")
                forms.add(f"{mm}{sep}{dd}{sep}{d.year}")
        for name in {MONTHS[d.month - 1], MONTHS[d.month - 1][:3]}:
            forms.add(f"{dd} {name} {d.year}")
            forms.add(f"{name} {dd} {d.year}")
    return forms


def _flat(text: str) -> str:
    t = re.sub(r"(?<=[a-z])\.", "", text.lower().replace(",", " "))
    return re.sub(r"\s+", " ", t)


def _date_occurrences(d: date, text: str) -> list[int]:
    t = _flat(text)
    return sorted({m.start() for form in _date_forms(d) for m in re.finditer(re.escape(form), t)})


def _date_grounded(d: date, text: str) -> bool:
    """The full date must appear in one recognizable format (not just matching digits somewhere in the text)."""
    return bool(_date_occurrences(d, text))


def _date_is_only_a_due_date(d: date, text: str) -> bool:
    """True when every place the date is printed is preceded by 'due' wording: it is the payment deadline, not the
    invoice date. (Confusing the two silently defeats the possible-duplicate check.)"""
    t = _flat(text)
    spots = _date_occurrences(d, text)
    return bool(spots) and all(any(w in t[max(0, i - 25):i] for w in _DUE_WORDS) for i in spots)


def _currency_grounded(code: str, text: str) -> bool:
    if re.search(rf"\b{re.escape(code)}\b", text, re.IGNORECASE):
        return True
    return any(sym in text and mapped == code for sym, mapped in SYMBOLS.items())


def _words(s: str) -> set[str]:
    """Lower-case word stems (a trailing 's' is ignored) so 'inch' and 'inchs' compare equal."""
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in re.findall(r"[a-z0-9]+", s.lower())}


def _strip_fence(raw: str) -> tuple[str, list[str]]:
    t = raw.strip()
    m = re.fullmatch(r"```[a-zA-Z]*\s*\n?(.*?)\n?```", t, re.DOTALL)
    return (m.group(1).strip(), ["stripped_code_fence"]) if m else (raw, [])


def validate(raw: str, text: Optional[str], policy: Policy, *, check_arithmetic: bool = True,
             check_grounding: bool = True, check_consistency: bool = True, check_anchoring: bool = True) -> Outcome:
    """The three keyword switches exist only so evaluation can switch one safeguard off at a time (ablation)."""
    issues: list[str] = []
    raw, repairs = _strip_fence(raw)
    # 1. wire schema
    try:
        payload = json.loads(raw)
        # Backward compatibility for test fixtures and previously stored extraction payloads.
        for key in ("subtotal", "tax_total", "additional_charges", "discount_total"):
            payload.setdefault(key, None)
        wire = LLMExtraction.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        return Outcome(False, issues=[f"Output did not match the required JSON schema: {str(exc).splitlines()[0]}"],
                       repairs=repairs)
    # 2. domain conversion
    try:
        inv = _to_domain(wire)
    except (ValidationError, ValueError, InvalidOperation) as exc:
        return Outcome(False, issues=[f"Field values are invalid: {str(exc).splitlines()[0]}"], repairs=repairs)
    # 3. arithmetic
    if check_arithmetic:
        for l in inv.line_items:
            if abs(l.quantity * l.unit_price - l.amount) > Decimal("0.01"):
                issues.append(f"Line '{l.description}': quantity x unit price does not equal amount.")
        if inv.line_items:
            line_sum = d2(sum(l.amount for l in inv.line_items))
            # Prefer the invoice's explicitly printed subtotal. When it is absent,
            # reconcile the lines to the grand total using any extracted tax/fees/discounts.
            if inv.subtotal is not None:
                # Some invoices show net line amounts (sum = subtotal); others show gross
                # line amounts inclusive of tax (sum = grand total). Accept either explicit basis.
                matches_subtotal = abs(line_sum - inv.subtotal) <= Decimal("0.01")
                matches_total = inv.total is not None and abs(line_sum - inv.total) <= Decimal("0.01")
                if not (matches_subtotal or matches_total):
                    issues.append("Sum of line amounts matches neither the invoice subtotal nor the grand total.")
            elif inv.total is not None and abs(line_sum - inv.total) > Decimal("0.01"):
                expected_total = d2(line_sum + (inv.tax_total or Decimal(0))
                                    + (inv.additional_charges or Decimal(0))
                                    - (inv.discount_total or Decimal(0)))
                if abs(expected_total - inv.total) > Decimal("0.01"):
                    issues.append("Line amounts plus invoice-level tax/charges, less discounts, do not equal the total.")
        if inv.total is not None and inv.subtotal is not None:
            expected_total = d2(inv.subtotal + (inv.tax_total or Decimal(0))
                                + (inv.additional_charges or Decimal(0))
                                - (inv.discount_total or Decimal(0)))
            if abs(expected_total - inv.total) > Decimal("0.01"):
                issues.append("Subtotal plus invoice-level tax/charges, less discounts, does not equal the total.")
    # 4. cross-field consistency (catches plausible-looking values that are in the wrong field)
    if check_consistency:
        if inv.invoice_number and inv.po_number and norm(inv.invoice_number) == norm(inv.po_number):
            issues.append("invoice_number equals the PO number. The invoice number is the vendor's own document number, "
                          "not the purchase order reference.")
        if text and inv.invoice_date and _date_is_only_a_due_date(inv.invoice_date, text):
            issues.append("invoice_date is only printed as a due date. Report the date the invoice was issued.")
    # 4b. label anchoring: the value must sit next to the right label, not merely appear somewhere
    if check_anchoring and text:
        if inv.invoice_number and anchors.invoice_number_anchored(inv.invoice_number, text) is False:
            issues.append(f"invoice_number '{inv.invoice_number}' is not printed next to an invoice-number label "
                          "(for example 'Invoice No'). It may be another reference.")
        if inv.total is not None and anchors.total_anchored(inv.total, text, _candidates) is False:
            issues.append("total could not be reliably associated with a total/amount-due label; verify the printed total.")
        if inv.invoice_date and anchors.date_anchored(inv.invoice_date, text, _date_forms(inv.invoice_date)) is False:
            issues.append("invoice_date is not printed next to an invoice-date label. It may be an order, delivery or due date.")
    # 5. grounding (only when the PDF text is available)
    ungrounded: list[str] = []
    if text and check_grounding:
        tn, nums = norm(text), number_set(text)
        for name in ("vendor_name", "invoice_number", "po_number"):
            v = getattr(inv, name)
            if v is not None and norm(v) not in tn:
                ungrounded.append(name)
        for amount_field in ("total", "subtotal", "tax_total", "additional_charges", "discount_total"):
            amount_value = getattr(inv, amount_field)
            if amount_value is not None and amount_value not in nums:
                ungrounded.append(amount_field)
        if inv.currency is not None and not _currency_grounded(inv.currency, text):
            ungrounded.append("currency")
        if inv.invoice_date is not None and not _date_grounded(inv.invoice_date, text):
            ungrounded.append("invoice_date")
        text_words = _words(text)
        for i, l in enumerate(inv.line_items, 1):
            if not ({l.quantity, l.unit_price, l.amount} <= nums) or not _words(l.description) <= text_words:
                ungrounded.append(f"line_items[{i}]")
        critical = set(CRITICAL_FIELDS) | {"po_number", "total", "subtotal", "tax_total",
                                                "additional_charges", "discount_total"}
        # Remove only fields that fail their own grounding check. Keep independently verified
        # identifiers and amounts; a bad line item must not erase the vendor/invoice identity.
        updates = {}
        for f in ungrounded:
            if f in critical:
                updates[f] = None
                issues.append(f"Value for '{f}' does not appear in the invoice text; that field was withheld.")
            elif f.startswith("line_items["):
                issues.append(f"{f} could not be fully grounded in the PDF text; verify this line item.")
        if updates:
            inv = inv.model_copy(update=updates)
    # A failed arithmetic, label-anchor, or line-item check is a review condition, not a reason
    # to discard otherwise usable fields. `passed` remains false so the decision engine cannot
    # approve it automatically; `extracted` is intentionally retained for human review.
    return Outcome(passed=not issues, extracted=inv, ungrounded=ungrounded, issues=issues,
                   repairs=repairs)
