"""End-to-end pipeline. Orchestration only: each step lives in its own module."""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from ap import rules, safety
from ap.config import Policy, Settings
from ap.decision import decide
from ap.extraction.base import ProviderError, ProviderOutputInvalid
from ap.logging_setup import get_logger
from ap.pdf_text import PdfOpenError, extract_text
from ap.pdf_render import PdfRenderError, render_pdf_pages
from ap.schemas import (ErrorCode, ErrorResponse, ExtractedInvoice, Finding, FindingCode as C, Label, PROMPT_VERSION,
                        RunResult, Severity, ValidationReport)
from ap.storage import CsvStorage, Storage, StorageError
from ap.templates import render_internal_note, render_vendor_email, untraceable_numbers
from ap.validation import validate

log = get_logger("ap.pipeline")


class OutputValidationError(Exception):
    pass


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


class Pipeline:
    def __init__(self, settings: Settings, policy: Policy, storage: Storage, provider=None, mode: str = "mock"):
        self.settings, self.policy, self.storage, self.provider, self.mode = settings, policy, storage, provider, mode

    # ------------------------------------------------------------------ input
    def _load_input(self, path: Path) -> Union[tuple[bytes, str, Optional[list[bytes]]], ErrorResponse]:
        if not path.exists() or not path.is_file():
            return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, message=f"File not found: {path.name}", retryable=False)
        if path.suffix.lower() != ".pdf":
            return ErrorResponse(error_code=ErrorCode.UNSUPPORTED_FILE_TYPE, retryable=False,
                                 message=f"Only PDF files are supported. Received: {path.name}",
                                 details={"received_extension": path.suffix.lower()})
        size_mb = path.stat().st_size / (1024 * 1024)
        if size_mb > self.policy.max_file_mb:
            return ErrorResponse(error_code=ErrorCode.FILE_TOO_LARGE, retryable=False,
                                 message=f"File is {size_mb:.1f} MB; the limit is {self.policy.max_file_mb} MB.",
                                 details={"size_mb": round(size_mb, 1)})
        visual_enabled = self.mode == "live" and callable(getattr(self.provider, "extract_visual", None))
        try:
            text = extract_text(path)
        except PdfOpenError:
            if not visual_enabled:
                return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False,
                                     message=f"{path.name} could not be opened as a PDF.")
            # Visual extraction does not depend on an embedded PDF text layer.
            text = ""
        pages = None
        if visual_enabled:
            try:
                pages = render_pdf_pages(path)
            except PdfRenderError as exc:
                return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False,
                                     message=f"{path.name} could not be rendered for visual extraction: {exc}")
        return path.read_bytes(), text, pages

    # ------------------------------------------------------------- extraction
    def _cache_path(self, sha: str) -> Path:
        safe_model = self.settings.model.replace("/", "_")
        return self.settings.cache_dir / f"{sha}_{safe_model}_{PROMPT_VERSION}.json"

    def _extract_and_validate(self, text: str, sha: str, source: str, use_cache: bool,
                              override: Optional[dict], visual_pages: Optional[list[bytes]] = None):
        """Returns (extracted, validation_report, usage, cached, findings, error)."""
        visual_used = bool(visual_pages) and callable(getattr(self.provider, "extract_visual", None))
        policy = self.policy
        live = override is None and self.mode == "live"
        cached_raw, usage, cached = None, None, False
        if live and use_cache and self._cache_path(sha).exists():
            blob = json.loads(self._cache_path(sha).read_text())
            cached_raw, usage, cached = blob["raw"], blob.get("usage"), True
        max_attempts = 1 if override is not None else 1 + policy.extraction_retry_limit
        feedback, issues, ungrounded, attempts, raw = None, [], [], 0, None
        outcome = None
        for _ in range(max_attempts):
            attempts += 1
            if override is not None:
                raw = json.dumps(override)
            elif cached_raw is not None and attempts == 1:
                raw = cached_raw
            else:
                try:
                    if visual_used:
                        resp = self.provider.extract_visual(visual_pages, feedback, source=source)
                    else:
                        resp = self.provider.extract(text, feedback, source=source)
                    raw, usage, cached = resp.raw, resp.usage, False
                except ProviderOutputInvalid as exc:
                    issues, feedback, outcome = [str(exc)], str(exc), None
                    continue
                except ProviderError as exc:
                    report = ValidationReport(passed=False, attempts=attempts, confidence="none", issues=[str(exc)])
                    err = ErrorResponse(error_code=exc.code, message=str(exc), retryable=exc.retryable,
                                        details={"provider": getattr(self.provider, "name", None)})
                    return None, report, usage, cached, [Finding(
                        code=C.EXTRACTION_UNAVAILABLE, severity=Severity.REVIEW,
                        message="Automatic extraction was unavailable. The invoice must be read manually.",
                        evidence={"reason": exc.code.value})], err
            # Embedded text can be incomplete or incorrectly ordered. In vision mode the page
            # images are the source of truth, so do not let a lossy text layer erase valid fields.
            outcome = validate(raw, None if visual_used else (text or None), policy)
            if outcome.passed:
                break
            issues, ungrounded, feedback = outcome.issues, outcome.ungrounded, "; ".join(outcome.issues)
            cached_raw = None  # never reuse a cached answer that failed validation

        if outcome is not None and outcome.extracted is not None:
            ungrounded = outcome.ungrounded
            if outcome.passed and live and use_cache and not cached and raw:
                self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
                self._cache_path(sha).write_text(json.dumps({"raw": raw, "usage": usage}))
            # Fully valid extraction can be high confidence. A partial/flagged extraction is
            # retained for the reviewer but is never eligible for automatic approval.
            confidence = (("medium" if visual_used else ("high" if attempts == 1 and not ungrounded else "medium"))
                          if outcome.passed else "low")
            report = ValidationReport(passed=outcome.passed, attempts=attempts, confidence=confidence,
                                      ungrounded_fields=ungrounded, issues=outcome.issues,
                                      repairs=outcome.repairs)
            findings: list[Finding] = []
            if not outcome.passed:
                findings.append(Finding(code=C.EXTRACTION_INVALID, severity=Severity.REVIEW,
                                        message="Some extracted fields or line-item checks need human verification. Verified fields have been retained.",
                                        evidence={"attempts": attempts, "issues": " | ".join(outcome.issues)[:900]}))
            elif confidence != "high":
                findings.append(Finding(code=C.LOW_CONFIDENCE_EXTRACTION, severity=Severity.REVIEW,
                                        message=f"Extraction confidence is {confidence}. Verify the fields.",
                                        evidence={"attempts": attempts,
                                                  "ungrounded_fields": ", ".join(ungrounded) or None,
                                                  "note": "Visual extraction is not cross-checked against embedded PDF text." if visual_used else None}))
            return outcome.extracted, report, usage, cached, findings, None
        report = ValidationReport(passed=False, attempts=attempts, confidence="none", ungrounded_fields=ungrounded, issues=issues)
        return None, report, usage, cached, [Finding(
            code=C.EXTRACTION_INVALID, severity=Severity.REVIEW,
            message="The AI response could not be parsed into the required invoice fields. Manual extraction is required.",
            evidence={"attempts": attempts, "issues": " | ".join(issues)[:900]})], None

    # ------------------------------------------------------------------- main
    def process_file(self, path, *, use_cache: bool = True, extraction_override: Optional[dict] = None,
                     data_origin: str = "synthetic") -> Union[RunResult, ErrorResponse]:
        t_total = time.perf_counter()
        path = Path(path)
        loaded = self._load_input(path)
        if isinstance(loaded, ErrorResponse):
            log.info("input_rejected", extra={"error_code": loaded.error_code.value})
            return loaded
        data, text, visual_pages = loaded
        sha = hashlib.sha256(data).hexdigest()
        run_id = uuid.uuid4().hex[:12]
        started = datetime.now(timezone.utc)
        mode = "ground_truth" if extraction_override is not None else self.mode
        log.info("run_started", extra={"run_id": run_id, "mode": mode, "sha256": sha[:12]})

        findings: list[Finding] = []
        error: Optional[ErrorResponse] = None
        extracted: Optional[ExtractedInvoice] = None
        usage, cached = None, False
        wait_ms = 0

        sus = safety.scan(text)
        if sus:
            findings.append(Finding(code=C.SUSPICIOUS_TEXT, severity=Severity.REVIEW,
                                    message="The invoice text contains wording that looks like instructions to a system "
                                            "(it was ignored). Inspect the document.",
                                    evidence={"patterns": ", ".join(sus)}))

        t0 = time.perf_counter()
        if extraction_override is None and not text and not visual_pages:
            validation = ValidationReport(passed=False, attempts=0, confidence="none",
                                          issues=["The PDF has no readable text layer and visual extraction is unavailable."])
            findings.append(Finding(code=C.EXTRACTION_UNAVAILABLE, severity=Severity.REVIEW,
                                    message="The PDF has no readable text layer and no vision reader is configured.",
                                    evidence={"reason": "NO_TEXT_LAYER"}))
            error = ErrorResponse(error_code=ErrorCode.NO_TEXT_LAYER, retryable=False, run_id=run_id,
                                  message="The PDF has no text layer; configure a vision-capable Groq model to read scanned PDFs.")
        else:
            extracted, validation, usage, cached, fs, error = self._extract_and_validate(
                text, sha, path.stem, use_cache, extraction_override, visual_pages)
            findings += fs
            if error is not None:
                error.run_id = run_id
            wait_ms = getattr(self.provider, "last_wait_ms", 0) if (self.provider and extraction_override is None) else 0
        t_extract = _ms(t0)

        t0 = time.perf_counter()
        if extracted is not None:
            try:
                findings += rules.evaluate(extracted, self.storage, self.policy)
            except StorageError as exc:
                findings.append(Finding(code=C.PO_SOURCE_UNAVAILABLE, severity=Severity.REVIEW,
                                        message="The purchase-order list or the processed-invoice log could not be read, so the invoice was not matched.",
                                        evidence={"reason": str(exc)}))
                error = error or ErrorResponse(error_code=ErrorCode.PO_SOURCE_UNAVAILABLE, message=str(exc),
                                               retryable=True, run_id=run_id)
        t_rules = _ms(t0)

        label = decide(findings, validation)
        email = render_vendor_email(extracted, findings, validation)
        note = render_internal_note(label, extracted, findings, validation, self.policy)

        try:
            bad = untraceable_numbers([email], extracted, findings, self.policy)
            diagnostics = tuple(validation.issues) + ((error.message,) if error else ())
            bad |= untraceable_numbers([note], extracted, findings, self.policy, extra_facts=diagnostics)
            if bad:
                raise OutputValidationError(f"Generated text contains numbers not found in verified facts: {sorted(bad)}")
            if label == Label.APPROVE and any(f.severity != Severity.INFO for f in findings):
                raise OutputValidationError("Approve label is inconsistent with findings.")
            result = RunResult(
                run_id=run_id, started_at=started, input_file=str(path), input_sha256=sha, data_origin=data_origin,
                extraction_mode=mode, provider=(getattr(self.provider, "name", None) if mode == "live" else None),
                model=(getattr(self.provider, "model", None) if mode == "live" else None), extracted=extracted,
                validation=validation, findings=findings, label=label, vendor_email=email, internal_note=note,
                timings_ms={"extraction": t_extract, "rules": t_rules, "rate_limit_wait": int(wait_ms),
                            "total": _ms(t_total)},
                prompt_version=PROMPT_VERSION if mode == "live" else None, token_usage=usage, cached=cached, error=error)
        except OutputValidationError as exc:
            log.error("output_validation_failed", extra={"run_id": run_id})
            return ErrorResponse(error_code=ErrorCode.INTERNAL_ERROR, retryable=False, run_id=run_id, message=str(exc))

        try:
            self.storage.append_run(result)
        except (OSError, StorageError):      # a run-log failure must never hide the result from the reviewer
            log.error("run_log_write_failed", extra={"run_id": run_id})
        log.info("run_finished", extra={"run_id": run_id, "label": label.value,
                                        "finding_codes": [f.code.value for f in findings]})
        return result

    # ----------------------------------------------------------------- human step
    def confirm(self, run_id: str, decision: str, note: str = "") -> Union[dict, ErrorResponse]:
        if decision not in ("approve", "hold", "reject"):
            return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False,
                                 message="Decision must be approve, hold or reject.")
        run = self.storage.get_run(run_id)
        if run is None:
            return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False, message=f"Unknown run_id: {run_id}")
        if any(e.get("run_id") == run_id for e in self.storage.processed_entries()):
            return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False,
                                 message=f"Run {run_id} was already confirmed.")
        inv = run.get("extracted")
        if not inv or not inv.get("vendor_name") or not inv.get("invoice_number"):
            return ErrorResponse(error_code=ErrorCode.INVALID_INPUT, retryable=False,
                                 message="This run has no validated vendor and invoice number, so there is nothing to record.")
        from ap.storage import now_iso
        entry = {"vendor_name": inv["vendor_name"], "invoice_number": inv["invoice_number"],
                 "invoice_date": inv.get("invoice_date") or "", "total": inv.get("total") or "",
                 "currency": inv.get("currency") or "", "po_number": inv.get("po_number") or "",
                 "recommended_label": run["label"], "human_decision": decision, "run_id": run_id,
                 "confirmed_at": now_iso(), "note": note}
        self.storage.add_processed(entry)
        return entry
