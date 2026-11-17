"""Storage interface and CSV/JSONL implementation. Day 3 adds a Google Sheets adapter behind the same interface."""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Protocol

from ap.schemas import PORecord, POLine, RunResult


class StorageError(Exception):
    pass


class Storage(Protocol):
    def get_po(self, po_number: str) -> Optional[PORecord]: ...
    def list_pos(self) -> list[PORecord]: ...
    def processed_entries(self) -> list[dict]: ...
    def add_processed(self, entry: dict) -> None: ...
    def append_run(self, result: RunResult) -> None: ...
    def get_run(self, run_id: str) -> Optional[dict]: ...
    def recent_runs(self, limit: int = 20) -> list[dict]: ...
    def append_event(self, event: dict) -> None: ...
    def all_runs(self) -> list[dict]: ...
    def all_events(self) -> list[dict]: ...


PROCESSED_FIELDS = ["vendor_name", "invoice_number", "invoice_date", "total", "currency", "po_number",
                    "recommended_label", "human_decision", "run_id", "confirmed_at", "note"]


class CsvStorage:
    def __init__(self, data_dir: Path, logs_dir: Path):
        self.data_dir, self.logs_dir = Path(data_dir), Path(logs_dir)

    # ---- POs (read-only) ----
    def list_pos(self) -> list[PORecord]:
        try:
            with open(self.data_dir / "pos.csv", newline="") as f:
                headers = list(csv.DictReader(f))
            with open(self.data_dir / "po_lines.csv", newline="") as f:
                lines = list(csv.DictReader(f))
            by_po: dict[str, list[POLine]] = {}
            for r in lines:
                by_po.setdefault(r["po_number"], []).append(
                    POLine(description=r["description"], quantity=Decimal(r["quantity"]), unit_price=r["unit_price"]))
            return [PORecord(po_number=r["po_number"], vendor_name=r["vendor_name"], currency=r["currency"],
                             status=r["status"], total=r["total"], lines=by_po.get(r["po_number"], []))
                    for r in headers]
        except (OSError, KeyError, ValueError) as exc:
            raise StorageError(f"PO source unavailable or malformed: {type(exc).__name__}") from exc

    def get_po(self, po_number: str) -> Optional[PORecord]:
        target = po_number.strip().upper()
        for po in self.list_pos():
            if po.po_number.upper() == target:
                return po
        return None

    # ---- processed invoices (duplicate-check source; written only by confirm) ----
    def processed_entries(self) -> list[dict]:
        p = self.data_dir / "processed_invoices.csv"
        if not p.exists():
            return []
        try:
            with open(p, newline="") as f:
                return list(csv.DictReader(f))
        except OSError as exc:
            raise StorageError("Processed-invoice log unreadable") from exc

    def add_processed(self, entry: dict) -> None:
        p = self.data_dir / "processed_invoices.csv"
        new = not p.exists()
        with open(p, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PROCESSED_FIELDS)
            if new:
                w.writeheader()
            w.writerow({k: entry.get(k, "") for k in PROCESSED_FIELDS})

    # ---- run audit log ----
    def append_run(self, result: RunResult) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with open(self.logs_dir / "runs.jsonl", "a") as f:
            f.write(result.model_dump_json() + "\n")

    def recent_runs(self, limit: int = 20) -> list[dict]:
        p = self.logs_dir / "runs.jsonl"
        if not p.exists():
            return []
        rows = [run_summary(json.loads(l)) for l in p.read_text().splitlines() if l.strip()]
        return list(reversed(rows[-limit:]))

    def all_runs(self) -> list[dict]:
        p = self.logs_dir / "runs.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def all_events(self) -> list[dict]:
        p = self.logs_dir / "events.jsonl"
        return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

    def append_event(self, event: dict) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with open(self.logs_dir / "events.jsonl", "a") as f:
            f.write(json.dumps({"at": now_iso(), **event}) + "\n")

    def get_run(self, run_id: str) -> Optional[dict]:
        p = self.logs_dir / "runs.jsonl"
        if not p.exists():
            return None
        for line in p.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                if d.get("run_id") == run_id:
                    return d
        return None


def run_summary(d: dict) -> dict:
    """The few fields shown in a history list (never the full result)."""
    return {"run_id": d.get("run_id"), "started_at": d.get("started_at"),
            "file": Path(str(d.get("input_file", ""))).name, "label": d.get("label"),
            "findings": ", ".join(f["code"] for f in d.get("findings", []) if f.get("severity") != "info"),
            "confidence": (d.get("validation") or {}).get("confidence"), "mode": d.get("extraction_mode")}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
