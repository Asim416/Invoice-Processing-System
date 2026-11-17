"""UI-independent logic for the web app: turns pipeline results into plain-language view models.
Kept free of Streamlit imports so it can be unit-tested and reused by other interfaces."""
from __future__ import annotations

import csv
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from ap.config import Policy, Settings
from ap.fmt import money, qty
from ap.friendly import HEADLINES, error_text, finding_info
from ap.notify import NotifyOutcome, Notifier, build_message, should_suggest_escalation
from ap.pipeline import Pipeline
from ap.schemas import ErrorCode, ErrorResponse, RunResult
from ap.storage import Storage, StorageError

CONFIDENCE_TEXT = {
    "high": "High: every value was found in the invoice text and the arithmetic adds up.",
    "medium": "Medium: the invoice was read visually, but the extracted values could not be cross-checked against embedded PDF text. Please verify the fields.",
    "low": "Low: some details could not be double-checked against the document. Please verify the fields.",
    "none": "None: the invoice could not be read automatically.",
}


@dataclass
class Reason:
    title: str
    meaning: str
    detail: str
    next_step: str
    severity: str


@dataclass
class ResultView:
    run_id: str
    headline: str
    tone: str                       # green | amber | red
    action: str
    mode_note: str
    mode_is_demo: bool
    fields: list[tuple[str, str]]
    lines: list[dict]
    reasons: list[Reason]
    confidence_text: str
    vendor_email: Optional[str]
    internal_note: str
    escalate_suggested: bool
    can_record: bool
    cannot_record_reason: str = ""
    reader_problem: str = ""        # plain-language text if the reader was unavailable
    technical: dict = field(default_factory=dict)


@dataclass
class ErrorView:
    title: str
    what_to_do: str
    technical: dict


def build_view(r: RunResult, policy: Policy) -> ResultView:
    h = HEADLINES[r.label]
    inv = r.extracted
    fields: list[tuple[str, str]] = []
    lines: list[dict] = []
    if inv:
        fields = [("Vendor", inv.vendor_name or "NOT FOUND"), ("Invoice number", inv.invoice_number or "NOT FOUND"),
                  ("Invoice date", inv.invoice_date.isoformat() if inv.invoice_date else "NOT FOUND"),
                  ("PO number", inv.po_number or "—"), ("Currency", inv.currency or "NOT FOUND")]
        if inv.subtotal is not None:
            fields.append(("Subtotal", money(inv.subtotal)))
        if inv.tax_total is not None:
            fields.append(("Tax", money(inv.tax_total)))
        if inv.additional_charges is not None:
            fields.append(("Additional charges", money(inv.additional_charges)))
        if inv.discount_total is not None:
            fields.append(("Discounts", money(inv.discount_total)))
        fields.append(("Total", money(inv.total) if inv.total is not None else "NOT FOUND"))
        lines = [{"Item": l.description, "Qty": qty(l.quantity), "Unit price": money(l.unit_price),
                  "Amount": money(l.amount)} for l in inv.line_items]
    reasons = []
    for f in r.findings:
        info = finding_info(f.code)
        reasons.append(Reason(info.title, info.meaning, f.message, info.next_step, f.severity.value))
    order = {"block": 0, "review": 1, "info": 2}
    reasons.sort(key=lambda x: order[x.severity])
    if r.extraction_mode == "mock":
        mode_note, demo = ("Demo mode: this result uses a stored answer for the built-in sample invoices, "
                           "not a live AI reader."), True
    elif r.extraction_mode == "live":
        mode_note, demo = f"Read by AI ({r.provider} / {r.model}). The AI only reads the invoice; fixed rules make the recommendation.", False
    else:
        mode_note, demo = "Test mode (known-correct data).", True
    can = bool(inv and inv.vendor_name and inv.invoice_number)
    problem = ""
    if r.error:
        title, todo = error_text(r.error.error_code)
        problem = f"{title}. {todo}"
        if r.extraction_mode == "mock" and "fixture" in r.error.message.lower():
            problem = ("Demo mode can only read the built-in sample invoices. To read your own PDFs, "
                       "switch to live mode (see the setup guide).")
    return ResultView(
        run_id=r.run_id, headline=h.text, tone=h.tone, action=h.action, mode_note=mode_note, mode_is_demo=demo,
        fields=fields, lines=lines, reasons=reasons, confidence_text=CONFIDENCE_TEXT[r.validation.confidence],
        vendor_email=r.vendor_email, internal_note=r.internal_note, escalate_suggested=should_suggest_escalation(r, policy),
        can_record=can, cannot_record_reason="" if can else
        "There is no validated vendor and invoice number, so there is nothing to record. Handle this invoice manually.",
        reader_problem=problem,
        technical={"run_id": r.run_id, "mode": r.extraction_mode, "confidence": r.validation.confidence,
                   "attempts": r.validation.attempts, "timings_ms": r.timings_ms, "tokens": r.token_usage,
                   "error": r.error.model_dump(mode="json") if r.error else None})


