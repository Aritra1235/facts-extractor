from pathlib import Path

from app.pipeline.parser import PdfParser

FIXTURE = (
    Path(__file__).parents[3].parent
    / "starter-datasets"
    / "delhivery"
    / "03-delhivery-q4-fy24-earnings-presentation.pdf"
)


def test_parser_returns_normalized_bounding_boxes() -> None:
    parser = PdfParser(FIXTURE)
    parsed = parser.parse_page(5)

    assert "8,142" in parsed.text
    assert parsed.elements
    assert all(0 <= coordinate <= 1 for element in parsed.elements for coordinate in element.bbox)
    assert [element.reading_order for element in parsed.elements] == list(
        range(len(parsed.elements))
    )


def test_parser_reports_page_count() -> None:
    assert PdfParser(FIXTURE).page_count() == 27
