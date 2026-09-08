import re
import uuid
from dataclasses import dataclass

from app.llm.schemas import ExtractedFact
from app.models import Evidence


@dataclass(frozen=True)
class GroundingResult:
    accepted: bool
    reasons: list[str]


def _normalized_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _compact_value(value: str) -> str:
    return re.sub(r"[^\w.%+-]", "", value, flags=re.UNICODE).casefold()


def validate_grounding(candidate: ExtractedFact, evidence: Evidence) -> GroundingResult:
    reasons: list[str] = []
    try:
        evidence_id = uuid.UUID(candidate.evidence_id)
    except ValueError:
        return GroundingResult(False, ["evidence_id is not a UUID"])

    if evidence_id != evidence.id:
        reasons.append("evidence_id does not match the supporting evidence")

    evidence_text = _normalized_text(evidence.quote)
    quote = _normalized_text(candidate.supporting_quote)
    if not quote or quote not in evidence_text:
        reasons.append("supporting_quote is not a verbatim evidence substring")

    compact_value = _compact_value(candidate.value_raw)
    compact_evidence = _compact_value(evidence.quote)
    if not compact_value or compact_value not in compact_evidence:
        reasons.append("value_raw is not present in the evidence")

    if not candidate.subject.strip():
        reasons.append("subject is empty")
    if not candidate.predicate.strip():
        reasons.append("predicate is empty")

    return GroundingResult(not reasons, reasons)
