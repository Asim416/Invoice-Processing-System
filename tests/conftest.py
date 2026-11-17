import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ap.config import Policy, Settings            # noqa: E402
from ap.pipeline import Pipeline                  # noqa: E402
from ap.storage import CsvStorage                 # noqa: E402
import generate_data                              # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """A developer's real .env (keys, Sheet ids, webhooks) must never leak into tests."""
    for k in ("SLACK_WEBHOOK_URL", "GOOGLE_SHEET_ID", "GOOGLE_CREDENTIALS_FILE", "DATA_DIR", "LOGS_DIR", "CACHE_DIR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EXTRACTION_MODE", "mock")
    monkeypatch.setenv("STORAGE_BACKEND", "csv")
    monkeypatch.setenv("NOTIFY_BACKEND", "none")


@pytest.fixture(scope="session")
def master_data(tmp_path_factory):
    d = tmp_path_factory.mktemp("master") / "data"
    generate_data.generate(d)
    return d


@pytest.fixture
def workdir(tmp_path, master_data):
    """Fresh isolated copy of the seeded data for every test."""
    shutil.copytree(master_data, tmp_path / "data")
    return tmp_path


class ScriptedProvider:
    """Stand-in for an LLM provider. Each call consumes the next scripted outcome:
    an Exception (raised), or a str / dict (returned as the raw model output)."""
    name, model, last_wait_ms = "fake", "fake-model", 0

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def extract(self, text, feedback=None, *, source=""):
        from ap.extraction.base import ExtractionResponse
        self.calls.append(feedback)
        o = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(o, Exception):
            raise o
        raw = o if isinstance(o, str) else json.dumps(o)
        return ExtractionResponse(raw=raw, usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})


@pytest.fixture
def make_pipeline(workdir):
    def _make(provider=None, mode="mock", **policy_over):
        settings = Settings.from_env(data_dir=workdir / "data", logs_dir=workdir / "logs",
                                     cache_dir=workdir / "cache", api_key="SECRET-KEY-123", model="fake-model")
        policy = Policy.load()
        if policy_over:
            from dataclasses import replace
            policy = replace(policy, **policy_over)
        storage = CsvStorage(workdir / "data", workdir / "logs")
        if provider is None and mode == "mock":
            from ap.extraction.mock import MockProvider
            provider = MockProvider(workdir / "data" / "ground_truth")
        return Pipeline(settings, policy, storage, provider, mode)
    return _make


def truth(workdir, case):
    return json.loads((workdir / "data" / "ground_truth" / f"{case}.json").read_text())


def pdf(workdir, case):
    return workdir / "data" / "invoices" / f"{case}.pdf"


# ----------------------------------------------------------------------------- fake Google Sheets
import csv as _csv                                   # noqa: E402
from types import SimpleNamespace as _NS             # noqa: E402

from gspread.exceptions import APIError, WorksheetNotFound   # noqa: E402


def api_error(code):
    return APIError(_NS(status_code=code, text="x", json=lambda: {"error": {"code": code, "message": "x", "status": "X"}}))


class FakeWorksheet:
    def __init__(self, title, header):
        self.title, self.rows, self.calls = title, [list(header)], []
        self.fail = []                                   # exceptions to raise on the next calls

    def _maybe_fail(self):
        if self.fail:
            raise self.fail.pop(0)

    def get_all_records(self, numericise_ignore=None):
        self._maybe_fail(); self.calls.append("get_all_records")
        h = self.rows[0]
        return [dict(zip(h, [str(v) for v in r])) for r in self.rows[1:]]

    def get_all_values(self):
        self._maybe_fail(); return [list(r) for r in self.rows]

    def append_row(self, row, value_input_option=None):
        self._maybe_fail(); self.calls.append(("append_row", value_input_option)); self.rows.append(list(row))

    def append_rows(self, rows, value_input_option=None):
        self._maybe_fail(); self.calls.append(("append_rows", value_input_option)); self.rows.extend(list(r) for r in rows)

    def col_values(self, n):
        self._maybe_fail(); return [r[n - 1] for r in self.rows if len(r) >= n]

    def row_values(self, n):
        self._maybe_fail(); return list(self.rows[n - 1])


class FakeSpreadsheet:
    def __init__(self):
        self.tabs = {}
        self.fail_all = None                            # set to an exception to simulate an outage

    def worksheet(self, name):
        if self.fail_all:
            raise self.fail_all
        if name not in self.tabs:
            raise WorksheetNotFound(name)
        return self.tabs[name]

    def worksheets(self):
        if self.fail_all:
            raise self.fail_all
        return list(self.tabs.values())

    def add_worksheet(self, title, rows, cols):
        self.tabs[title] = FakeWorksheet(title, [])
        self.tabs[title].rows = []
        return self.tabs[title]


def make_fake_sheet(master_data, with_tabs=True, seed=True):
    from ap.storage_sheets import TABS
    sh = FakeSpreadsheet()
    if with_tabs:
        for name, header in TABS.items():
            sh.tabs[name] = FakeWorksheet(name, header)
        if seed:
            for tab, fname in {"POs": "pos.csv", "PO_Lines": "po_lines.csv", "Processed": "processed_invoices.csv"}.items():
                with open(master_data / fname, newline="") as f:
                    for r in _csv.DictReader(f):
                        sh.tabs[tab].rows.append([r.get(h, "") for h in TABS[tab]])
    return sh
