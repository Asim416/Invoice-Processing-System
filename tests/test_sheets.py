"""Google Sheets adapter, tested against a fake spreadsheet that mimics gspread (no network)."""
import json

import pytest

from ap.config import Policy, Settings
from ap.pipeline import Pipeline
from ap.extraction.mock import MockProvider
from ap.schemas import ErrorCode, FindingCode as C, Label
from ap.storage import StorageError
from ap.storage_sheets import SheetsStorage, TABS
from tests.conftest import api_error, make_fake_sheet, pdf


@pytest.fixture
def sh(master_data):
    return make_fake_sheet(master_data)


@pytest.fixture
def store(sh, tmp_path):
    clock = {"t": 0.0}
    s = SheetsStorage(sh, tmp_path / "logs", sleep=lambda x: None, clock=lambda: clock["t"], service_account_email="bot@proj.iam")
    s._clock_box = clock
    return s


def test_reads_pos_with_lines(store):
    pos = {p.po_number: p for p in store.list_pos()}
    assert len(pos) == 12 and pos["PO-1023"].total == 45000 and len(pos["PO-1023"].lines) == 2
    assert store.get_po("po-1023").vendor_name == "Acme Supplies Ltd"          # case-insensitive lookup
    assert store.get_po("PO-NOPE") is None


def test_po_reads_are_cached_briefly_and_refresh_later(store, sh):
    store.list_pos(); store.list_pos()
    assert sh.tabs["POs"].calls.count("get_all_records") == 1
    store._clock_box["t"] = 61
    store.list_pos()
    assert sh.tabs["POs"].calls.count("get_all_records") == 2


def test_processed_entries_are_never_cached(store):
    n = len(store.processed_entries())
    store.add_processed({"vendor_name": "V", "invoice_number": "1", "run_id": "r"})
    assert len(store.processed_entries()) == n + 1


def test_writes_use_raw_mode_so_formulas_cannot_run(store, sh):
    evil = '=HYPERLINK("http://evil","click")'
    store.add_processed({"vendor_name": evil, "invoice_number": "1", "run_id": "r"})
    assert sh.tabs["Processed"].calls[-1][1] == "RAW"
    assert sh.tabs["Processed"].rows[-1][0] == evil                              # stored as literal text


def test_ids_with_leading_zeros_survive(store, sh):
    sh.tabs["Processed"].rows.append(["V", "00123", "", "", "", "", "", "", "r9", "", ""])
    assert store.processed_entries()[-1]["invoice_number"] == "00123"


def test_run_roundtrip_via_sheet_and_local_copy(store, master_data, tmp_path):
    from tests.conftest import truth
    pipe = Pipeline(Settings.from_env(data_dir=tmp_path, logs_dir=tmp_path / "logs"), Policy.load(), store,
                    MockProvider(master_data / "ground_truth"), "mock")
    res = pipe.process_file(master_data / "invoices" / "TC03.pdf")
    got = store.get_run(res.run_id)
    assert got["label"] == "Needs review" and got["run_id"] == res.run_id
    assert (tmp_path / "logs" / "runs.jsonl").exists()                          # local audit copy
    assert store.get_run("does-not-exist") is None
    rec = store.recent_runs(5)[0]
    assert rec["run_id"] == res.run_id and rec["label"] == "Needs review" and "AMOUNT_OVER_TOLERANCE" in rec["findings"]


def test_get_run_falls_back_to_local_copy(store, master_data, tmp_path, sh):
    pipe = Pipeline(Settings.from_env(data_dir=tmp_path, logs_dir=tmp_path / "logs"), Policy.load(), store,
                    MockProvider(master_data / "ground_truth"), "mock")
    res = pipe.process_file(master_data / "invoices" / "TC01.pdf")
    sh.tabs["Runs"].rows = sh.tabs["Runs"].rows[:1]                               # sheet row lost
    assert store.get_run(res.run_id)["run_id"] == res.run_id


def test_retries_rate_limit_then_succeeds(store, sh):
    sleeps = []
    store._sleep = sleeps.append
    sh.tabs["Processed"].fail = [api_error(429), api_error(503)]
    assert isinstance(store.processed_entries(), list) and sleeps == [2, 4]


