# B. Input/Output Schemas and Data Contracts

> **Historical design document (Day 2).** Parts of it are superseded by later work (label anchoring, vendor-vs-PO check, number-format handling, void, run history). For how the system works now, read `docs/ARCHITECTURE.md`.


All contracts are Pydantic v2 models, defined in `ap/schemas.py`. The models below were executed and validated while writing this document (valid examples accepted; a lowercase currency code, a negative total and an unknown field were rejected). Stage 2 adopted them as `ap/schemas.py` (section 10 shows the implemented file, including three finding codes added during the build). Money and date normalization (for example lowercase `usd` becoming `USD`) happens in `ap/validation.py` before the domain model is built.

## 1. Two layers

| Layer | Purpose | Notes |
|---|---|---|
| Wire contract (`LLMExtraction`) | What the LLM must return | Plain JSON numbers and strings, every field required, unknown values must be `null`. Kept deliberately simple so strict structured output can enforce it |
| Domain models (`ExtractedInvoice`, ...) | What the rest of the system uses | `Decimal` money to 2 places, real dates, 3-letter uppercase currency, `extra="forbid"` |

The conversion from wire to domain happens in `ap/validation.py`. If it fails, that counts as a validation failure (retry once, then `EXTRACTION_INVALID`).

Note on the wire schema: Pydantic emits `$defs` references and `anyOf` with `null`. If Groq's strict mode rejects references, Stage 2 adds a small helper that inlines them. That cannot be verified from my sandbox; the first live run will show it.

## 2. Input contract (CLI)

| Input | Type | Required | Validation | Invalid behavior |
|---|---|---|---|---|
| `invoice_path` | file path | yes | Exists; extension `.pdf`; size at most `max_file_mb` (default 10); opens as a PDF | `ErrorResponse` (`INVALID_INPUT`, `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`); no run created |
| `--mode` | `live` or `mock` | no (default from config) | Enum | `INVALID_INPUT` |
| `--no-cache` | flag | no | | |
| `confirm run_id` | string | yes | `run_id` exists in `runs.jsonl` and has not been confirmed | `INVALID_INPUT` |
| `confirm --decision` | `approve`, `hold`, `reject` | yes | Enum | `INVALID_INPUT` |

Missing or empty PDF text is not an input error; it is handled as a finding (`EXTRACTION_UNAVAILABLE`) so the reviewer still gets a result.

## 3. Enumerations

| Enum | Values |
|---|---|
| `Label` | Approve; Needs review; Reject (hold) |
| `Severity` | block (forces Reject); review (forces Needs review); info (shown only) |
| `FindingCode` | AMOUNT_OVER_TOLERANCE, QUANTITY_EXCEEDS_PO, UNIT_PRICE_MISMATCH, LINE_NOT_ON_PO, EXACT_DUPLICATE, POSSIBLE_DUPLICATE, PO_MISSING_ON_INVOICE, PO_NOT_FOUND, PO_CLOSED, CURRENCY_MISMATCH, FIELD_NOT_FOUND, EXTRACTION_INVALID, EXTRACTION_UNAVAILABLE, SUSPICIOUS_TEXT, **LOW_CONFIDENCE_EXTRACTION**, **WITHIN_TOLERANCE_VARIANCE**, **PO_SOURCE_UNAVAILABLE** (the last three were added in Stage 2) |
| `ErrorCode` | INVALID_INPUT, UNSUPPORTED_FILE_TYPE, FILE_TOO_LARGE, NO_TEXT_LAYER, LLM_UNAVAILABLE, LLM_RATE_LIMITED, LLM_OUTPUT_INVALID, PO_SOURCE_UNAVAILABLE, INTERNAL_ERROR |

## 4. Finding severity map

| Code | Severity | Triggered by |
|---|---|---|
| EXACT_DUPLICATE | block | Same vendor and normalized invoice number in `processed_invoices.csv` |
| PO_NOT_FOUND | block | PO number not in `pos.csv` |
| PO_CLOSED | block | PO status closed |
| AMOUNT_OVER_TOLERANCE | review | Total above PO total by more than the tolerance |
| QUANTITY_EXCEEDS_PO | review | Billed quantity above PO quantity on any line |
| UNIT_PRICE_MISMATCH | review | Unit price differs from PO beyond tolerance |
| LINE_NOT_ON_PO | review | Invoice line cannot be matched to a PO line |
| POSSIBLE_DUPLICATE | review | Same vendor, total and date, different invoice number |
| PO_MISSING_ON_INVOICE | review | No PO number extracted. Candidate POs may be listed, never auto-selected |
| CURRENCY_MISMATCH | review | Currency differs from PO currency (no conversion) |
| FIELD_NOT_FOUND | review | A critical field is null (for example total) |
| EXTRACTION_INVALID | review | Validation failed after one retry |
| EXTRACTION_UNAVAILABLE | review | No text layer, or LLM unavailable after retries |
| SUSPICIOUS_TEXT | review | Embedded-instruction patterns found in the text |
| LOW_CONFIDENCE_EXTRACTION | review | Extraction needed a retry (medium) or a non-critical field could not be grounded (low) |
| PO_SOURCE_UNAVAILABLE | review | PO data could not be read, so the invoice was not matched |
| WITHIN_TOLERANCE_VARIANCE | info | Total differs from the PO but within tolerance (shown, not flagged) |

