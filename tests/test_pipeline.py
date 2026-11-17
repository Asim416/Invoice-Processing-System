"""End-to-end pipeline behaviour: the 12 cases, fault injection, human confirmation, reproducibility."""
import json

import pytest

import run_cases
from ap.extraction.base import ProviderError, ProviderOutputInvalid
from ap.schemas import ErrorCode, ErrorResponse, FindingCode as C, Label
from tests.conftest import ScriptedProvider, pdf, truth


def codes(res):
    return {f.code for f in res.findings}


# ---------------------------------------------------------------- the 12 cases
@pytest.mark.parametrize("mode", ["ground_truth", "mock"])
def test_all_twelve_cases(mode, master_data):
    rows = run_cases.run(mode, master_data)
    assert len(rows) == 12
    bad = [r for r in rows if not (r["label_ok"] and r["codes_ok"])]
    assert not bad, bad


def test_tc03_end_to_end_in_mock_mode(make_pipeline, workdir):
    res = make_pipeline().process_file(pdf(workdir, "TC03"))
    assert res.label == Label.NEEDS_REVIEW and res.extraction_mode == "mock" and res.provider is None
    assert {C.AMOUNT_OVER_TOLERANCE, C.UNIT_PRICE_MISMATCH} <= codes(res)
    assert "47,500.00" in res.vendor_email and "45,000.00" in res.vendor_email and "2,500.00" in res.vendor_email
    assert res.requires_human_confirmation is True and res.validation.confidence == "high"
    logged = (workdir / "logs" / "runs.jsonl").read_text().splitlines()
    assert json.loads(logged[-1])["run_id"] == res.run_id


# ---------------------------------------------------------------- hard gates
def test_gate_exact_duplicate_never_approved(make_pipeline, workdir):
    assert make_pipeline().process_file(pdf(workdir, "TC05")).label == Label.REJECT_HOLD


def test_gate_over_tolerance_never_approved(make_pipeline, workdir):
    for c in ("TC03", "TC04", "TC12"):
        assert make_pipeline().process_file(pdf(workdir, c)).label != Label.APPROVE


def test_gate_injection_text_ignored_and_flagged(make_pipeline, workdir):
    res = make_pipeline().process_file(pdf(workdir, "TC12"))
    assert res.label == Label.NEEDS_REVIEW and C.SUSPICIOUS_TEXT in codes(res)
    assert "approved" not in (res.vendor_email or "").lower() and "ignore" not in (res.vendor_email or "").lower()


def test_gate_missing_total_stays_null_and_no_vendor_email(make_pipeline, workdir):
    res = make_pipeline().process_file(pdf(workdir, "TC10"))
    assert res.extracted.total is None and res.vendor_email is None and C.FIELD_NOT_FOUND in codes(res)


def test_gate_llm_that_invents_a_total_is_rejected_by_grounding(make_pipeline, workdir):
    d = truth(workdir, "TC10"); d["total"] = 390.0          # the model "calculates" a total that is not printed
    p = ScriptedProvider([d])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC10"), use_cache=False)
    assert res.extracted is None and C.EXTRACTION_INVALID in codes(res) and res.label == Label.NEEDS_REVIEW
    assert res.vendor_email is None and len(p.calls) == 2    # one corrective retry, then fail safe


# ---------------------------------------------------------------- fault injection
def test_llm_unavailable_fails_safe(make_pipeline, workdir):
    p = ScriptedProvider([ProviderError("down", ErrorCode.LLM_UNAVAILABLE, True)])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert res.label == Label.NEEDS_REVIEW and C.EXTRACTION_UNAVAILABLE in codes(res)
    assert res.vendor_email is None and res.error.error_code == ErrorCode.LLM_UNAVAILABLE and res.error.retryable


def test_rate_limited_error_code_is_preserved(make_pipeline, workdir):
    p = ScriptedProvider([ProviderError("429", ErrorCode.LLM_RATE_LIMITED, True)])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert res.error.error_code == ErrorCode.LLM_RATE_LIMITED and res.label != Label.APPROVE


def test_malformed_json_twice_is_extraction_invalid(make_pipeline, workdir):
    p = ScriptedProvider(["{broken"])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert C.EXTRACTION_INVALID in codes(res) and res.validation.attempts == 2 and res.label == Label.NEEDS_REVIEW


