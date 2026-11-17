"""Drives the real Streamlit app headlessly (streamlit.testing), clicking through it like a user.
This tests the app's logic and wording; it does not test how it looks in a browser."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(workdir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(workdir / "data"))
    monkeypatch.setenv("LOGS_DIR", str(workdir / "logs"))
    monkeypatch.setenv("CACHE_DIR", str(workdir / "cache"))
    monkeypatch.setenv("NOTIFY_BACKEND", "console")
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def btn(at, label):
    return next(b for b in at.button if b.label == label)


def pick_sample(at, case):
    at.radio[0].set_value("Use a sample invoice").run()
    opts = at.selectbox[0].options
    at.selectbox[0].select(next(o for o in opts if o.startswith(case + ":"))).run()
    btn(at, "Check this invoice").click().run()
    assert not at.exception, at.exception


def texts(at):
    out = [m.value for m in at.markdown] + [w.value for w in at.warning] + [s.value for s in at.success] \
          + [e.value for e in at.error] + [c.value for c in at.caption] + [i.value for i in at.info]
    return "\n".join(out)


def test_starts_in_demo_mode_with_status_in_sidebar(app):
    assert any("Demo mode" in w.value for w in app.sidebar.warning)
    assert any("local sample files" in m.value for m in app.sidebar.markdown)
    assert btn(app, "Check this invoice").disabled           # nothing chosen yet


def test_clean_invoice_shows_green_and_plain_language(app):
    pick_sample(app, "TC01")
    assert any("Looks safe to pay" in s.value for s in app.success)
    assert "Every check passed" in texts(app)
    assert "Demo mode" in texts(app)


def test_exception_shows_amber_reasons_and_draft_email(app):
    pick_sample(app, "TC03")
    assert any("Needs your review before paying" in w.value for w in app.warning)
    labels = " ".join(e.label for e in app.expander)
    assert "Invoice total is higher than the purchase order" in labels and "A unit price differs" in labels
    assert any("47,500.00" in c.value and "Subject:" in c.value for c in app.code)       # draft email shown
    assert any("never sends" in c.value for c in app.caption)


def test_duplicate_shows_red_do_not_pay(app):
    pick_sample(app, "TC05")
    assert any("Do not pay yet" in e.value for e in app.error)


def test_decision_requires_a_choice_then_records_it(app, workdir):
    pick_sample(app, "TC01")
    assert btn(app, "Record my decision").disabled           # no default choice (avoids nudging the reviewer)
    app.radio[1].set_value("Approve for payment").run()
    btn(app, "Record my decision").click().run()
    assert any("approved for payment" in s.value and "Nothing was paid or sent" in s.value for s in app.success)
    row = (workdir / "data" / "processed_invoices.csv").read_text().splitlines()[-1]
    assert "INV-5001" in row and "approve" in row


def test_recorded_invoice_is_then_held_as_duplicate(app):
    pick_sample(app, "TC01")
    app.radio[1].set_value("Approve for payment").run()
    btn(app, "Record my decision").click().run()
    btn(app, "Check this invoice").click().run()               # check the same invoice again
    assert any("Do not pay yet" in e.value for e in app.error)
    assert any("already processed" in e.label for e in app.expander)


def test_send_to_manager_reports_outcome(app, workdir):
    pick_sample(app, "TC03")
    assert any("above the amount your manager normally approves" in m.value for m in app.markdown)
    btn(app, "Send to manager").click().run()
    assert any("Printed to the console" in s.value for s in app.success)
    assert "escalated_to_manager" in (workdir / "logs" / "events.jsonl").read_text()


def test_no_manager_button_for_green_result(app):
    pick_sample(app, "TC01")
    assert not [b for b in app.button if b.label == "Send to manager"]


def test_missing_total_case_cannot_be_blamed_on_a_guess(app):
    pick_sample(app, "TC10")
    assert any("An important field could not be found" in e.label for e in app.expander)
    assert not app.code                                       # no vendor email built from unverified data


def test_history_appears_in_sidebar(app):
    pick_sample(app, "TC01")
    assert any("TC01.pdf" in str(d.value) for d in app.sidebar.dataframe)


def test_setup_check_runs_from_the_sidebar(app):
    btn(app, "Run check").click().run()
    shown = " ".join(m.value for m in app.sidebar.markdown)
    assert "Purchase orders" in shown and "✅" in shown


def test_app_explains_instead_of_crashing_when_data_source_is_misconfigured(workdir, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(workdir / "data"))
    monkeypatch.setenv("LOGS_DIR", str(workdir / "logs"))
    monkeypatch.setenv("STORAGE_BACKEND", "sheets")            # but no sheet id or key
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30); at.run()
    assert not at.exception
    assert any("could not start because its data source is not available" in e.value for e in at.error)
    assert "GOOGLE_SHEET_ID" in texts(at)


# ----------------------------------------------------------------- Day 4 usability review (expert review, not user feedback)
def test_check_another_invoice_resets_the_screen(app):
    pick_sample(app, "TC03")
    assert any(w for w in app.warning if "Needs your review" in w.value)
    btn(app, "Check another invoice").click().run()
    assert not any("Needs your review" in w.value for w in app.warning)
    assert btn(app, "Check this invoice").disabled
    assert not [b for b in app.button if b.label == "Check another invoice"]
