from dataclasses import dataclass
from typing import Protocol

from app.llm.schemas import ExtractedFact, RelationshipClassification


@dataclass(frozen=True)
class EvidenceInput:
    id: str
    text: str
    page_index: int


class LLMProvider(Protocol):
    async def extract_facts(
        self,
        *,
        document_name: str,
        evidence: list[EvidenceInput],
        limit: int,
    ) -> list[ExtractedFact]: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def classify_relationship(
        self, *, fact_a: str, evidence_a: str, fact_b: str, evidence_b: str
    ) -> RelationshipClassification: ...

    async def close(self) -> None: ...
