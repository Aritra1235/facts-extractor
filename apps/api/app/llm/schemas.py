from typing import Literal

from pydantic import BaseModel, Field

ClaimKind = Literal["OBSERVATION", "ESTIMATE", "FORECAST", "TARGET", "OPINION"]
RelationKind = Literal["CORROBORATES", "CONTRADICTS", "RECONCILABLE", "RELATED", "NOT_COMPARABLE"]


class ExtractedFact(BaseModel):
    evidence_id: str = Field(description="The supplied evidence identifier")
    subject: str = Field(description="Entity the claim is about")
    predicate: str = Field(description="Human-readable metric or property")
    predicate_canonical: str = Field(
        description="Stable lowercase dot notation, e.g. financial.revenue_from_services"
    )
    value_raw: str = Field(description="Value exactly as written in the evidence")
    unit: str | None = Field(default=None, description="Unit exactly as written")
    period: str | None = Field(default=None, description="Period exactly as written")
    scope: str | None = Field(default=None, description="Consolidated, standalone, segment, etc.")
    claim_kind: ClaimKind
    estimate_vintage: str | None = None
    supporting_quote: str = Field(description="Exact verbatim substring from the evidence")
    confidence: float = Field(ge=0, le=1)


class ExtractionBatch(BaseModel):
    facts: list[ExtractedFact]


class RelationshipClassification(BaseModel):
    relation: RelationKind
    confidence: float = Field(ge=0, le=1)
    explanation: str
    differences: list[str] = Field(default_factory=list)
