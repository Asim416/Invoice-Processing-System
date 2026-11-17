"""Label anchoring: a value must be printed next to the right label, not merely somewhere in the document.

Grounding proves a value exists in the text; anchoring proves it is the RIGHT value. It catches the dangerous errors
where a real but wrong identifier is chosen (customer reference as invoice number, delivery date as invoice date).

Design rule: a check applies only if the document contains at least one label of that kind. A layout that uses
unfamiliar wording gets no anchoring (and no false alarm) rather than a guess; this limitation is documented.
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Optional

INVOICE_NO = re.compile(r"(?:invoice|inv|bill)\s*(?:number|num|no|id)\b|(?:invoice|inv|bill)\s*#|document\s*(?:number|no)\b",
                        re.IGNORECASE)
TOTAL = re.compile(r"(?<!sub)(?<!line )(?:grand\s+)?total(?:\s+(?:due|amount|payable))?\b|amount\s+(?:due|payable)\b|balance\s+due\b|gross\s+worth\b|net\s+amount\b|invoice\s+amount\b",
                   re.IGNORECASE)
DATE = re.compile(r"(?:invoice|bill|issue|issued|tax)\s*date\b|date\s+of\s+(?:issue|invoice)\b|\bissued\b|\bdated\b|(?<![a-z])date\b",
                  re.IGNORECASE)
_NOT_INVOICE_DATE = ("due", "delivery", "order", "ship", "payment", "expir", "valid", "service", "ref", "po ")
_SEPARATORS = ".:#-–—\u00a0 \t\r\n"


def _tokens_after(text: str, end: int, n: int = 5) -> list[str]:
    return text[end:].lstrip(_SEPARATORS).split()[:n]


def _tokens_before(text: str, start: int, n: int = 4) -> list[str]:
    return text[:start].split()[-n:]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def invoice_number_anchored(value: str, text: str) -> Optional[bool]:
    """None = no invoice-number label in the document (cannot judge); True/False otherwise."""
    labels = list(INVOICE_NO.finditer(text))
    if not labels:
        return None
    want = _norm(value)
    for m in labels:
        toks = _tokens_after(text, m.end(), 4)
        if any(_norm("".join(toks[:k])) == want for k in range(1, len(toks) + 1)):
            return True
    return False


def total_anchored(value: Decimal, text: str, candidates) -> Optional[bool]:
    """The total must be the number printed right AFTER a total label. Only when no number follows the label (the value
    is printed before it, as in some layouts) are the words before it consulted. A subtotal printed before 'Total'
    therefore cannot pass for the total."""
    labels = list(TOTAL.finditer(text))
    if not labels:
        return None

    def numeric(tok):
        clean = tok.strip("$€£()").rstrip(",.")
        return candidates(clean) if clean and any(ch.isdigit() for ch in clean) else set()

    for m in labels:
        after = [numeric(t) for t in _tokens_after(text, m.end(), 4)]
        after = [c for c in after if c]
        pool = after if after else [numeric(t) for t in _tokens_before(text, m.start(), 3) if numeric(t)]
        if any(value in c for c in pool):
            return True

    # Table-aware anchoring: headers and values may be on separate rows in a PDF text layer.
    # Accept only when a total-like header and the extracted amount occupy the same column.
    total_headers = re.compile(r"(?:grand\s+total|total|amount\s+due|amount\s+payable|gross\s+worth|net\s+amount|invoice\s+total)", re.I)
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 2:
            continue
        matching = [j for j, cell in enumerate(cells) if total_headers.search(cell)]
        if not matching:
            continue
        for following in lines[i + 1:i + 5]:
            values = [c.strip() for c in following.split("|")]
            for j in matching:
                if j < len(values) and value in numeric(values[j]):
                    return True
    return False


def date_anchored(d: date, text: str, forms) -> Optional[bool]:
    flat = re.sub(r"\s+", " ", text.lower().replace(",", " "))
    labels = []
    for m in DATE.finditer(flat):
        before = flat[max(0, m.start() - 12):m.start()]
        if any(w in before for w in _NOT_INVOICE_DATE):
            continue
        labels.append(m)
    if not labels:
        return None
    for m in labels:
        window = re.sub(r"(?<=[a-z])\.", "", flat[m.end(): m.end() + 32])
        if any(form in window for form in forms):
            return True
    return False