def test_retry_feedback_is_sent_to_the_model(make_pipeline, workdir):
    p = ScriptedProvider(["{broken", truth(workdir, "TC01")])
    make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert p.calls[0] is None and "schema" in p.calls[1].lower()


def test_recovered_extraction_is_medium_confidence_and_cannot_approve(make_pipeline, workdir):
    p = ScriptedProvider(["{broken", truth(workdir, "TC01")])            # TC01 is a clean invoice
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert res.validation.confidence == "medium" and C.LOW_CONFIDENCE_EXTRACTION in codes(res)
    assert res.label == Label.NEEDS_REVIEW


def test_empty_model_output_counts_as_failed_attempt_then_recovers(make_pipeline, workdir):
    p = ScriptedProvider([ProviderOutputInvalid("empty"), truth(workdir, "TC01")])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert res.validation.attempts == 2 and res.validation.passed


def test_model_that_adds_a_decision_field_is_rejected(make_pipeline, workdir):
    d = {**truth(workdir, "TC03"), "decision": "Approve"}
    res = make_pipeline(ScriptedProvider([d]), mode="live").process_file(pdf(workdir, "TC03"), use_cache=False)
    assert res.label != Label.APPROVE and C.EXTRACTION_INVALID in codes(res)


def test_hostile_but_well_formed_model_output_still_cannot_approve(make_pipeline, workdir):
    d = truth(workdir, "TC12")                                            # model dutifully extracts the real numbers
    res = make_pipeline(ScriptedProvider([d]), mode="live").process_file(pdf(workdir, "TC12"), use_cache=False)
    assert res.label == Label.NEEDS_REVIEW


@pytest.mark.parametrize("name,code", [("missing.pdf", ErrorCode.INVALID_INPUT)])
def test_missing_file(make_pipeline, workdir, name, code):
    r = make_pipeline().process_file(workdir / name)
    assert isinstance(r, ErrorResponse) and r.error_code == code


def test_non_pdf_is_rejected(make_pipeline, workdir):
    f = workdir / "invoice.docx"; f.write_text("x")
    r = make_pipeline().process_file(f)
    assert isinstance(r, ErrorResponse) and r.error_code == ErrorCode.UNSUPPORTED_FILE_TYPE and not r.retryable


def test_corrupt_pdf_is_rejected(make_pipeline, workdir):
    f = workdir / "bad.pdf"; f.write_text("not a pdf")
    assert make_pipeline().process_file(f).error_code == ErrorCode.INVALID_INPUT


def test_oversized_file_is_rejected(make_pipeline, workdir):
    r = make_pipeline(max_file_mb=0.0001).process_file(pdf(workdir, "TC01"))
    assert isinstance(r, ErrorResponse) and r.error_code == ErrorCode.FILE_TOO_LARGE


def test_no_text_layer_goes_to_review_without_calling_the_llm(make_pipeline, workdir):
    p = ScriptedProvider([truth(workdir, "TC01")])
    res = make_pipeline(p, mode="live").process_file(workdir / "data" / "invoices" / "no_text_layer.pdf")
    assert res.label == Label.NEEDS_REVIEW and res.error.error_code == ErrorCode.NO_TEXT_LAYER
    assert p.calls == [] and res.vendor_email is None


def test_unreadable_po_source_fails_safe(make_pipeline, workdir):
    (workdir / "data" / "pos.csv").unlink()
    res = make_pipeline().process_file(pdf(workdir, "TC01"))
    assert res.label == Label.NEEDS_REVIEW and C.PO_SOURCE_UNAVAILABLE in codes(res)
    assert res.error.error_code == ErrorCode.PO_SOURCE_UNAVAILABLE


def test_mock_mode_without_fixture_is_a_clear_unavailable_result(make_pipeline, workdir, master_data):
    import shutil
    other = workdir / "data" / "invoices" / "unknown.pdf"
    shutil.copy(master_data / "invoices" / "TC01.pdf", other)
    res = make_pipeline().process_file(other)
    assert res.label == Label.NEEDS_REVIEW and "fixture" in res.error.message.lower()


# ---------------------------------------------------------------- output validation
def test_untraceable_number_in_output_blocks_release(make_pipeline, workdir, monkeypatch):
    import ap.pipeline as pl
    monkeypatch.setattr(pl, "render_vendor_email", lambda *a, **k: "We owe you 999.99 dollars.")
    r = make_pipeline().process_file(pdf(workdir, "TC03"))
    assert isinstance(r, ErrorResponse) and r.error_code == ErrorCode.INTERNAL_ERROR


