"""Day 4: one regression test per root cause found by breaking the system, plus whole-matrix gates."""
import csv
import json
from decimal import Decimal
from datetime import date

import pytest

from ap import anchors
from ap.config import Policy
from ap.friendly import ERRORS, FINDINGS
from ap.names import same_vendor, vendor_key
from ap.rules import evaluate
from ap.schemas import ErrorCode, ExtractedInvoice, FindingCode as C, Label, PORecord, POLine, Severity
from ap.templates import render_vendor_email
from ap.validation import number_set, validate, _candidates
from tests.test_rules import FakeStorage, inv, po, codes


POLICY = Policy()
TEXT = ("Acme Ltd Invoice No: A-1 Invoice Date: 2026-11-05 PO Number: PO-9 Currency: USD "
        "Widget 2 5.00 10.00 Total: USD 10.00 Order date: 2026-10-01 Delivery date: 2026-11-08 Due date: 2026-12-05 "
        "Your ref: ORD-5501")
GOOD = dict(vendor_name="Acme Ltd", invoice_number="A-1", invoice_date="2026-11-05", po_number="PO-9", currency="USD",
            line_items=[dict(description="Widget", quantity=2, unit_price=5.0, amount=10.0)], total=10.0)


def v(d, text=TEXT, **kw):
    return validate(json.dumps(d), text, POLICY, **kw)


# ------------------------------------------------------------- every code has plain-language text
def test_every_finding_and_error_code_has_friendly_text():
    assert [c for c in C if c not in FINDINGS] == []
    assert [c for c in ErrorCode if c not in ERRORS] == []


# ------------------------------------------------------------- vendor names
@pytest.mark.parametrize("a,b", [("Acme Supplies Ltd", "ACME Supplies Limited"), ("Delta Cables Co", "Delta Cables Company"),
                                 ("Rhein Industrial GmbH", "rhein industrial"), ("Orbit Office Furniture", "Orbit Office Furniture, Inc.")])
def test_legitimate_name_variants_match(a, b):
    assert same_vendor(a, b)


@pytest.mark.parametrize("a,b", [("Summit Packaging", "Summit Packing"), ("Acme Supplies Ltd", "Acme Supplier Ltd"),
                                 ("Orbit Office Furniture", "Harbor Light Trading Co"), ("", "x")])
def test_lookalike_and_different_names_do_not_match(a, b):
    assert not same_vendor(a, b)


def test_vendor_key_ignores_legal_suffixes_only():
    assert vendor_key("The Acme Co., Ltd.") == "acme"
    assert vendor_key("Ltd") == "ltd"            # a name made only of suffixes keeps them


# ------------------------------------------------------------- rules: vendor vs PO, duplicates via PO vendor, line matching
def test_vendor_not_matching_po_is_flagged_and_blocks_the_vendor_email():
    f = evaluate(inv(vendor="Harbor Light Trading Co"), FakeStorage([po()]), POLICY)
    assert C.VENDOR_MISMATCH in codes(f)
    from ap.schemas import ValidationReport
    assert render_vendor_email(inv(vendor="Harbor Light Trading Co"), f, ValidationReport(passed=True, attempts=1, confidence="high")) is None


def test_vendor_suffix_difference_is_not_a_mismatch():
    assert C.VENDOR_MISMATCH not in codes(evaluate(inv(vendor="WIDGET CO LIMITED"), FakeStorage([po()]), POLICY))


def test_duplicate_is_still_found_when_the_extracted_vendor_is_wrong():
    seen = [dict(vendor_name="Widget Co", invoice_number="INV-1", invoice_date="2026-09-01", total="1.00", run_id="r1")]
    f = evaluate(inv(vendor="Harbor Light Trading Co"), FakeStorage([po()], seen), POLICY)
    assert {C.EXACT_DUPLICATE, C.VENDOR_MISMATCH} <= codes(f)           # PO vendor is the second opinion


def test_near_duplicate_line_names_match_but_different_products_never_do():
    pos = [PORecord(po_number="PO-T", vendor_name="Widget Co", currency="USD", status="open", total="500.00",
                    lines=[POLine(description="Standard office desk 120 cm", quantity="10", unit_price="50.00")])]
    ok = evaluate(inv(desc="Standard office desks 120 cm", qty="10", price="50.00", total="500.00"), FakeStorage(pos), POLICY)
    assert C.LINE_NOT_ON_PO not in codes(ok)                                # a plural still matches
    from difflib import SequenceMatcher
    assert SequenceMatcher(None, "standardofficedesk120cm", "standardofficedesk160cm").ratio() >= 0.92   # similar enough to fool a naive matcher
    other = evaluate(inv(desc="Standard office desk 160 cm", qty="10", price="50.00", total="500.00"), FakeStorage(pos), POLICY)
    assert C.LINE_NOT_ON_PO in codes(other)                                 # ...but different numbers are never matched