def build_error_view(e: ErrorResponse) -> ErrorView:
    title, todo = error_text(e.error_code)
    return ErrorView(title, todo, {"code": e.error_code.value, "message": e.message, "retryable": e.retryable,
                                   **(e.details or {})})


def needs_demo_warning(upload_name: str, mode: str, sample_names: set[str]) -> bool:
    """In demo mode only the built-in samples can be read; warn BEFORE the user presses Check for anything else."""
    return mode != "live" and Path(safe_filename(upload_name)).stem not in sample_names


def safe_filename(name: str) -> str:
    base = re.split(r"[\\/]", name or "invoice.pdf")[-1]          # handles both / and \ separators
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base)[:120] or "invoice.pdf"
    return base


class AppService:
    """Everything the interface needs, in one object. No Streamlit here."""

    def __init__(self, settings: Settings, policy: Policy, pipeline: Pipeline, storage: Storage, notifier: Notifier):
        self.settings, self.policy, self.pipeline, self.storage, self.notifier = settings, policy, pipeline, storage, notifier

    @classmethod
    def from_env(cls, **overrides) -> "AppService":
        from ap.services import build_notifier, build_pipeline, build_storage
        settings = Settings.from_env(**overrides)
        storage = build_storage(settings)
        return cls(settings, Policy.load(), build_pipeline(settings, storage=storage), storage, build_notifier(settings))

    # ---- inputs
    def sample_invoices(self) -> list[tuple[str, Path]]:
        d = self.settings.data_dir / "invoices"
        return [(p.stem, p) for p in sorted(d.glob("TC*.pdf"))] if d.exists() else []

    def sample_labels(self) -> dict[str, str]:
        f = self.settings.data_dir / "expected_results.csv"
        if not f.exists():
            return {}
        with open(f, newline="") as fh:
            return {r["case_id"]: r["description"] for r in csv.DictReader(fh)}

    def analyze_bytes(self, filename: str, data: bytes) -> Union[RunResult, ErrorResponse]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / safe_filename(filename)
            path.write_bytes(data)
            return self.pipeline.process_file(path)

    def analyze_path(self, path: Path) -> Union[RunResult, ErrorResponse]:
        return self.pipeline.process_file(path)

    # ---- human actions
    def record_decision(self, run_id: str, decision: str, note: str = "") -> tuple[bool, str]:
        try:
            out = self.pipeline.confirm(run_id, decision, note)
        except StorageError as exc:
            return False, f"Your decision could not be saved: {exc}"
        if isinstance(out, ErrorResponse):
            return False, out.message
        words = {"approve": "approved for payment", "hold": "put on hold", "reject": "rejected"}[decision]
        return True, f"Recorded: invoice {out['invoice_number']} {words}. Nothing was paid or sent."

    def escalate(self, run_id: str, note: str = "") -> NotifyOutcome:
        try:
            raw = self.storage.get_run(run_id)
        except StorageError as exc:
            return NotifyOutcome(False, self.notifier.backend, str(exc))
        if raw is None:
            return NotifyOutcome(False, self.notifier.backend, "That run could not be found.")
        result = RunResult.model_validate(raw)
        outcome = self.notifier.send(build_message(result, note))
        try:
            self.storage.append_event({"run_id": run_id, "event": "escalated_to_manager" if outcome.sent else "escalation_failed",
                                       "detail": f"{outcome.backend}: {outcome.detail}"[:200]})
        except StorageError:
            pass        # the event log is secondary; never hide the notification outcome
        return outcome

    def history(self, limit: int = 15) -> list[dict]:
        try:
            return self.storage.recent_runs(limit)
        except StorageError:
            return []

    def status(self) -> dict:
        s = self.settings
        return {"mode": s.extraction_mode, "storage": s.storage_backend, "notify": self.notifier.backend,
                "model": s.model if s.extraction_mode == "live" else None}