## 5. Policy configuration (`config/policy.yaml`)

```yaml
amount_tolerance_pct: 1.0
unit_price_tolerance_pct: 1.0
quantity_over_allowed: 0
supported_currencies: [USD, EUR]
max_file_mb: 10
extraction_retry_limit: 1
```

Thresholds are configuration, not code, so policy can change without editing logic. Changing one requires updating the test set to match.

## 6. Validation rules for extraction (step 6)

| Check | Rule | On failure |
|---|---|---|
| Schema | Wire JSON parses and matches `LLMExtraction` | Retry once with the error text, then `EXTRACTION_INVALID` |
| Domain conversion | Money to 2 decimals and at least 0; date parses; currency is 3 uppercase letters | Same |
| Line sum | Sum of line amounts equals total (within 0.01) when both present | Same |
| Line arithmetic | quantity x unit price equals amount (within 0.01) | Same |
| Grounding: strings | `vendor_name`, `invoice_number`, `po_number` appear in the PDF text after normalizing case, spaces and punctuation | Field treated as ungrounded; confidence lowered; if critical, `EXTRACTION_INVALID` |
| Grounding: numbers | `total` and line amounts appear in the text after removing thousands separators | Same |
| Grounding: dates | Day, month (name or number) and year components all appear in the text | Same (approximate; see limitations) |
| Grounding: currency | Code or symbol present in the text. `$` maps to USD within the supported set | Same |

Derived confidence (no LLM self-reported score): `high` = first attempt, everything grounded, sums match; `medium` = needed the retry; `low` = some non-critical field ungrounded; `none` = no usable extraction.

## 7. Output contract (`RunResult`)

Defined in full in the code below. Key properties:

- `label` is always present once a file is accepted. Failures degrade to Needs review, never to Approve.
- `requires_human_confirmation` is always `true`.
- `extraction_mode` is `live`, `mock` or `ground_truth`, so simulated runs cannot be mistaken for real model calls.
- `findings[].message` is built by code from templates. The LLM never writes reasons.
- `vendor_email` is `null` when the extraction was invalid or unavailable (no unverified data is sent to a vendor).
- `timings_ms` separates extraction, rules and total, and Stage 2 will add a separate `rate_limit_wait_ms` so throttling does not pollute latency.

## 8. Error response

Returned (and printed as JSON) when a file is rejected before a run exists, or when an internal error prevents releasing a result:

```json
{
  "error_code": "UNSUPPORTED_FILE_TYPE",
  "message": "Only PDF files are supported. Received: invoice.docx",
  "retryable": false,
  "run_id": null,
  "details": {
    "received_extension": ".docx"
  }
}
```

Behavior split: **input rejected** = `ErrorResponse` only. **Input accepted but a dependency fails** (LLM down, no text layer, invalid extraction) = a normal `RunResult` with label Needs review, the matching finding, and `error` populated.

## 9. Example: input and expected output (TC03, total over PO)

Synthetic data. Fictional vendor. The output below is the **expected** result for correct extraction, hand-specified from the Day 1 rules and arithmetic-checked (47,500 vs 45,000 is 5.56% over; 850 vs 800 is 6.25% over). It is not a measured run; `timings_ms` values are placeholders. Stage 3 reproduced it with the real v0; the actual output is in `docs/day2/evidence/TC03_mock_run.json`. The findings, labels and numbers match; the email subject and wording differ slightly, and money is formatted to two decimals (850.00 rather than 850.0) (see the stage report).

**PO record (`pos.csv` plus `po_lines.csv`)**

```json
{
  "po_number": "PO-1023",
  "vendor_name": "Acme Supplies Ltd",
  "currency": "USD",
  "status": "open",
  "total": "45000.00",
  "lines": [
    {
      "description": "Laptop 15 inch",
      "quantity": "50",
      "unit_price": "800.00"
    },
    {
      "description": "Docking station",
      "quantity": "50",
      "unit_price": "100.00"
    }
  ]
}
```

**Extraction the LLM should return (wire contract)**

```json
{
  "vendor_name": "Acme Supplies Ltd",
  "invoice_number": "4471",
  "invoice_date": "2026-11-02",
  "po_number": "PO-1023",
  "currency": "USD",
  "line_items": [
    {
      "description": "Laptop 15 inch",
      "quantity": 50,
      "unit_price": 850.0,
      "amount": 42500.0
    },
    {
      "description": "Docking station",
      "quantity": 50,
      "unit_price": 100.0,
      "amount": 5000.0
    }
  ],
  "total": 47500.0
}
```

