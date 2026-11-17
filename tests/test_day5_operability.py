"""Day 5: what an operator needs: undo a mistake, see usage over time, trust the metrics."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from ap import adoption
from ap.config import Policy
from ap.rules import evaluate
from ap.schemas import FindingCode as C, Label
from ap.storage import CsvStorage
from tests.conftest import make_fake_sheet, pdf
from tests.test_rules import FakeStorage, inv, po, codes

POLICY = Policy()


# ------------------------------------------------------------------------------------------- void
def test_voided_entry_no_longer_counts_as_a_duplicate():
    seen = dict(vendor_name="Widget Co", invoice_number="INV-1", invoice_date="2026-09-01", total="1000.00", run_id="r1")
    assert C.EXACT_DUPLICATE in codes(evaluate(inv(), FakeStorage([po()], [dict(seen, human_decision="approve")]), POLICY))
    assert not codes(evaluate(inv(), FakeStorage([po()], [dict(seen, human_decision="void")]), POLICY)) & {C.EXACT_DUPLICATE, C.POSSIBLE_DUPLICATE}
    assert not codes(evaluate(inv(), FakeStorage([po()], [dict(seen, human_decision=" VOID ")]), POLICY)) & {C.EXACT_DUPLICATE}


def test_operator_can_void_a_mistaken_decision_by_editing_the_file(make_pipeline, workdir):
    pipe = make_pipeline()
    r = pipe.process_file(pdf(workdir, "TC01"))
    pipe.confirm(r.run_id, "approve")
    assert pipe.process_file(pdf(workdir, "TC01")).label == Label.REJECT_HOLD            # now a duplicate
    f = workdir / "data" / "processed_invoices.csv"
    f.write_text(f.read_text().replace(",approve,", ",void,"))                            # what the runbook tells the operator to do
    assert pipe.process_file(pdf(workdir, "TC01")).label == Label.APPROVE


# ------------------------------------------------------------------------------------------- run history
def test_csv_storage_returns_all_runs_and_events(make_pipeline, workdir):
    pipe = make_pipeline()
    a = pipe.process_file(pdf(workdir, "TC01")); b = pipe.process_file(pdf(workdir, "TC03"))
    pipe.storage.append_event({"run_id": b.run_id, "event": "escalated_to_manager", "detail": "x"})
    assert [r["run_id"] for r in pipe.storage.all_runs()] == [a.run_id, b.run_id]
    assert pipe.storage.all_events()[0]["event"] == "escalated_to_manager"
    assert CsvStorage(workdir / "none", workdir / "none").all_runs() == []


def test_sheets_storage_returns_all_runs_with_local_fallback(master_data, tmp_path):
    from ap.config import Settings
    from ap.extraction.mock import MockProvider
    from ap.pipeline import Pipeline
    from ap.storage_sheets import SheetsStorage
    sh = make_fake_sheet(master_data)
    st = SheetsStorage(sh, tmp_path / "logs", sleep=lambda x: None)
    pipe = Pipeline(Settings.from_env(data_dir=tmp_path, logs_dir=tmp_path / "logs"), Policy.load(), st,
                    MockProvider(master_data / "ground_truth"), "mock")
    a = pipe.process_file(master_data / "invoices" / "TC01.pdf"); b = pipe.process_file(master_data / "invoices" / "TC02.pdf")
    assert [r["run_id"] for r in st.all_runs()] == [a.run_id, b.run_id]
    sh.tabs["Runs"].rows[1][8] = json.dumps({"truncated": True})                           # a too-large row falls back to the local copy
    assert st.all_runs()[0]["run_id"] == a.run_id
    st.append_event({"run_id": a.run_id, "event": "escalated_to_manager", "detail": "ok"})
    assert st.all_events()[0]["event"] == "escalated_to_manager"


# ------------------------------------------------------------------------------------------- adoption metrics
T0 = datetime(2026, 12, 1, 9, 0, tzinfo=timezone.utc)


def run(i, label, day=0, minutes=0, vendor="V", number=None, total="100.00", cur="USD", codes_=(), mode="live", origin="real",
        error=None, attempts=1, conf="high", lat=2000, wait=0, tin=1000, tout=300):
    t = T0 + timedelta(days=day, minutes=minutes)
    return {"run_id": f"r{i}", "started_at": t.isoformat(), "label": label, "extraction_mode": mode, "data_origin": origin,
            "extracted": {"vendor_name": vendor, "invoice_number": number or f"N{i}", "total": total, "currency": cur},
            "findings": [{"code": c, "severity": "review"} for c in codes_] + [{"code": "WITHIN_TOLERANCE_VARIANCE", "severity": "info"}],
            "validation": {"attempts": attempts, "confidence": conf}, "error": error,
            "timings_ms": {"total": lat + wait, "rate_limit_wait": wait}, "token_usage": {"prompt_tokens": tin, "completion_tokens": tout}}


def dec(i, decision, after_min=5, day=0, start_min=0):
    return {"run_id": f"r{i}", "human_decision": decision,
            "confirmed_at": (T0 + timedelta(days=day, minutes=start_min + after_min)).isoformat()}


def test_adoption_metrics_against_hand_computed_values():
    runs = [run(1, "Approve", day=0), run(2, "Approve", day=0, minutes=10), run(3, "Reject (hold)", day=1, codes_=["EXACT_DUPLICATE"], total="500.00"),
            run(4, "Needs review", day=1, codes_=["AMOUNT_OVER_TOLERANCE"], total="2000.00"), run(5, "Approve", day=3, attempts=2),
            run(6, "Reject (hold)", day=3, codes_=["PO_NOT_FOUND"], total="50.00", cur="EUR"),
            run(7, "Needs review", day=3, error={"error_code": "LLM_UNAVAILABLE"})]
    processed = [dec(1, "approve", 4), dec(2, "hold", 10, start_min=10),        # run 2: person overrode an Approve
                 dec(3, "reject", 6, day=1), dec(4, "hold", 20, day=1),
                 dec(6, "approve", 3, day=3)]                                   # run 6: person approved a hold recommendation
    events = [{"run_id": "r4", "event": "escalated_to_manager"}, {"run_id": "r4", "event": "escalation_failed"}]
    m = adoption.compute(runs, processed, events)
    assert m["runs"] == 7 and m["active_days"] == 3 and m["by_day"] == {"2026-12-01": 2, "2026-12-02": 2, "2026-12-04": 3}
    assert m["labels"] == {"Approve": 3, "Reject (hold)": 2, "Needs review": 2}
    assert m["decisions_recorded"] == 5 and m["follow_through"] == pytest.approx(5 / 7)
    assert m["approve_overridden"] == (1, 2)                # runs 1,2 recorded; run 2 overridden; run 5 never recorded
    assert m["hold_overridden"] == (1, 2)                   # run 6 approved against a hold; run 3 agreed
    assert m["review_outcomes"] == {"hold": 1}
    # decision times: run1 4 min, run2 10, run3 6, run4 20, run6 3  ->  sorted 3,4,6,10,20  ->  median 6
    assert m["time_to_decision_min"]["median"] == pytest.approx(6.0) and m["time_to_decision_min"]["n"] == 5
    assert m["duplicates_caught"] == 1 and m["amount_held_or_rejected"] == {"USD": 2500.0}   # runs 3 (500) and 4 (2000) held/rejected
    assert m["errors"] == {"LLM_UNAVAILABLE": 1} and m["error_rate"] == pytest.approx(1 / 7)
    assert m["retry_rate"] == pytest.approx(1 / 7)
    assert m["escalations"] == {"sent": 1, "failed": 1}
    assert m["tokens_mean"] == {"in": 1000, "out": 300}


def test_throttle_wait_is_excluded_from_latency_and_cost_uses_given_prices():
    m = adoption.compute([run(1, "Approve", lat=2000, wait=5000)], [], [], price_in=1.0, price_out=2.0)
    assert m["live_latency_ms"]["p50"] == 2000
    assert m["notional_cost_total"] == pytest.approx((1000 * 1.0 + 300 * 2.0) / 1e6)


def test_voided_decisions_are_not_counted():
    runs = [run(1, "Approve")]
    m = adoption.compute(runs, [dec(1, "void")], [])
    assert m["decisions_recorded"] == 0


def test_window_filters_runs():
    runs = [run(1, "Approve", day=0), run(2, "Approve", day=10)]
    m = adoption.compute(runs, [], [], since=T0 + timedelta(days=5))
    assert m["runs"] == 1


def test_no_runs_is_handled():
    assert "No runs" in adoption.markdown(adoption.compute([], [], []))


def test_synthetic_traffic_is_loudly_labelled_and_real_traffic_is_not():
    synth = adoption.markdown(adoption.compute([run(1, "Approve", mode="mock", origin="synthetic")], [], []))
    assert "READ THIS FIRST" in synth and "NOT real adoption" in synth
    real = adoption.markdown(adoption.compute([run(1, "Approve", mode="live", origin="real")], [], []))
    assert "READ THIS FIRST" not in real and "Not measurable from logs" in real


def test_report_works_on_real_pipeline_output(make_pipeline, workdir):
    pipe = make_pipeline()
    r1 = pipe.process_file(pdf(workdir, "TC01")); pipe.confirm(r1.run_id, "approve")
    pipe.process_file(pdf(workdir, "TC05"))
    st = pipe.storage
    m = adoption.compute(st.all_runs(), st.processed_entries(), st.all_events())
    assert m["runs"] == 2 and m["decisions_recorded"] == 1 and m["duplicates_caught"] == 1
    assert "READ THIS FIRST" in adoption.markdown(m)                  # these runs are synthetic demo-mode runs


def test_reset_demo_clears_local_state_but_not_secrets(tmp_path):
    import shutil, sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    shutil.copytree(root / "scripts", tmp_path / "scripts")
    sys.path.insert(0, str(tmp_path / "scripts"))
    (tmp_path / "logs").mkdir(); (tmp_path / "logs" / "runs.jsonl").write_text("x")
    (tmp_path / "cache" / "extractions").mkdir(parents=True); (tmp_path / "cache" / "extractions" / "a.json").write_text("x")
    (tmp_path / ".env").write_text("LLM_API_KEY=keep-me")
    (tmp_path / "secrets").mkdir(); (tmp_path / "secrets" / "k.json").write_text("keep-me")
    import importlib.util
    spec = importlib.util.spec_from_file_location("reset_demo_t", tmp_path / "scripts" / "reset_demo.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    done = mod.reset(tmp_path)
    assert not (tmp_path / "logs" / "runs.jsonl").exists() and not (tmp_path / "cache" / "extractions").exists()
    assert (tmp_path / "data" / "processed_invoices.csv").exists() and (tmp_path / "data" / "invoices" / "TC03.pdf").exists()
    assert (tmp_path / ".env").read_text() == "LLM_API_KEY=keep-me" and (tmp_path / "secrets" / "k.json").exists()
    assert any("regenerated" in d for d in done)