def test_persistent_rate_limit_becomes_a_clear_error(store, sh):
    sh.tabs["Processed"].fail = [api_error(429)] * 5
    with pytest.raises(StorageError, match="rate limiting"):
        store.processed_entries()


def test_access_denied_message_names_the_account_to_share_with(store, sh):
    sh.fail_all = api_error(403)
    with pytest.raises(StorageError) as e:
        store.list_pos()
    assert "bot@proj.iam" in str(e.value) and "Editor" in str(e.value)


def test_missing_tab_message_points_to_setup(store, sh):
    del sh.tabs["Processed"]
    with pytest.raises(StorageError, match="setup_sheet"):
        store.processed_entries()


def test_malformed_po_tab_is_explained(store, sh):
    sh.tabs["POs"].rows[0] = ["po_number", "vendor_name"]                        # columns missing
    for r in sh.tabs["POs"].rows[1:]:
        del r[2:]
    with pytest.raises(StorageError, match="missing column"):
        store.list_pos()


def test_ensure_tabs_creates_missing_tabs_once(master_data, tmp_path):
    sh = make_fake_sheet(master_data, with_tabs=False)
    s = SheetsStorage(sh, tmp_path, sleep=lambda x: None)
    assert set(s.ensure_tabs()) == set(TABS)
    assert sh.tabs["Runs"].rows[0] == TABS["Runs"]
    assert s.ensure_tabs() == []


def test_setup_script_seeds_only_empty_tabs(master_data, tmp_path):
    from tests.scripts_path import load_setup_sheet
    mod = load_setup_sheet()
    sh = make_fake_sheet(master_data, seed=False)
    s = SheetsStorage(sh, tmp_path, sleep=lambda x: None)
    done = mod.seed(s, master_data)
    assert any("POs (12 rows)" in d for d in done) and len(sh.tabs["PO_Lines"].rows) > 12
    assert mod.seed(s, master_data) == []                                         # second run overwrites nothing


def test_from_settings_validates_configuration(tmp_path):
    with pytest.raises(StorageError, match="GOOGLE_SHEET_ID"):
        SheetsStorage.from_settings(Settings.from_env(storage_backend="sheets"))
    with pytest.raises(StorageError, match="was not found"):
        SheetsStorage.from_settings(Settings.from_env(storage_backend="sheets", google_sheet_id="x",
                                                      google_credentials_file=str(tmp_path / "nope.json")))


# ------------------------------------------------------------- the whole pipeline on top of Sheets
def make_pipe(store, master_data, tmp_path):
    return Pipeline(Settings.from_env(data_dir=tmp_path, logs_dir=tmp_path / "logs"), Policy.load(), store,
                    MockProvider(master_data / "ground_truth"), "mock")


def test_pipeline_end_to_end_on_sheets_including_duplicate_detection(store, master_data, tmp_path):
    pipe = make_pipe(store, master_data, tmp_path)
    r = pipe.process_file(master_data / "invoices" / "TC01.pdf")
    assert r.label == Label.APPROVE
    assert pipe.confirm(r.run_id, "approve")["human_decision"] == "approve"       # row lands in the Processed tab
    again = pipe.process_file(master_data / "invoices" / "TC01.pdf")
    assert again.label == Label.REJECT_HOLD and C.EXACT_DUPLICATE in {f.code for f in again.findings}
    seeded = pipe.process_file(master_data / "invoices" / "TC05.pdf")             # duplicate of a seeded sheet row
    assert seeded.label == Label.REJECT_HOLD


def test_sheet_outage_fails_safe_without_crashing(store, master_data, tmp_path, sh):
    pipe = make_pipe(store, master_data, tmp_path)
    sh.fail_all = api_error(500)
    store._sleep = lambda x: None
    r = pipe.process_file(master_data / "invoices" / "TC01.pdf")
    assert not hasattr(r, "error_code")                                           # a RunResult, not a crash
    assert r.label == Label.NEEDS_REVIEW and C.PO_SOURCE_UNAVAILABLE in {f.code for f in r.findings}
    assert r.error.error_code == ErrorCode.PO_SOURCE_UNAVAILABLE and "temporarily unavailable" in r.error.message