**Expected `RunResult`**

```json
{
  "schema_version": "0.1",
  "run_id": "example-run-0001",
  "started_at": "2026-11-16T09:00:00Z",
  "input_file": "data/invoices/TC03.pdf",
  "input_sha256": "<sha256 of file>",
  "data_origin": "synthetic",
  "extraction_mode": "ground_truth",
  "provider": null,
  "model": null,
  "extracted": {
    "vendor_name": "Acme Supplies Ltd",
    "invoice_number": "4471",
    "invoice_date": "2026-11-02",
    "po_number": "PO-1023",
    "currency": "USD",
    "line_items": [
      {
        "description": "Laptop 15 inch",
        "quantity": "50",
        "unit_price": "850.0",
        "amount": "42500.0"
      },
      {
        "description": "Docking station",
        "quantity": "50",
        "unit_price": "100.0",
        "amount": "5000.0"
      }
    ],
    "total": "47500.0"
  },
  "validation": {
    "passed": true,
    "attempts": 1,
    "confidence": "high",
    "ungrounded_fields": [],
    "issues": []
  },
  "findings": [
    {
      "code": "AMOUNT_OVER_TOLERANCE",
      "severity": "review",
      "message": "Invoice total 47,500.00 USD exceeds PO total 45,000.00 USD by 2,500.00 (5.56%); tolerance is 1.00%.",
      "evidence": {
        "invoice_total": "47500.00",
        "po_total": "45000.00",
        "difference": "2500.00",
        "difference_pct": 5.56,
        "tolerance_pct": 1.0
      }
    },
    {
      "code": "UNIT_PRICE_MISMATCH",
      "severity": "review",
      "message": "Line 'Laptop 15 inch': unit price 850.00 vs PO 800.00 (6.25% higher); tolerance is 1.00%.",
      "evidence": {
        "line": "Laptop 15 inch",
        "invoice_unit_price": "850.00",
        "po_unit_price": "800.00",
        "difference_pct": 6.25,
        "tolerance_pct": 1.0
      }
    }
  ],
  "label": "Needs review",
  "requires_human_confirmation": true,
  "vendor_email": "Subject: Invoice 4471 does not match PO-1023\n\nHi Acme Supplies Ltd team,\n\nWe received invoice 4471 dated 2026-11-02 and compared it with PO-1023.\n\n- The invoice total is 47,500.00 USD but the PO total is 45,000.00 USD (difference 2,500.00, 5.56%).\n- Line 'Laptop 15 inch': unit price 850.00 on the invoice vs 800.00 on the PO (6.25% higher).\n\nCould you confirm the pricing or send a corrected invoice?\n\nThanks,\n[Sender name]",
  "internal_note": "NEEDS REVIEW. Invoice 4471 from Acme Supplies Ltd vs PO-1023: total over tolerance (5.56% vs 1.00% allowed) and one unit price above tolerance. Vendor email drafted. A human must confirm.",
  "timings_ms": {
    "extraction": 0,
    "rules": 0,
    "total": 0
  },
  "token_usage": null,
  "error": null
}
```

## 10. Schema source (as implemented in `ap/schemas.py`)

```python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Money = Annotated[Decimal, Field(ge=0, decimal_places=2)]
SCHEMA_VERSION = "0.1"
PROMPT_VERSION = "v1"


# ---------- Layer 1: wire contract (what the LLM must return) ----------
class LLMLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str
    quantity: float
    unit_price: float
    amount: float


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
```

## 11. Wire schema as emitted by Pydantic

```json
{
  "$defs": {
    "LLMLine": {
      "additionalProperties": false,
      "properties": {
        "description": {
          "title": "Description",
          "type": "string"
        },
        "quantity": {
          "title": "Quantity",
          "type": "number"
        },
        "unit_price": {
          "title": "Unit Price",
          "type": "number"
        },
        "amount": {
          "title": "Amount",
          "type": "number"
        }
      },
      "required": [
        "description",
        "quantity",
        "unit_price",
        "amount"
      ],
      "title": "LLMLine",
      "type": "object"
    }
  },
  "additionalProperties": false,
  "description": "Every field is required; unknown values must be null. Never guess.",
  "properties": {
    "vendor_name": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Vendor Name"
    },
    "invoice_number": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Invoice Number"
    },
    "invoice_date": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Invoice Date"
    },
    "po_number": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Po Number"
    },
    "currency": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "title": "Currency"
    },
    "line_items": {
      "items": {
        "$ref": "#/$defs/LLMLine"
      },
      "title": "Line Items",
      "type": "array"
    },
    "total": {
      "anyOf": [
        {
          "type": "number"
        },
        {
          "type": "null"
        }
      ],
      "title": "Total"
    }
  },
  "required": [
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "po_number",
    "currency",
    "line_items",
    "total"
  ],
  "title": "LLMExtraction",
  "type": "object"
}
```
