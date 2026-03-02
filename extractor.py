"""Extract text from PPTX and PDF files."""

import re
from pathlib import Path

from pptx import Presentation
from pypdf import PdfReader


def _normalize(text: str) -> str:
    """Normalize whitespace and strip."""
    if not text or not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text).strip()


def extract_pptx(path: str | Path) -> list[tuple[int, str]]:
    """Extract text from each slide of a PPTX file. Returns list of (slide_index, text)."""
    path = Path(path)
    if not path.suffix.lower() == ".pptx":
        raise ValueError(f"Expected .pptx file, got {path.suffix}")
    prs = Presentation(str(path))
    result: list[tuple[int, str]] = []
    for i, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                parts.append(shape.text)
        text = _normalize(" ".join(parts))
        if text:
            result.append((i, text))
    return result


def extract_pdf(path: str | Path) -> list[tuple[int, str]]:
    """Extract text from each page of a PDF. Returns list of (page_number, text)."""
    path = Path(path)
    if not path.suffix.lower() == ".pdf":
        raise ValueError(f"Expected .pdf file, got {path.suffix}")
    reader = PdfReader(str(path))
    result: list[tuple[int, str]] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text()
        text = _normalize(text or "")
        if text:
            result.append((i, text))
    return result


def extract(path: str | Path) -> list[tuple[int, str]]:
    """
    Extract text from a PPTX or PDF file. Infers format from extension.
    Returns list of (slide_or_page_index, text). Empty slides/pages are omitted.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        return extract_pptx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    raise ValueError(f"Unsupported format: {suffix}. Use .pptx or .pdf")
