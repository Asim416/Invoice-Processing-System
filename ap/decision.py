"""Decision: the label is derived from findings by fixed logic. Approve must be earned."""
from __future__ import annotations

from ap.schemas import Finding, Label, Severity, ValidationReport


def decide(findings: list[Finding], validation: ValidationReport) -> Label:
    if any(f.severity == Severity.BLOCK for f in findings):
        return Label.REJECT_HOLD
    if any(f.severity == Severity.REVIEW for f in findings):
        return Label.NEEDS_REVIEW
    if not validation.passed or validation.confidence != "high":
        return Label.NEEDS_REVIEW   # safety net; normally a LOW_CONFIDENCE_EXTRACTION finding exists already
    return Label.APPROVE
