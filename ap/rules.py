"""Deterministic matching rules. Pure Python, no AI. Every finding's text is built here from evidence."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from ap.config import Policy
import difflib
import re

from ap.fmt import d2, money, pct, qty
from ap.names import same_vendor
from ap.schemas import ExtractedInvoice, Finding, FindingCode as C, PORecord, Severity as S
from ap.storage import Storage
from ap.validation import norm

HUNDRED = Decimal(100)
LINE_SIMILARITY = 0.92


def _match_line(description: str, po_lines: dict):
    """Exact (normalized) match first; otherwise a near match ONLY if the digits are identical, so 'Cat6 cable box'
    can never be matched to 'Cat5 cable box' while 'Desk chair' still matches 'Desk chairs'."""
    key = norm(description)
    if key in po_lines:
        return po_lines[key]
    digits = re.findall(r"\d+", description)
    best, best_ratio = None, 0.0
    for k, pl in po_lines.items():
        if re.findall(r"\d+", pl.description) != digits:
            continue
        r = difflib.SequenceMatcher(None, key, k).ratio()
        if r > best_ratio:
            best, best_ratio = pl, r
    return best if best_ratio >= LINE_SIMILARITY else None


def _pct_diff(new: Decimal, base: Decimal) -> Decimal:
    return (new - base) / base * HUNDRED if base else Decimal(0)


def _infer_unique_po(inv: ExtractedInvoice, storage: Storage, policy: Policy) -> Optional[PORecord]:
    """Recover a missing PO reference only when one open PO matches the invoice evidence.

    Vendor is deliberately not used as a hard filter here: it is checked afterwards, so a
    misidentified Bill-To party can still be caught as a vendor mismatch. Ambiguous matches
    are never selected.
    """
    if not inv.line_items or inv.total is None or not inv.currency:
        return None
    tolerance = Decimal(str(policy.amount_tolerance_pct))
    price_tolerance = Decimal(str(policy.unit_price_tolerance_pct))
    matches: list[PORecord] = []
    for candidate in storage.list_pos():
        if candidate.status != "open" or candidate.currency != inv.currency or candidate.total <= 0:
            continue
        if abs(_pct_diff(inv.total, candidate.total)) > tolerance:
            continue
        po_lines = {norm(line.description): line for line in candidate.lines}
        all_lines_match = True
        for line in inv.line_items:
            po_line = _match_line(line.description, po_lines)
            if po_line is None or line.quantity > po_line.quantity + Decimal(str(policy.quantity_over_allowed)):
                all_lines_match = False
                break
            if abs(_pct_diff(line.unit_price, po_line.unit_price)) > price_tolerance:
                all_lines_match = False
                break
        if all_lines_match:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def evaluate(inv: ExtractedInvoice, storage: Storage, policy: Policy) -> list[Finding]:
    f: list[Finding] = []
    tol_total = Decimal(str(policy.amount_tolerance_pct))
    tol_price = Decimal(str(policy.unit_price_tolerance_pct))

    # 1. critical fields
    for name in ("vendor_name", "invoice_number", "currency", "total"):
        if getattr(inv, name) is None:
            f.append(Finding(code=C.FIELD_NOT_FOUND, severity=S.REVIEW,
                             message=f"Field '{name}' was not found on the invoice.", evidence={"field": name}))

    # 2. PO lookup first: the PO's vendor is a second opinion on who issued the invoice
    po = storage.get_po(inv.po_number) if inv.po_number else _infer_unique_po(inv, storage, policy)

    # 3. duplicates (compared against the extracted vendor AND the PO vendor, so a mis-read vendor cannot hide one)
    vendors = [v for v in (inv.vendor_name, po.vendor_name if po else None) if v]
    if vendors and inv.invoice_number:
        n = norm(inv.invoice_number)
        for e in storage.processed_entries():
            if str(e.get("human_decision", "")).strip().lower() == "void":
                continue            # an operator cancelled this entry (for example a mistaken click): it no longer counts
            if not any(same_vendor(e.get("vendor_name", ""), v) for v in vendors):
                continue
            if norm(e.get("invoice_number", "")) == n:
                f.append(Finding(code=C.EXACT_DUPLICATE, severity=S.BLOCK,
                                 message=(f"Invoice {inv.invoice_number} from {inv.vendor_name or vendors[0]} was already "
                                          f"processed on {e.get('confirmed_at', 'an earlier date')}."),
                                 evidence={"invoice_number": inv.invoice_number,
                                           "original_run_id": e.get("run_id"), "processed_at": e.get("confirmed_at")}))
                break
            same_total = inv.total is not None and e.get("total") and d2(e["total"]) == inv.total
            same_date = inv.invoice_date is not None and e.get("invoice_date") == inv.invoice_date.isoformat()
            if same_total and same_date:
                f.append(Finding(code=C.POSSIBLE_DUPLICATE, severity=S.REVIEW,
                                 message=(f"Same vendor, total and date as invoice {e.get('invoice_number')} "
                                          f"(run {e.get('run_id')}), but a different invoice number."),
                                 evidence={"other_invoice_number": e.get("invoice_number"),
                                           "other_run_id": e.get("run_id")}))
                break

    # 3. PO
    # A missing PO reference is not an exception by itself. Continue with the
    # invoice-level checks already performed above; PO-specific matching is simply skipped.
    if not inv.po_number and po is None:
        return f

    if inv.po_number and po is None:
        f.append(Finding(code=C.PO_NOT_FOUND, severity=S.BLOCK,
                         message=f"Purchase order {inv.po_number} was not found.", evidence={"po_number": inv.po_number}))
        return f
    if inv.vendor_name and not same_vendor(inv.vendor_name, po.vendor_name):
        f.append(Finding(code=C.VENDOR_MISMATCH, severity=S.REVIEW,
                         message=(f"The vendor on the invoice ('{inv.vendor_name}') does not match the vendor on "
                                  f"{po.po_number} ('{po.vendor_name}')."),
                         evidence={"invoice_vendor": inv.vendor_name, "po_vendor": po.vendor_name,
                                   "po_number": po.po_number}))
    if po.status != "open":
        f.append(Finding(code=C.PO_CLOSED, severity=S.BLOCK,
                         message=f"Purchase order {po.po_number} is closed.", evidence={"po_number": po.po_number}))
        return f

    # 4. currency (no conversion; amount checks are skipped when currencies differ)
    if inv.currency and inv.currency != po.currency:
        f.append(Finding(code=C.CURRENCY_MISMATCH, severity=S.REVIEW,
                         message=(f"Invoice currency {inv.currency} differs from PO currency {po.currency}. "
                                  "No conversion was performed and amounts were not compared."),
                         evidence={"invoice_currency": inv.currency, "po_currency": po.currency}))
        return f

    cur = inv.currency or po.currency

    # 5. lines
    po_lines = {}
    for pl in po.lines:
        po_lines.setdefault(norm(pl.description), pl)
    for line in inv.line_items:
        pl = _match_line(line.description, po_lines)
        if pl is None:
            f.append(Finding(code=C.LINE_NOT_ON_PO, severity=S.REVIEW,
                             message=f"Line '{line.description}' does not match any line on {po.po_number}.",
                             evidence={"line": line.description}))
            continue
        if line.quantity > pl.quantity + Decimal(str(policy.quantity_over_allowed)):
            f.append(Finding(code=C.QUANTITY_EXCEEDS_PO, severity=S.REVIEW,
                             message=(f"Line '{line.description}': billed quantity {qty(line.quantity)} exceeds PO "
                                      f"quantity {qty(pl.quantity)}."),
                             evidence={"line": line.description, "invoice_quantity": qty(line.quantity),
                                       "po_quantity": qty(pl.quantity)}))
        diff = _pct_diff(line.unit_price, pl.unit_price)
        if abs(diff) > tol_price:
            direction = "higher" if diff > 0 else "lower"
            f.append(Finding(code=C.UNIT_PRICE_MISMATCH, severity=S.REVIEW,
                             message=(f"Line '{line.description}': unit price {money(line.unit_price)} vs PO "
                                      f"{money(pl.unit_price)} ({pct(abs(diff))}% {direction}); tolerance is {pct(tol_price)}%."),
                             evidence={"line": line.description, "invoice_unit_price": money(line.unit_price),
                                       "po_unit_price": money(pl.unit_price), "difference_pct": float(pct(abs(diff))),
                                       "direction": direction, "tolerance_pct": float(pct(tol_price))}))

    # 6. total (only billing ABOVE the PO is an exception; below is shown as information)
    if inv.total is not None:
        diff = _pct_diff(inv.total, po.total)
        delta = inv.total - po.total
        if diff > tol_total:
            f.append(Finding(code=C.AMOUNT_OVER_TOLERANCE, severity=S.REVIEW,
                             message=(f"Invoice total {money(inv.total)} {cur} exceeds PO total {money(po.total)} {cur} "
                                      f"by {money(delta)} ({pct(diff)}%); tolerance is {pct(tol_total)}%."),
                             evidence={"invoice_total": money(inv.total), "po_total": money(po.total),
                                       "difference": money(delta), "difference_pct": float(pct(diff)),
                                       "tolerance_pct": float(pct(tol_total))}))
        elif delta != 0:
            word = "above" if delta > 0 else "below"
            f.append(Finding(code=C.WITHIN_TOLERANCE_VARIANCE, severity=S.INFO,
                             message=(f"Invoice total {money(inv.total)} {cur} is {money(abs(delta))} "
                                      f"({pct(abs(diff))}%) {word} the PO total {money(po.total)} {cur}; "
                                      f"within the {pct(tol_total)}% tolerance."),
                             evidence={"invoice_total": money(inv.total), "po_total": money(po.total),
                                       "difference": money(abs(delta)), "difference_pct": float(pct(abs(diff))),
                                       "tolerance_pct": float(pct(tol_total))}))
    return f
