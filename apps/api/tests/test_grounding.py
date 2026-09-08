import uuid

from app.llm.schemas import ExtractedFact
from app.models import Evidence
from app.pipeline.grounding import validate_grounding


def test_accepts_exact_grounded_fact() -> None:
    evidence_id = uuid.uuid4()
    evidence = Evidence(
        id=evidence_id,
        document_id=uuid.uuid4(),
        page_id=uuid.uuid4(),
        quote="₹81,415 Mn Revenue from services",
        element_ids=[],
        bboxes=[],
    )
    candidate = ExtractedFact(
        evidence_id=str(evidence_id),
        subject="Delhivery",
        predicate="Revenue from services",
        predicate_canonical="financial.revenue_from_services",
        value_raw="₹81,415 Mn",
        unit="INR million",
        period="FY24",
        scope=None,
        claim_kind="OBSERVATION",
        estimate_vintage=None,
        supporting_quote="₹81,415 Mn Revenue from services",
        confidence=0.98,
    )
    assert validate_grounding(candidate, evidence).accepted


def test_rejects_invented_quote() -> None:
    evidence_id = uuid.uuid4()
    evidence = Evidence(
        id=evidence_id,
        document_id=uuid.uuid4(),
        page_id=uuid.uuid4(),
        quote="Revenue was strong.",
        element_ids=[],
        bboxes=[],
    )
    candidate = ExtractedFact(
        evidence_id=str(evidence_id),
        subject="Delhivery",
        predicate="Revenue",
        predicate_canonical="financial.revenue",
        value_raw="₹8,142 Cr",
        unit="INR crore",
        period="FY24",
        scope=None,
        claim_kind="OBSERVATION",
        estimate_vintage=None,
        supporting_quote="₹8,142 Cr revenue",
        confidence=0.9,
    )
    result = validate_grounding(candidate, evidence)
    assert not result.accepted
    assert len(result.reasons) == 2
