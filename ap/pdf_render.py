"""Render PDF pages to compact JPEG images for multimodal invoice extraction."""
from __future__ import annotations

from pathlib import Path


class PdfRenderError(Exception):
    """The PDF could not be rendered into images."""


def render_pdf_pages(path: Path, *, scale: float = 2.0, jpeg_quality: int = 88) -> list[bytes]:
    """Return one JPEG byte string per page, preserving page order.

    PyMuPDF renders the PDF directly; no PDF text extraction or OCR is involved.
    """
    try:
        import fitz

        pages: list[bytes] = []
        with fitz.open(str(path)) as document:
            if document.needs_pass:
                raise PdfRenderError("The PDF is password-protected and cannot be rendered.")
            if document.page_count < 1:
                raise PdfRenderError("The PDF contains no pages.")
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                pages.append(pixmap.tobytes("jpeg", jpg_quality=jpeg_quality))
        return pages
    except PdfRenderError:
        raise
    except Exception as exc:
        raise PdfRenderError(f"Could not render PDF pages: {type(exc).__name__}.") from exc
