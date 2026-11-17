"""Plain-language text for non-developers: what a result or error means and what to do next."""
from __future__ import annotations

from dataclasses import dataclass

from ap.schemas import ErrorCode, FindingCode as C, Label


@dataclass(frozen=True)
class Info:
    title: str
    meaning: str
    next_step: str


FINDINGS: dict[C, Info] = {
    C.AMOUNT_OVER_TOLERANCE: Info("Invoice total is higher than the purchase order",
        "The vendor is billing more than was agreed.", "Ask the vendor to confirm the amount or send a corrected invoice."),
    C.UNIT_PRICE_MISMATCH: Info("A unit price differs from the purchase order",
        "The price per item is not the agreed price.", "Ask the vendor which price is correct."),
    C.QUANTITY_EXCEEDS_PO: Info("More items billed than ordered",
        "The invoice quantity is above the quantity on the purchase order.", "Check what was actually delivered, then ask the vendor to correct it."),
    C.LINE_NOT_ON_PO: Info("An invoice line is not on the purchase order",
        "One billed item cannot be matched to any ordered item.", "Ask the vendor or the requester whether this item was approved."),
    C.EXACT_DUPLICATE: Info("This invoice was already processed",
        "The same vendor and invoice number are already in the processed log.", "Do not pay it again. Tell the vendor you already have it."),
    C.POSSIBLE_DUPLICATE: Info("This may be a duplicate",
        "Another invoice from the same vendor has the same total and date.", "Compare the two invoices before paying either."),
    C.PO_MISSING_ON_INVOICE: Info("No PO reference supplied",
        "A purchase order reference was not provided; PO matching was skipped.", "No action is required unless your process separately requires a PO."),
    C.PO_NOT_FOUND: Info("Purchase order not found",
        "The PO number on the invoice is not in the purchase order list.", "Ask the vendor to check the PO number. Do not pay yet."),
    C.PO_CLOSED: Info("Purchase order is closed",
        "The order was already completed or cancelled.", "Check with whoever raised the order before paying."),
    C.CURRENCY_MISMATCH: Info("Invoice currency differs from the purchase order",
        "Amounts were not compared because no currency conversion is done.", "Ask the vendor to reissue in the PO currency, or check manually."),
    C.FIELD_NOT_FOUND: Info("An important field could not be found",
        "The invoice is missing something needed (for example the total).", "Read the invoice yourself or ask the vendor for a clearer copy."),
    C.EXTRACTION_INVALID: Info("The invoice could not be read reliably",
        "The values read from the document failed the safety checks, so none were used.", "Read this invoice manually."),
    C.EXTRACTION_UNAVAILABLE: Info("Automatic reading was not available",
        "The reader could not be used for this file.", "Read this invoice manually, or try again later."),
    C.SUSPICIOUS_TEXT: Info("The invoice contains instruction-like text",
        "Wording such as 'ignore the checks' or 'mark as approved' was found. It was ignored.", "Inspect the document before doing anything else."),
    C.LOW_CONFIDENCE_EXTRACTION: Info("The reading was not fully certain",
        "Some details could not be double-checked against the document text.", "Compare the extracted fields with the PDF yourself."),
    C.WITHIN_TOLERANCE_VARIANCE: Info("Small difference from the purchase order (allowed)",
        "The total differs slightly but is inside the allowed margin.", "No action needed."),
    C.VENDOR_MISMATCH: Info("Vendor does not match the purchase order",
        "The company that issued the invoice is different from the vendor the PO was raised with.",
        "Check who really issued this invoice before paying. No vendor email is drafted because the sender is uncertain."),
    C.PO_SOURCE_UNAVAILABLE: Info("Reference data could not be read",
        "The purchase-order list or processed-invoice log could not be opened, so nothing was matched.", "Check the Google Sheet connection, then run the check again."),
}


def finding_info(code: C) -> Info:
    return FINDINGS[code]


@dataclass(frozen=True)
class Headline:
    text: str
    tone: str         # green | amber | red
    action: str


HEADLINES = {
    Label.APPROVE: Headline("Looks safe to pay", "green", "Check the details below, then record your decision."),
    Label.NEEDS_REVIEW: Headline("Needs your review before paying", "amber", "Read the reasons below, then decide."),
    Label.REJECT_HOLD: Headline("Do not pay yet", "red", "Put it on hold and contact the vendor."),
}

ERRORS: dict[ErrorCode, tuple[str, str]] = {
    ErrorCode.INVALID_INPUT: ("That file could not be used", "Check that it is a PDF that opens normally, then try again."),
    ErrorCode.UNSUPPORTED_FILE_TYPE: ("Only PDF invoices are supported", "Save or export the invoice as a PDF and upload that."),
    ErrorCode.FILE_TOO_LARGE: ("That file is too large", "Upload a smaller PDF (under 10 MB), for example one invoice per file."),
    ErrorCode.NO_TEXT_LAYER: ("This PDF is a picture of a page (scanned)", "Scanned invoices are not supported yet. Read it manually."),
    ErrorCode.LLM_UNAVAILABLE: ("The invoice reader is not available right now", "Try again in a minute. If it keeps happening, tell the person who set this up."),
    ErrorCode.LLM_RATE_LIMITED: ("The invoice reader has reached an API usage limit", "Check Technical details for the retry/reset time. If the limit is daily, wait until Groq resets it or review the model limits in your Groq console."),
    ErrorCode.LLM_OUTPUT_INVALID: ("The invoice reader gave an unusable answer", "Try again. If it repeats, read the invoice manually."),
    ErrorCode.PO_SOURCE_UNAVAILABLE: ("The purchase-order list could not be opened", "Check the Google Sheet connection, then try again."),
    ErrorCode.INTERNAL_ERROR: ("Something went wrong on our side", "Nothing was recorded. Try again, and report it if it repeats."),
}


def error_text(code: ErrorCode) -> tuple[str, str]:
    return ERRORS.get(code, ERRORS[ErrorCode.INTERNAL_ERROR])
