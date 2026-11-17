"""Google Sheets storage adapter (Day 3, integration 1).

The spreadsheet is the system of record for reference data and history:

  POs, PO_Lines      read-only to the pipeline (maintained by finance)
  Processed          duplicate-check source; written only by the human `confirm` step
  Runs               one row per run: summary columns + the full result JSON (so `confirm` works from any machine)
  Events             small audit trail (for example "escalated to manager")

Security and robustness notes
- Authentication is a service account key file whose path comes from GOOGLE_CREDENTIALS_FILE. The key is never logged.
- Least privilege: share ONE spreadsheet with the service account (Editor). Nothing else is reachable.
- Every write uses value_input_option="RAW", so vendor-supplied text such as "=HYPERLINK(...)" is stored as literal
  text and can never run as a formula.
- API calls retry on 429 and 5xx with backoff; anything else becomes a StorageError with a plain-language reason.
- A local copy of every run is also appended to logs/runs.jsonl (belt and braces audit trail).
"""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Callable, Optional

from ap.logging_setup import get_logger
from ap.schemas import POLine, PORecord, RunResult
from ap.storage import CsvStorage, PROCESSED_FIELDS, StorageError, now_iso, run_summary

log = get_logger("ap.sheets")

TABS = {
    "POs": ["po_number", "vendor_name", "currency", "status", "total"],
    "PO_Lines": ["po_number", "description", "quantity", "unit_price"],
    "Processed": PROCESSED_FIELDS,
    "Runs": ["run_id", "started_at", "input_file", "label", "finding_codes", "extraction_mode", "confidence",
             "total_ms", "result_json"],
    "Events": ["at", "run_id", "event", "detail"],
}
CELL_LIMIT = 45000          # Google Sheets allows 50,000 characters per cell
PO_CACHE_SECONDS = 60       # POs change rarely; this keeps us well under the API read quota


def _status_of(exc: Exception) -> Optional[int]:
    resp = getattr(exc, "response", None)
    return getattr(resp, "status_code", None)


