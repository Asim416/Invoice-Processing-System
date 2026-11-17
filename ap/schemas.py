from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[Decimal, Field(ge=0, decimal_places=2)]
SCHEMA_VERSION = "0.1"
PROMPT_VERSION = "v4-vision"


# ---------- Layer 1: wire contract (what the LLM must return) ----------
class LLMLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: float
    unit_price: float
    amount: float

    @field_validator("quantity", "unit_price", "amount", mode="before")
    @classmethod
    def _coerce(cls, v):
        return _num(v)


def _num(v):
    """Accept '47,500.00' (US thousands commas) as a number. Anything ambiguous is left alone and fails validation."""
    if isinstance(v, str):
        t = v.strip()
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", t):
            return float(t.replace(",", ""))
        try:
            return float(t)
        except ValueError:
            return v
    return v


class LLMExtraction(BaseModel):
    """Every field is required; unknown values must be null. Never guess."""
    model_config = ConfigDict(extra="forbid")
    vendor_name: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[str]      # YYYY-MM-DD or null
    po_number: Optional[str]
    currency: Optional[str]          # ISO 4217 code or null
    line_items: list[LLMLine]
    total: Optional[float]
    subtotal: Optional[float] = None
    tax_total: Optional[float] = None
    additional_charges: Optional[float] = None
    discount_total: Optional[float] = None

    @field_validator("total", mode="before")
    @classmethod
    def _coerce_total(cls, v):
        return _num(v)

    @field_validator("subtotal", "tax_total", "additional_charges", "discount_total", mode="before")
    @classmethod
    def _coerce_optional_money(cls, v):
        return _num(v) if v is not None else None


# ---------- Layer 2: domain models (validated, Decimal money) ----------
class InvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1)
    quantity: Decimal = Field(ge=0)
    unit_price: Money
    amount: Money


class ExtractedInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    po_number: Optional[str] = None
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    line_items: list[InvoiceLine] = Field(default_factory=list)
    total: Optional[Money] = None
    subtotal: Optional[Money] = None
    tax_total: Optional[Money] = None
    additional_charges: Optional[Money] = None
    discount_total: Optional[Money] = None

    @field_validator("vendor_name", "invoice_number", "po_number")
    @classmethod
    def blank_to_none(cls, v):
        return v.strip() or None if isinstance(v, str) else v


class POLine(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Money


class PORecord(BaseModel):
    po_number: str
    vendor_name: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    status: Literal["open", "closed"]
    total: Money
    lines: list[POLine]


class Label(str, Enum):
    APPROVE = "Approve"
    NEEDS_REVIEW = "Needs review"
    REJECT_HOLD = "Reject (hold)"


class FindingCode(str, Enum):
    AMOUNT_OVER_TOLERANCE = "AMOUNT_OVER_TOLERANCE"
    QUANTITY_EXCEEDS_PO = "QUANTITY_EXCEEDS_PO"
    UNIT_PRICE_MISMATCH = "UNIT_PRICE_MISMATCH"
    LINE_NOT_ON_PO = "LINE_NOT_ON_PO"
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    PO_MISSING_ON_INVOICE = "PO_MISSING_ON_INVOICE"
    PO_NOT_FOUND = "PO_NOT_FOUND"
    PO_CLOSED = "PO_CLOSED"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    FIELD_NOT_FOUND = "FIELD_NOT_FOUND"
    EXTRACTION_INVALID = "EXTRACTION_INVALID"
    EXTRACTION_UNAVAILABLE = "EXTRACTION_UNAVAILABLE"
    SUSPICIOUS_TEXT = "SUSPICIOUS_TEXT"
    LOW_CONFIDENCE_EXTRACTION = "LOW_CONFIDENCE_EXTRACTION"
    WITHIN_TOLERANCE_VARIANCE = "WITHIN_TOLERANCE_VARIANCE"
    PO_SOURCE_UNAVAILABLE = "PO_SOURCE_UNAVAILABLE"
    VENDOR_MISMATCH = "VENDOR_MISMATCH"


class Severity(str, Enum):
    BLOCK = "block"      # forces Reject (hold)
    REVIEW = "review"    # forces Needs review
    INFO = "info"        # shown, does not change the label


class Finding(BaseModel):
    code: FindingCode
    severity: Severity
    message: str                      # built by code from a template, never by the LLM
    evidence: dict[str, str | float | int | None] = Field(default_factory=dict)


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    NO_TEXT_LAYER = "NO_TEXT_LAYER"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_OUTPUT_INVALID = "LLM_OUTPUT_INVALID"
    PO_SOURCE_UNAVAILABLE = "PO_SOURCE_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorResponse(BaseModel):
    error_code: ErrorCode
    message: str
    retryable: bool
    run_id: Optional[str] = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    passed: bool
    attempts: int = Field(ge=0, le=2)
    confidence: Literal["high", "medium", "low", "none"]
    ungrounded_fields: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    repairs: list[str] = Field(default_factory=list)      # harmless format fixes applied, e.g. a stripped code fence


class RunResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    run_id: str
    started_at: datetime
    input_file: str
    input_sha256: str
    data_origin: Literal["synthetic", "public", "real"]
    extraction_mode: Literal["live", "mock", "ground_truth"]
    provider: Optional[str] = None
    model: Optional[str] = None
    extracted: Optional[ExtractedInvoice] = None
    validation: ValidationReport
    findings: list[Finding]
    label: Label
    requires_human_confirmation: Literal[True] = True
    vendor_email: Optional[str] = None
    internal_note: str
    timings_ms: dict[str, int]
    prompt_version: Optional[str] = None
    token_usage: Optional[dict[str, int]] = None
    cached: bool = False
    error: Optional[ErrorResponse] = None