# ------------------------------------------------------------- validation: format tolerance
def test_code_fence_is_stripped_and_recorded():
    o = validate("```json\n" + json.dumps(GOOD) + "\n```", TEXT, POLICY)
    assert o.passed and o.repairs == ["stripped_code_fence"]


def test_plain_json_has_no_repairs():
    assert v(GOOD).repairs == []


def test_us_formatted_number_strings_are_accepted():
    d = {**GOOD, "total": "1,010.00", "line_items": [dict(description="Widget", quantity="2", unit_price="505.00", amount="1,010.00")]}
    t = TEXT.replace("10.00", "1,010.00").replace("5.00", "505.00")
    assert v(d, t).passed


def test_ambiguous_european_string_is_rejected_not_guessed():
    assert not v({**GOOD, "total": "1.234,56"}).passed


@pytest.mark.parametrize("printed,value", [("1.234,56", "1234.56"), ("1,234.56", "1234.56"), ("47.500,00", "47500.00"),
                                           ("850,00", "850.00"), ("12", "12")])
def test_number_readings_cover_both_conventions(printed, value):
    assert Decimal(value) in number_set(f"Total {printed}")


def test_european_invoice_total_is_grounded():
    t = "Acme Ltd Invoice No: A-1 PO Number: PO-9 USD Widget 2 5,00 10,00 Total: USD 10,00"
    assert v(GOOD, t.replace("Invoice No: A-1", "Invoice No: A-1 Invoice Date: 05.11.2026")).passed


# ------------------------------------------------------------- validation: cross-field and anchoring
def test_invoice_number_equal_to_po_number_is_rejected():
    o = v({**GOOD, "invoice_number": "PO-9"})
    assert not o.passed and any("equals the PO number" in i for i in o.issues)


def test_due_date_reported_as_invoice_date_is_rejected():
    o = v({**GOOD, "invoice_date": "2026-12-05"})
    assert not o.passed and any("invoice_date" in i for i in o.issues)


@pytest.mark.parametrize("wrong", ["2026-10-01", "2026-11-08"])     # order date, delivery date
def test_other_printed_dates_are_rejected_by_label_anchoring(wrong):
    assert not v({**GOOD, "invoice_date": wrong}).passed


def test_customer_reference_as_invoice_number_is_rejected():
    assert not v({**GOOD, "invoice_number": "ORD-5501"}, TEXT).passed


def test_anchoring_is_skipped_when_the_document_has_no_such_label():
    text = "Acme Ltd Document ZX-77 Widget 2 5.00 10.00 USD 10.00 PO-9"
    o = v({**GOOD, "invoice_number": "ZX-77", "invoice_date": None}, text)
    assert anchors.invoice_number_anchored("ZX-77", text) is None and o.passed


def test_invoice_number_must_match_whole_token_not_a_prefix():
    assert anchors.invoice_number_anchored("INV-50", "Invoice No: INV-5001 Date") is False
    assert anchors.invoice_number_anchored("INV-5001", "Invoice No: INV-5001 Date") is True


@pytest.mark.parametrize("text", ["Invoice\n# DC-88120\nDate: x", "Bill No.  DC-88120 Issued x", "Invoice No: DC-88120"])
def test_invoice_number_labels_across_layouts(text):
    assert anchors.invoice_number_anchored("DC-88120", text) is True


def test_total_is_found_after_or_before_its_label_and_subtotal_is_ignored():
    cand = _candidates
    assert anchors.total_anchored(Decimal("47500"), "Total: USD 47,500.00", cand) is True
    assert anchors.total_anchored(Decimal("47500"), "Amount due 47.500,00", cand) is True
    assert anchors.total_anchored(Decimal("47500"), "47,500.00 Total", cand) is True
    assert anchors.total_anchored(Decimal("100"), "Subtotal 100.00 Total 150.00", cand) is False


def test_date_anchoring_ignores_due_delivery_and_order_dates():
    forms = __import__("ap.validation", fromlist=["_date_forms"])._date_forms
    d = date(2026, 11, 8)
    assert anchors.date_anchored(d, "Delivery date: 2026-11-08 Invoice Date: 2026-11-05", forms(d)) is False
    assert anchors.date_anchored(date(2026, 11, 5), "Delivery date: 2026-11-08 Invoice Date: 2026-11-05", forms(date(2026, 11, 5))) is True


