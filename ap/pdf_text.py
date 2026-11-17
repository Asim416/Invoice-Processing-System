"""PDF text-layer extraction with table-aware and coordinate-preserving fallbacks.

Scanned image-only PDFs remain unsupported. For digital PDFs, retain ordinary text and
append reconstructed table rows so headings and values remain associated.
"""
from __future__ import annotations
from pathlib import Path
import pdfplumber

class PdfOpenError(Exception):
    pass

def _table_text(page) -> str:
    blocks: list[str] = []
    options = [
        {"vertical_strategy": "lines", "horizontal_strategy": "lines", "intersection_tolerance": 5},
        {"vertical_strategy": "text", "horizontal_strategy": "text", "min_words_vertical": 1,
         "min_words_horizontal": 1, "text_tolerance": 3},
    ]
    seen: set[str] = set()
    for settings in options:
        try:
            tables = page.extract_tables(table_settings=settings) or []
        except Exception:
            continue
        for table in tables:
            rows = []
            for row in table or []:
                cells = [" ".join(str(cell or "").split()) for cell in row]
                if any(cells):
                    rows.append(" | ".join(cells))
            rendered = "\n".join(rows).strip()
            if rendered and rendered not in seen:
                seen.add(rendered)
                blocks.append(rendered)
    return "\n".join(blocks)

def _coordinate_rows(page) -> str:
    try:
        words = page.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False) or []
    except Exception:
        return ""
    if not words:
        return ""
    words.sort(key=lambda w: (round(float(w["top"]) / 4), float(w["x0"])))
    rows: list[list[dict]] = []
    for word in words:
        y = float(word["top"])
        if not rows or abs(y - float(rows[-1][0]["top"])) > 4:
            rows.append([word])
        else:
            rows[-1].append(word)
    return "\n".join(" | ".join(str(w["text"]) for w in sorted(row, key=lambda x: x["x0"]))
                     for row in rows if row).strip()

def extract_text(path: Path) -> str:
    try:
        pages: list[str] = []
        with pdfplumber.open(str(path)) as pdf:
            for page_no, page in enumerate(pdf.pages, 1):
                ordinary = page.extract_text(layout=True) or page.extract_text() or ""
                table = _table_text(page)
                coordinates = _coordinate_rows(page)
                parts: list[str] = []
                if ordinary.strip():
                    parts.append(f"[PAGE {page_no} TEXT]\n{ordinary}")
                if table:
                    parts.append(f"[PAGE {page_no} RECONSTRUCTED TABLE ROWS]\n{table}")
                if coordinates and not table:
                    parts.append(f"[PAGE {page_no} POSITIONED TEXT ROWS]\n{coordinates}")
                if parts:
                    pages.append("\n\n".join(parts))
    except Exception as exc:
        raise PdfOpenError(str(exc)) from exc
    return "\n\n".join(pages).strip()
