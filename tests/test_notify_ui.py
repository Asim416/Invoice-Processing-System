"""Slack notifier (against a real local HTTP server), notification content, UI logic, doctor."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ap.config import Policy, Settings
from ap.doctor import run_checks
from ap.notify import ConsoleNotifier, NullNotifier, SlackWebhookNotifier, build_message, should_suggest_escalation
from ap.schemas import ErrorCode, ErrorResponse, Label
from ap.ui_logic import AppService, build_error_view, build_view, safe_filename
from tests.conftest import pdf


# ------------------------------------------------------------------- local fake Slack
class FakeSlack:
    def __init__(self, script):
        self.script, self.received = list(script), []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.received.append(json.loads(body))
                status, headers = outer.script.pop(0) if len(outer.script) > 1 else outer.script[0]
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers(); self.wfile.write(b"ok")

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}/services/T/B/SECRETTOKEN"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def slack():
    made = []

    def _make(script):
        f = FakeSlack(script); made.append(f); return f
    yield _make
    for f in made:
        f.close()


def test_slack_success_posts_text_json(slack):
    f = slack([(200, {})])
    o = SlackWebhookNotifier(f.url).send("hello")
    assert o.sent and f.received == [{"text": "hello"}]


def test_slack_retries_on_429_with_retry_after_then_succeeds(slack):
    f = slack([(429, {"Retry-After": "3"}), (200, {})])
    sleeps = []
    o = SlackWebhookNotifier(f.url, sleep=sleeps.append).send("x")
    assert o.sent and sleeps == [3.0] and len(f.received) == 2


def test_slack_retries_on_5xx(slack):
    f = slack([(500, {}), (502, {}), (200, {})])
    assert SlackWebhookNotifier(f.url, sleep=lambda s: None).send("x").sent


def test_slack_gives_up_after_max_attempts(slack):
    f = slack([(503, {})])
    o = SlackWebhookNotifier(f.url, sleep=lambda s: None).send("x")
    assert not o.sent and len(f.received) == 3 and "contact the manager another way" in o.detail


def test_slack_bad_webhook_is_not_retried_and_explained(slack):
    f = slack([(404, {})])
    o = SlackWebhookNotifier(f.url, sleep=lambda s: None).send("x")
    assert not o.sent and len(f.received) == 1 and "SLACK_WEBHOOK_URL" in o.detail


def test_slack_unreachable_is_handled(slack):
    o = SlackWebhookNotifier("http://127.0.0.1:9/hook", sleep=lambda s: None, max_attempts=2, timeout=1).send("x")
    assert not o.sent and "could not be reached" in o.detail


def test_webhook_secret_never_appears_in_outcome_or_logs(slack, capfd):
    f = slack([(404, {})])
    o = SlackWebhookNotifier(f.url, sleep=lambda s: None).send("x")
    out = capfd.readouterr()
    assert "SECRETTOKEN" not in o.detail + out.err + out.out


def test_null_and_console_notifiers():
    assert not NullNotifier().send("x").sent
    c = ConsoleNotifier(); assert c.send("hello").sent and c.sent_messages == ["hello"]


# ------------------------------------------------------------------- message content and escalation rule
@pytest.fixture
def svc(workdir):
    s = Settings.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs", cache_dir=workdir / "cache",
                          notify_backend="console")
    return AppService.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs", cache_dir=workdir / "cache",
                               notify_backend="console")


def run(svc, workdir, case):
    return svc.analyze_path(pdf(workdir, case))


def test_message_is_minimal_and_free_of_invoice_text(svc, workdir):
    r = run(svc, workdir, "TC03")
    msg = build_message(r, "please look")
    assert "Invoice 4471 from Acme Supplies Ltd" in msg and "47,500.00 USD" in msg and r.run_id in msg
    assert "Reviewer note: please look" in msg
    for leaked in ("Hi Acme", "Laptop 15 inch", "Docking station", "Subject:"):
        assert leaked not in msg


@pytest.mark.parametrize("case,expected", [("TC01", False),          # approve
                                           ("TC03", True),           # 47,500 over threshold
                                           ("TC08", False),          # held but only 950
                                           ("TC10", True)])          # total unknown
def test_escalation_suggestion_rule(svc, workdir, case, expected):
    assert should_suggest_escalation(run(svc, workdir, case), Policy.load()) is expected


# ------------------------------------------------------------------- view models and service
def test_view_for_each_label(svc, workdir):
    p = Policy.load()
    assert build_view(run(svc, workdir, "TC01"), p).tone == "green"
    v3 = build_view(run(svc, workdir, "TC03"), p)
    assert v3.tone == "amber" and v3.headline == "Needs your review before paying"
    assert v3.reasons[0].next_step and {r.severity for r in v3.reasons} <= {"review", "block", "info"}
    assert build_view(run(svc, workdir, "TC05"), p).tone == "red"


def test_view_orders_blocking_reasons_first_and_lists_fields(svc, workdir):
    v = build_view(run(svc, workdir, "TC02"), Policy.load())
    assert dict(v.fields)["Total"] == "4,512.00" and v.reasons[0].severity == "info"
    assert v.mode_is_demo and "Demo mode" in v.mode_note


def test_unreadable_file_in_demo_mode_explains_in_plain_language(svc, workdir, master_data):
    data = (pdf(workdir, "TC01")).read_bytes()
    r = svc.analyze_bytes("my_invoice.pdf", data)           # no fixture exists for this name
    v = build_view(r, Policy.load())
    assert "Demo mode can only read the built-in sample invoices" in v.reader_problem and not v.can_record


def test_uploaded_sample_bytes_work_when_named_like_a_sample(svc, workdir):
    r = svc.analyze_bytes("TC03.pdf", pdf(workdir, "TC03").read_bytes())
    assert r.label == Label.NEEDS_REVIEW


def test_bad_uploads_give_friendly_error_views(svc, workdir):
    e = svc.analyze_bytes("notes.docx", b"hello")
    assert isinstance(e, ErrorResponse)
    ev = build_error_view(e)
    assert ev.title == "Only PDF invoices are supported" and "PDF" in ev.what_to_do and ev.technical["code"] == "UNSUPPORTED_FILE_TYPE"
    assert build_error_view(svc.analyze_bytes("x.pdf", b"not a pdf")).title == "That file could not be used"


@pytest.mark.parametrize("raw,expected", [("../../etc/passwd.pdf", "passwd.pdf"), ("C:\\Users\\a\\inv 1.pdf", "inv 1.pdf"),
                                          ("we!rd$$name?.pdf", "we_rd__name_.pdf"), ("", "invoice.pdf")])
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


def test_record_decision_messages(svc, workdir):
    r = run(svc, workdir, "TC01")
    ok, msg = svc.record_decision(r.run_id, "approve", "checked")
    assert ok and "approved for payment" in msg and "Nothing was paid or sent" in msg
    ok2, msg2 = svc.record_decision(r.run_id, "approve")
    assert not ok2 and "already confirmed" in msg2
    assert not svc.record_decision("nope", "approve")[0]


def test_escalation_sends_and_logs_an_event(svc, workdir):
    r = run(svc, workdir, "TC03")
    out = svc.escalate(r.run_id, "urgent")
    assert out.sent and "Invoice 4471" in svc.notifier.sent_messages[0]
    events = (workdir / "logs" / "events.jsonl").read_text()
    assert "escalated_to_manager" in events and r.run_id in events


def test_escalation_failure_is_reported_not_raised(workdir, slack):
    f = slack([(404, {})])
    s = AppService.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs", cache_dir=workdir / "cache",
                            notify_backend="slack", slack_webhook_url=f.url)
    s.notifier._sleep = lambda x: None
    r = s.analyze_path(pdf(workdir, "TC03"))
    out = s.escalate(r.run_id)
    assert not out.sent and "SLACK_WEBHOOK_URL" in out.detail
    assert "escalation_failed" in (workdir / "logs" / "events.jsonl").read_text()


def test_history_lists_recent_runs_newest_first(svc, workdir):
    a = run(svc, workdir, "TC01"); b = run(svc, workdir, "TC03")
    h = svc.history()
    assert [x["run_id"] for x in h][:2] == [b.run_id, a.run_id] and h[0]["file"] == "TC03.pdf"


# ------------------------------------------------------------------- doctor
def test_doctor_reports_plain_language_problems(tmp_path):
    s = Settings.from_env(data_dir=tmp_path, logs_dir=tmp_path / "logs", extraction_mode="live", api_key="",
                          storage_backend="sheets", notify_backend="slack", slack_webhook_url="")
    checks = {c.name: c for c in run_checks(s)}
    assert checks["AI reader"].status == "fail" and "LLM_API_KEY" in checks["AI reader"].fix
    assert checks["Google Sheets"].status == "fail" and "GOOGLE_SHEET_ID" in checks["Google Sheets"].message
    assert checks["Manager alerts"].status == "fail"


def test_doctor_is_happy_with_defaults(workdir):
    s = Settings.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs")
    assert not [c for c in run_checks(s) if c.status == "fail"]


def test_doctor_never_prints_secrets(workdir):
    s = Settings.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs", api_key="SECRET-KEY-123",
                          slack_webhook_url="https://hooks.slack.com/services/SECRET", notify_backend="slack")
    blob = " ".join(f"{c.name} {c.message} {c.fix}" for c in run_checks(s))
    assert "SECRET" not in blob


def test_doctor_does_not_send_test_to_non_slack_address(slack, workdir):
    f = slack([(200, {})])
    s = Settings.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs", notify_backend="slack",
                          slack_webhook_url=f.url)
    c = {x.name: x for x in run_checks(s, send_test=True)}["Manager alerts"]
    assert c.status == "warn" and "does not look like a Slack webhook" in c.message
    assert f.received == []          # safety: a test message is never sent to an address that is not a Slack webhook


# ------------------------------------------------------------------- Day 4: warn early in demo mode
@pytest.mark.parametrize("name,mode,expected", [("my_invoice.pdf", "mock", True), ("TC03.pdf", "mock", False),
                                                ("C:\\Users\\a\\TC03.pdf", "mock", False), ("my_invoice.pdf", "live", False)])
def test_demo_warning_rule(name, mode, expected):
    from ap.ui_logic import needs_demo_warning
    assert needs_demo_warning(name, mode, {"TC01", "TC03"}) is expected
