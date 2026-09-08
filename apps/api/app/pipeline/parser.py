import hashlib
from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass(frozen=True)
class ParsedElement:
    text: str
    bbox: list[float]
    reading_order: int
    element_type: str = "TEXT"
    extraction_method: str = "NATIVE_TEXT"
    confidence: float = 1.0


@dataclass(frozen=True)
class ParsedPage:
    page_index: int
    printed_page_label: str | None
    width: float
    height: float
    text: str
    content_hash: str
    elements: list[ParsedElement]


class PdfParser:
    def __init__(self, path: Path):
        self.path = path

    def page_count(self) -> int:
        with pymupdf.open(self.path) as document:
            return document.page_count

    def parse_page(self, page_index: int) -> ParsedPage:
        with pymupdf.open(self.path) as document:
            page = document.load_page(page_index)
            width = float(page.rect.width)
            height = float(page.rect.height)
            blocks = page.get_text("blocks", sort=True)

            elements: list[ParsedElement] = []
            for block in blocks:
                x0, y0, x1, y1, text, *_ = block
                text = text.strip()
                if not text:
                    continue
                # Some PDF text layers extend a few points beyond the media box (often footers).
                # Clamp coordinates so the frontend can safely treat them as normalized values.
                bbox = [
                    min(1.0, max(0.0, x0 / width)),
                    min(1.0, max(0.0, y0 / height)),
                    min(1.0, max(0.0, x1 / width)),
                    min(1.0, max(0.0, y1 / height)),
                ]
                elements.append(ParsedElement(text=text, bbox=bbox, reading_order=len(elements)))

            page_text = "\n\n".join(element.text for element in elements)
            return ParsedPage(
                page_index=page_index,
                printed_page_label=page.get_label() or None,
                width=width,
                height=height,
                text=page_text,
                content_hash=hashlib.sha256(page_text.encode()).hexdigest(),
                elements=elements,
            )
