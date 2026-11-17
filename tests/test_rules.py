"""Rules engine: boundary values for every tolerance, plus each finding code."""
from decimal import Decimal

import pytest

from ap.config import Policy
from ap.rules import evaluate
from ap.schemas import ExtractedInvoice, PORecord, POLine, FindingCode as C, Severity

POLICY = Policy()


class FakeStorage:
    def __init__(self, pos=(), processed=()):
        self.pos, self.processed = list(pos), list(processed)

    def get_po(self, n):
        return next((p for p in self.pos if p.po_number.upper() == n.upper()), None)

    def list_pos(self):
        return self.pos

    def processed_entries(self):
        return self.processed


def po(status="open", cur="USD", vendor="Widget Co", num="PO-T", total="1000.00", price="100.00", qty="10"):
    return PORecord(po_number=num, vendor_name=vendor, currency=cur, status=status, total=total,
                    lines=[POLine(description="Widget", quantity=qty, unit_price=price)])


def inv(total="1000.00", qty="10", price="100.00", cur="USD", po_number="PO-T", vendor="Widget Co", number="INV-1",
        date="2026-10-01", desc="Widget"):
    amount = str(Decimal(qty) * Decimal(price))
    return ExtractedInvoice(vendor_name=vendor, invoice_number=number, invoice_date=date, po_number=po_number,
                            currency=cur, total=total,
                            line_items=[dict(description=desc, quantity=qty, unit_price=price, amount=amount)])


def codes(findings):
    return {f.code for f in findings}


def run(invoice, storage=None):
    return evaluate(invoice, storage or FakeStorage([po()]), POLICY)


def test_clean_match_has_no_findings():
    assert run(inv()) == []


@pytest.mark.parametrize("total,flagged", [("1010.00", False), ("1010.01", True), ("1000.01", False), ("1100.00", True)])
def test_total_tolerance_boundary(total, flagged):
    assert (C.AMOUNT_OVER_TOLERANCE in codes(run(inv(total=total)))) is flagged


def test_within_tolerance_variance_is_info_only():
    f = run(inv(total="1005.00"))
    assert codes(f) == {C.WITHIN_TOLERANCE_VARIANCE} and f[0].severity == Severity.INFO


def test_under_billing_is_not_an_exception():
    f = run(inv(total="900.00"))
    assert C.AMOUNT_OVER_TOLERANCE not in codes(f) and all(x.severity == Severity.INFO for x in f)


@pytest.mark.parametrize("qty,flagged", [("10", False), ("9", False), ("11", True)])
def test_quantity_boundary(qty, flagged):
    assert (C.QUANTITY_EXCEEDS_PO in codes(run(inv(qty=qty)))) is flagged


@pytest.mark.parametrize("price,flagged", [("101.00", False), ("101.01", True), ("99.00", False), ("98.99", True)])
def test_unit_price_boundary_is_symmetric(price, flagged):
    assert (C.UNIT_PRICE_MISMATCH in codes(run(inv(price=price)))) is flagged


def test_line_not_on_po():
    assert C.LINE_NOT_ON_PO in codes(run(inv(desc="Gadget")))


def test_line_matching_ignores_case_and_punctuation():
    assert C.LINE_NOT_ON_PO not in codes(run(inv(desc="  WIDGET! ")))


def test_currency_mismatch_skips_amount_checks():
    f = run(inv(cur="EUR", total="9999.00"))
    assert codes(f) == {C.CURRENCY_MISMATCH}


def test_po_not_found_blocks():
    f = run(inv(po_number="PO-NOPE"))
    assert codes(f) == {C.PO_NOT_FOUND} and f[0].severity == Severity.BLOCK


def test_po_closed_blocks():
    f = run(inv(), FakeStorage([po(status="closed")]))
    assert codes(f) == {C.PO_CLOSED} and f[0].severity == Severity.BLOCK


def test_missing_po_does_not_create_a_finding_or_stop_invoice_review():
    f = run(inv(po_number=None), FakeStorage([po(num="PO-A"), po(num="PO-B", vendor="Other Co")]))
    assert C.PO_MISSING_ON_INVOICE not in codes(f)
    assert C.PO_NOT_FOUND not in codes(f)


def test_missing_po_still_runs_duplicate_checks():
    seen = [dict(vendor_name="Widget Co", invoice_number="INV-1", invoice_date="2026-10-01",
                 total="1000.00", run_id="r1", confirmed_at="2026-10-02")]
    f = run(inv(po_number=None), FakeStorage([], seen))
    assert C.EXACT_DUPLICATE in codes(f)


def test_missing_po_uses_a_unique_evidence_match_without_flagging_the_missing_reference():
    f = run(inv(po_number=None), FakeStorage([po(num="PO-A")]))
    assert C.PO_MISSING_ON_INVOICE not in codes(f)
    assert C.PO_NOT_FOUND not in codes(f)

def test_inferred_po_still_detects_vendor_mismatch():
    f = run(inv(po_number=None), FakeStorage([po(num="PO-A", vendor="Different Vendor")]))
    assert C.VENDOR_MISMATCH in codes(f)


def test_exact_duplicate_ignores_case_and_punctuation():
    seen = [dict(vendor_name="WIDGET CO.", invoice_number="inv 1", invoice_date="2026-09-01", total="1.00",
                 run_id="r1", confirmed_at="2026-09-02")]
    f = run(inv(), FakeStorage([po()], seen))
    assert C.EXACT_DUPLICATE in codes(f) and any(x.severity == Severity.BLOCK for x in f)


def test_possible_duplicate_needs_same_total_and_date():
    seen = dict(vendor_name="Widget Co", invoice_number="INV-0", invoice_date="2026-10-01", total="1000.00", run_id="r1")
    assert C.POSSIBLE_DUPLICATE in codes(run(inv(), FakeStorage([po()], [seen])))
    other_date = dict(seen, invoice_date="2026-10-02")
    assert C.POSSIBLE_DUPLICATE not in codes(run(inv(), FakeStorage([po()], [other_date])))
    other_total = dict(seen, total="999.00")
    assert C.POSSIBLE_DUPLICATE not in codes(run(inv(), FakeStorage([po()], [other_total])))


def test_different_vendor_same_number_is_not_a_duplicate():
    seen = [dict(vendor_name="Another Co", invoice_number="INV-1", invoice_date="2026-10-01", total="1000.00", run_id="r")]
    assert not codes(run(inv(), FakeStorage([po()], seen))) & {C.EXACT_DUPLICATE, C.POSSIBLE_DUPLICATE}


@pytest.mark.parametrize("field", ["vendor_name", "invoice_number", "currency", "total"])
def test_null_critical_field_is_flagged(field):
    d = inv().model_dump()
    d[field] = None
    f = evaluate(ExtractedInvoice(**d), FakeStorage([po()]), POLICY)
    assert any(x.code == C.FIELD_NOT_FOUND and x.evidence["field"] == field for x in f)


def test_duplicate_check_skipped_without_invoice_number():
    seen = [dict(vendor_name="Widget Co", invoice_number="", invoice_date="", total="", run_id="r")]
    d = inv().model_dump(); d["invoice_number"] = None
    assert not codes(evaluate(ExtractedInvoice(**d), FakeStorage([po()], seen), POLICY)) & {C.EXACT_DUPLICATE}
