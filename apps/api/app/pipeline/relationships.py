from dataclasses import dataclass

from app.models import Fact


@dataclass(frozen=True)
class RuleDecision:
    relation: str
    confidence: float
    explanation: str
    differences: list[dict]
    comparison: dict
    final: bool = True


def _same_optional(left: str | None, right: str | None) -> bool:
    return not left or not right or left.casefold() == right.casefold()


def _values_close(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    scale = max(abs(left), abs(right), 1.0)
    return abs(left - right) / scale <= 0.01


def classify_with_rules(fact_a: Fact, fact_b: Fact) -> RuleDecision | None:
    same_subject = fact_a.subject_canonical == fact_b.subject_canonical
    same_predicate = fact_a.predicate_canonical == fact_b.predicate_canonical
    same_period = _same_optional(fact_a.period_label, fact_b.period_label)
    explicit_same_period = bool(
        fact_a.period_label
        and fact_b.period_label
        and fact_a.period_label.casefold() == fact_b.period_label.casefold()
    )
    scope_a = fact_a.context.get("scope")
    scope_b = fact_b.context.get("scope")
    same_scope = _same_optional(scope_a, scope_b)
    same_unit = _same_optional(fact_a.unit_canonical, fact_b.unit_canonical)
    value_match = _values_close(fact_a.canonical_numeric_value, fact_b.canonical_numeric_value)
    comparison = {
        "same_subject": same_subject,
        "same_predicate": same_predicate,
        "period_match": same_period,
        "period_explicitly_matched": explicit_same_period,
        "scope_match": same_scope,
        "unit_match": same_unit,
        "value_match": value_match,
    }

    if not same_subject or not same_predicate:
        return None

    if fact_a.period_label and fact_b.period_label and not same_period:
        return RuleDecision(
            "NOT_COMPARABLE",
            0.98,
            "The claims describe the same metric for different periods.",
            [{"dimension": "PERIOD", "fact_a": fact_a.period_label, "fact_b": fact_b.period_label}],
            comparison,
        )

    if not same_scope:
        return RuleDecision(
            "RECONCILABLE",
            0.95,
            "The values use different reporting scopes.",
            [{"dimension": "SCOPE", "fact_a": scope_a, "fact_b": scope_b}],
            comparison,
        )

    if fact_a.estimate_vintage and fact_b.estimate_vintage:
        if fact_a.estimate_vintage.casefold() != fact_b.estimate_vintage.casefold():
            return RuleDecision(
                "RECONCILABLE",
                0.97,
                "The claims use different estimate vintages, so the later value can "
                "update the earlier one.",
                [
                    {
                        "dimension": "VINTAGE",
                        "fact_a": fact_a.estimate_vintage,
                        "fact_b": fact_b.estimate_vintage,
                    }
                ],
                comparison,
            )

    if same_unit and value_match:
        return RuleDecision(
            "CORROBORATES",
            0.99,
            "The normalized values agree within a one percent rounding tolerance.",
            [],
            comparison,
        )

    if (
        fact_a.canonical_numeric_value is not None
        and fact_b.canonical_numeric_value is not None
        and same_unit
        and explicit_same_period
    ):
        qualifier = (
            "These are competing forecasts, not contradictory historical observations."
            if fact_a.claim_kind == fact_b.claim_kind == "FORECAST"
            else "The same metric, period, scope, and unit have materially different values."
        )
        return RuleDecision(
            "CONTRADICTS",
            0.9,
            qualifier,
            [
                {
                    "dimension": "VALUE",
                    "fact_a": fact_a.canonical_numeric_value,
                    "fact_b": fact_b.canonical_numeric_value,
                }
            ],
            comparison,
        )

    return None


def fact_summary(fact: Fact) -> str:
    return (
        f"subject={fact.subject_canonical}; predicate={fact.predicate_canonical}; "
        f"value={fact.normalized_value or fact.value_raw}; unit={fact.unit_canonical}; "
        f"period={fact.period_label}; claim_kind={fact.claim_kind}; "
        f"scope={fact.context.get('scope')}; estimate_vintage={fact.estimate_vintage}"
    )