class SheetsStorage:
    def __init__(self, spreadsheet, logs_dir: Path, *, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, service_account_email: str = ""):
        self.sh = spreadsheet
        self._local = CsvStorage(Path("."), logs_dir)         # only its run-log helpers are used
        self._sleep, self._clock = sleep, clock
        self._po_cache: tuple[float, list[PORecord]] | None = None
        self.service_account_email = service_account_email

    # ------------------------------------------------------------------ construction
    @classmethod
    def from_settings(cls, settings) -> "SheetsStorage":
        if not settings.google_sheet_id or not settings.google_credentials_file:
            raise StorageError("Google Sheets is selected but GOOGLE_SHEET_ID or GOOGLE_CREDENTIALS_FILE is not set "
                               "in .env.")
        key = Path(settings.google_credentials_file)
        if not key.exists():
            raise StorageError(f"The Google key file '{key.name}' was not found. Check GOOGLE_CREDENTIALS_FILE in .env.")
        try:
            import gspread
            gc = gspread.service_account(filename=str(key))
            email = json.loads(key.read_text()).get("client_email", "")
            return cls(gc.open_by_key(settings.google_sheet_id), settings.logs_dir, service_account_email=email)
        except StorageError:
            raise
        except Exception as exc:   # noqa: BLE001 - convert to a friendly message
            raise StorageError(cls._explain(exc, json.loads(key.read_text()).get("client_email", "")
                                            if key.exists() else "")) from exc

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _explain(exc: Exception, email: str = "") -> str:
        code = _status_of(exc)
        who = f" '{email}'" if email else " (the service account in your key file)"
        if code in (401, 403):
            return f"Google denied access to the spreadsheet. Share it with{who} as Editor."
        if code == 404 or type(exc).__name__ == "SpreadsheetNotFound":
            return "The spreadsheet was not found. Check GOOGLE_SHEET_ID in .env and that it is shared with the service account."
        if code == 429:
            return "Google Sheets is rate limiting requests. Wait a minute and try again."
        if code and code >= 500:
            return "Google Sheets is temporarily unavailable. Try again shortly."
        if type(exc).__name__ in ("WorksheetNotFound",):
            return "A required tab is missing from the spreadsheet. Run: python scripts/setup_sheet.py"
        return f"Could not reach Google Sheets ({type(exc).__name__})."

    def _call(self, fn: Callable, *args, **kwargs):
        last: Exception | None = None
        for attempt in range(1, 4):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:   # noqa: BLE001
                last = exc
                code = _status_of(exc)
                if code in (429, 500, 502, 503) and attempt < 3:
                    delay = 2 ** attempt
                    log.info("sheets_retry", extra={"attempt": attempt, "status": code, "delay_s": delay})
                    self._sleep(delay)
                    continue
                break
        raise StorageError(self._explain(last, self.service_account_email)) from last

    def _ws(self, name: str):
        return self._call(self.sh.worksheet, name)

    def _records(self, name: str) -> list[dict]:
        ws = self._ws(name)
        return self._call(ws.get_all_records, numericise_ignore=["all"])    # keep IDs like 00123 as text

    # ------------------------------------------------------------------ POs (read-only)
    def list_pos(self) -> list[PORecord]:
        now = self._clock()
        if self._po_cache and now - self._po_cache[0] < PO_CACHE_SECONDS:
            return self._po_cache[1]
        try:
            heads, lines = self._records("POs"), self._records("PO_Lines")
            by_po: dict[str, list[POLine]] = {}
            for r in lines:
                by_po.setdefault(str(r["po_number"]), []).append(
                    POLine(description=str(r["description"]), quantity=Decimal(str(r["quantity"])),
                           unit_price=str(r["unit_price"])))
            pos = [PORecord(po_number=str(r["po_number"]), vendor_name=str(r["vendor_name"]),
                            currency=str(r["currency"]).upper(), status=str(r["status"]).lower(),
                            total=str(r["total"]), lines=by_po.get(str(r["po_number"]), []))
                   for r in heads if str(r.get("po_number", "")).strip()]
        except StorageError:
            raise
        except (KeyError, ValueError, ArithmeticError) as exc:
            raise StorageError("The POs or PO_Lines tab has a missing column or an invalid value. "
                               "Expected columns: " + ", ".join(TABS["POs"]) + " / " + ", ".join(TABS["PO_Lines"])) from exc
        self._po_cache = (now, pos)
        return pos

    def get_po(self, po_number: str) -> Optional[PORecord]:
        target = po_number.strip().upper()
        return next((p for p in self.list_pos() if p.po_number.upper() == target), None)

    # ------------------------------------------------------------------ processed invoices
    def processed_entries(self) -> list[dict]:
        return self._records("Processed")      # never cached: duplicates must be detected immediately

    def add_processed(self, entry: dict) -> None:
        row = [str(entry.get(k, "")) for k in PROCESSED_FIELDS]
        self._call(self._ws("Processed").append_row, row, value_input_option="RAW")

    # ------------------------------------------------------------------ runs and events
    def append_run(self, result: RunResult) -> None:
        self._local.append_run(result)                      # local audit copy first; never lost
        blob = result.model_dump_json()
        if len(blob) > CELL_LIMIT:
            blob = json.dumps({"run_id": result.run_id, "truncated": True})
            log.error("run_json_too_large", extra={"run_id": result.run_id})
        row = [result.run_id, result.started_at.isoformat(), Path(result.input_file).name, result.label.value,
               ", ".join(f.code.value for f in result.findings if f.severity.value != "info"),
               result.extraction_mode, result.validation.confidence, result.timings_ms.get("total", 0), blob]
        self._call(self._ws("Runs").append_row, row, value_input_option="RAW")

    def get_run(self, run_id: str) -> Optional[dict]:
        ws = self._ws("Runs")
        ids = self._call(ws.col_values, 1)
        if run_id in ids:
            row = self._call(ws.row_values, ids.index(run_id) + 1)
            try:
                d = json.loads(row[8])
                if not d.get("truncated"):
                    return d
            except (IndexError, json.JSONDecodeError):
                pass
        return self._local.get_run(run_id)

    def all_runs(self) -> list[dict]:
        out = []
        for r in self._records("Runs"):
            try:
                d = json.loads(r.get("result_json", ""))
                if not d.get("truncated"):
                    out.append(d)
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            local = self._local.get_run(r.get("run_id", ""))      # the sheet row was too large or damaged: use the local copy
            if local:
                out.append(local)
        return out

    def all_events(self) -> list[dict]:
        return [{"at": r.get("at"), "run_id": r.get("run_id"), "event": r.get("event"), "detail": r.get("detail")}
                for r in self._records("Events")]

    def recent_runs(self, limit: int = 20) -> list[dict]:
        rows = self._records("Runs")[-limit:]
        out = []
        for r in rows:
            out.append({"run_id": r.get("run_id"), "started_at": r.get("started_at"), "file": r.get("input_file"),
                        "label": r.get("label"), "findings": r.get("finding_codes"),
                        "confidence": r.get("confidence"), "mode": r.get("extraction_mode")})
        return list(reversed(out))

    def append_event(self, event: dict) -> None:
        self._local.append_event(event)
        row = [now_iso(), str(event.get("run_id", "")), str(event.get("event", "")), str(event.get("detail", ""))]
        self._call(self._ws("Events").append_row, row, value_input_option="RAW")

    # ------------------------------------------------------------------ one-time setup
    def ensure_tabs(self) -> list[str]:
        """Create any missing tab with its header row. Returns the names of tabs it created."""
        created = []
        existing = {w.title for w in self._call(self.sh.worksheets)}
        for name, header in TABS.items():
            if name not in existing:
                ws = self._call(self.sh.add_worksheet, title=name, rows=1000, cols=max(len(header), 6))
                self._call(ws.append_row, header, value_input_option="RAW")
                created.append(name)
        return created
