from app.models import Fact
from app.pipeline.relationships import classify_with_rules


def fact(**overrides) -> Fact:
    values = {
        "subject_raw": "Delhivery",
        "subject_canonical": "delhivery",
        "predicate_raw": "Revenue from services",
        "predicate_canonical": "financial.revenue_from_services",
        "value_raw": "₹8,142 Cr",
        "value_kind": "NUMBER",
        "numeric_value": 8142.0,
        "normalized_value": "8142.0",
        "unit_raw": "INR crore",
        "unit_canonical": "INR crore",
        "canonical_numeric_value": 8142.0,
        "claim_kind": "OBSERVATION",
        "period_label": "FY2023/24",
        "estimate_vintage": None,
        "context": {"scope": None},
        "confidence": 0.98,
        "extractor_version": "test",
    }
    values.update(overrides)
    return Fact(**values)


def test_rounding_difference_corroborates() -> None:
    decision = classify_with_rules(
        fact(canonical_numeric_value=8141.5), fact(canonical_numeric_value=8142.0)
    )
    assert decision.relation == "CORROBORATES"


def test_different_estimate_vintages_reconcile() -> None:
    decision = classify_with_rules(
        fact(
            subject_raw="India",
            subject_canonical="india",
            predicate_raw="Real GDP growth",
            predicate_canonical="macroeconomic.real_gdp_growth",
            canonical_numeric_value=6.4,
            unit_canonical="percent",
            estimate_vintage="First Advance Estimate",
        ),
        fact(
            subject_raw="India",
            subject_canonical="india",
            predicate_raw="Real GDP growth",
            predicate_canonical="macroeconomic.real_gdp_growth",
            canonical_numeric_value=6.5,
            unit_canonical="percent",
            estimate_vintage="Second Advance Estimate",
        ),
    )
    assert decision.relation == "RECONCILABLE"


def test_different_periods_are_not_comparable() -> None:
    decision = classify_with_rules(fact(period_label="FY2022/23"), fact())
    assert decision.relation == "NOT_COMPARABLE"


def test_missing_period_does_not_create_a_false_contradiction() -> None:
    decision = classify_with_rules(
        fact(period_label=None, canonical_numeric_value=7000),
        fact(canonical_numeric_value=8000),
    )
    assert decision is None
