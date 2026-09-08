from app.llm.schemas import ExtractedFact
from app.pipeline.normalizer import (
    canonical_predicate,
    canonical_subject,
    normalize_period,
    normalize_value,
)


def candidate(**overrides) -> ExtractedFact:
    values = {
        "evidence_id": "b95a49f1-e9db-4353-b993-b6da55d8a111",
        "subject": "Delhivery Limited",
        "predicate": "Revenue from services",
        "predicate_canonical": "financial.revenue_from_services",
        "value_raw": "₹81,415 Mn",
        "unit": "INR million",
        "period": "FY24",
        "scope": None,
        "claim_kind": "OBSERVATION",
        "estimate_vintage": None,
        "supporting_quote": "₹81,415 Mn Revenue from services",
        "confidence": 0.98,
    }
    values.update(overrides)
    return ExtractedFact(**values)


def test_normalizes_inr_million_to_crore() -> None:
    result = normalize_value("₹81,415 Mn", "INR million")
    assert result.unit_canonical == "INR crore"
    assert result.canonical_numeric_value == 8141.5


def test_parenthesized_financial_value_is_negative() -> None:
    result = normalize_value("(452 Cr)", "Rs. Cr")
    assert result.canonical_numeric_value == -452


def test_normalizes_crore_without_an_explicit_currency_marker() -> None:
    result = normalize_value("127 Cr", "Cr")
    assert result.unit_canonical == "INR crore"
    assert result.canonical_numeric_value == 127


def test_canonical_subject_strips_corporate_suffix() -> None:
    assert canonical_subject("Delhivery Limited") == "delhivery"
    assert canonical_subject("Delhivery Ltd") == "delhivery"


def test_normalizes_fiscal_year_and_quarter() -> None:
    year = normalize_period("FY24")
    quarter = normalize_period("Q4 FY24")
    assert year.label == "FY2023/24"
    assert year.start.isoformat().startswith("2023-04-01")
    assert year.end.isoformat().startswith("2024-03-31")
    assert quarter.label == "Q4 FY2023/24"
    assert quarter.start.isoformat().startswith("2024-01-01")
    assert quarter.end.isoformat().startswith("2024-03-31")


def test_preserves_supplied_canonical_predicate() -> None:
    assert canonical_predicate(candidate()) == "financial.revenue_from_services"