# ---------------------------------------------------------------- human confirmation & duplicates
def test_confirm_then_resubmit_is_an_exact_duplicate(make_pipeline, workdir):
    pipe = make_pipeline()
    first = pipe.process_file(pdf(workdir, "TC01"))
    assert first.label == Label.APPROVE
    # processing alone must not write to the duplicate log
    assert pipe.process_file(pdf(workdir, "TC01")).label == Label.APPROVE
    entry = pipe.confirm(first.run_id, "approve", "ok")
    assert entry["human_decision"] == "approve"
    again = pipe.process_file(pdf(workdir, "TC01"))
    assert again.label == Label.REJECT_HOLD and C.EXACT_DUPLICATE in codes(again)


def test_confirm_validation(make_pipeline, workdir):
    pipe = make_pipeline()
    r = pipe.process_file(pdf(workdir, "TC01"))
    assert pipe.confirm("nope", "approve").error_code == ErrorCode.INVALID_INPUT
    assert pipe.confirm(r.run_id, "maybe").error_code == ErrorCode.INVALID_INPUT
    assert not isinstance(pipe.confirm(r.run_id, "hold"), ErrorResponse)
    assert pipe.confirm(r.run_id, "hold").message.endswith("already confirmed.")


def test_confirm_refuses_run_without_validated_invoice(make_pipeline, workdir):
    pipe = make_pipeline(ScriptedProvider([ProviderError("down")]), mode="live")
    r = pipe.process_file(pdf(workdir, "TC01"), use_cache=False)
    assert isinstance(pipe.confirm(r.run_id, "approve"), ErrorResponse)


# ---------------------------------------------------------------- reproducibility, cache, logging
def _stable(res):
    d = json.loads(res.model_dump_json())
    for k in ("run_id", "started_at", "timings_ms", "input_file"):
        d.pop(k)
    return d


@pytest.mark.parametrize("case", ["TC01", "TC03", "TC05", "TC12"])
def test_same_input_gives_identical_decision_json(make_pipeline, workdir, case):
    a = make_pipeline().process_file(pdf(workdir, case))
    b = make_pipeline().process_file(pdf(workdir, case))
    assert _stable(a) == _stable(b)


def test_cache_avoids_second_llm_call_and_no_cache_bypasses_it(make_pipeline, workdir):
    p = ScriptedProvider([truth(workdir, "TC01")])
    pipe = make_pipeline(p, mode="live")
    r1 = pipe.process_file(pdf(workdir, "TC01"))
    r2 = pipe.process_file(pdf(workdir, "TC01"))
    assert len(p.calls) == 1 and r1.cached is False and r2.cached is True
    pipe.process_file(pdf(workdir, "TC01"), use_cache=False)
    assert len(p.calls) == 2


def test_api_key_never_appears_in_logs_or_results(make_pipeline, workdir, capfd):
    p = ScriptedProvider([ProviderError("down"), ])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    out = capfd.readouterr()
    assert "run_started" in out.err          # guard: logs really were captured, so the check below is meaningful
    blob = out.err + out.out + res.model_dump_json() + (workdir / "logs" / "runs.jsonl").read_text()
    assert "SECRET-KEY-123" not in blob


def test_logs_do_not_contain_invoice_text(make_pipeline, workdir, capfd):
    make_pipeline().process_file(pdf(workdir, "TC03"))
    err = capfd.readouterr().err
    assert "Acme Supplies" not in err and "47,500" not in err and "run_started" in err


def test_provider_error_message_with_digits_still_fails_safe(make_pipeline, workdir):
    # regression: "unavailable after 3 attempts" used to trip the traceability check and become INTERNAL_ERROR
    p = ScriptedProvider([ProviderError("LLM unavailable after 3 attempts (HTTP 503).", ErrorCode.LLM_UNAVAILABLE, True)])
    res = make_pipeline(p, mode="live").process_file(pdf(workdir, "TC01"), use_cache=False)
    assert not isinstance(res, ErrorResponse)
    assert res.label == Label.NEEDS_REVIEW and res.error.error_code == ErrorCode.LLM_UNAVAILABLE