def test_description_not_in_text_lowers_confidence_but_plural_is_tolerated():
    d = {**GOOD, "line_items": [dict(description="Widgets", quantity=2, unit_price=5.0, amount=10.0)]}
    assert "line_items[1]" not in v(d).ungrounded
    d["line_items"][0]["description"] = "Sprocket"
    assert "line_items[1]" in v(d).ungrounded


def test_safeguard_switches_exist_for_ablation():
    bad = {**GOOD, "invoice_number": "PO-9"}
    assert v(bad).passed is False and v(bad, check_consistency=False, check_anchoring=False).passed


# ------------------------------------------------------------- whole-matrix regression gates
@pytest.fixture(scope="session")
def full_data(tmp_path_factory):
    import generate_data
    d = tmp_path_factory.mktemp("full") / "data"
    generate_data.generate(d); generate_data.generate_stress(d); generate_data.generate_holdout(d)
    return d


def test_gate_fault_matrix_has_no_unsafe_outcomes_and_no_false_alarms(full_data):
    from evalkit.matrix import run_matrix, unsafe
    rows = run_matrix(full_data)
    assert len(rows) >= 700
    assert unsafe(rows) == []
    assert [r for r in rows if r["outcome"] == "FALSE_ALARM"] == []
    assert [r for r in rows if r["outcome"] == "ERROR"] == []


def test_gate_held_out_faults_have_no_unsafe_outcomes(full_data):
    from evalkit.matrix import run_matrix, unsafe
    rows = run_matrix(full_data, holdout=True)
    assert len(rows) >= 70 and unsafe(rows) == []


def test_gate_transient_faults_never_approve_on_a_retried_extraction(full_data):
    from evalkit.matrix import run_matrix, unsafe
    rows = run_matrix(full_data, transient=True)
    assert unsafe(rows) == []
    assert all(r["got"] != "Approve" for r in rows if str(r["attempts"]) == "2")     # a retried reading goes to a human


def test_gate_perfect_extractor_handles_every_document_variant(full_data):
    from evalkit.runner import load_expected, run_one
    bad = []
    for sub, truth_dir in (("", full_data / "ground_truth"), ("stress", full_data / "stress" / "ground_truth"),
                           ("holdout", full_data / "holdout" / "ground_truth")):
        f = (full_data / sub / "expected_results.csv") if sub else full_data / "expected_results.csv"
        for r in load_expected(f):
            truth = json.loads((truth_dir / f"{r['case_id']}.json").read_text())
            res = run_one(r, full_data / r["invoice_file"], truth, full_data, provider=None, mode="ground_truth", override=truth)
            if res["outcome"] != "CORRECT" or not res["codes_ok"]:
                bad.append((r["case_id"], res["outcome"], res["codes"]))
    assert bad == []


def test_gate_every_fault_is_actually_exercised(full_data):
    from evalkit.matrix import run_matrix
    from evalkit.faults import FAULTS, HOLDOUT_FAULTS
    seen = {r["fault"] for r in run_matrix(full_data)} | {r["fault"] for r in run_matrix(full_data, holdout=True)}
    assert seen == {f.fid for f in FAULTS + HOLDOUT_FAULTS}


# ------------------------------------------------------------- invoice-level tax is reconciled separately from line subtotal
TAX_TEXT = ("Acme Ltd Invoice No: A-1 Invoice Date: 2026-11-05 PO Number: PO-9 Currency: USD "
            "Widget 2 500.00 1,000.00 Subtotal 1,000.00 Tax 100.00 Total 1,100.00")
TAX_GOOD = dict(GOOD, line_items=[dict(description="Widget", quantity=2, unit_price=500.0, amount=1000.0)])


def test_invoice_with_tax_and_correct_total_passes_subtotal_reconciliation():
    o = v({**TAX_GOOD, "subtotal": 1000.0, "tax_total": 100.0, "total": 1100.0}, TAX_TEXT)
    assert o.passed, o.issues      # lines match subtotal; subtotal + tax matches grand total


def test_subtotal_reported_as_total_is_caught_by_anchoring():
    o = v({**TAX_GOOD, "total": 1000.0}, TAX_TEXT)                                   # arithmetic is consistent, value is real...
    assert not o.passed and any("total could not be reliably associated with a total/amount-due label" in i for i in o.issues)   # ...but it is the wrong number
