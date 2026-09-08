import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.base import EvidenceInput, LLMProvider
from app.models import Document, Evidence, Fact, FactRelationship, Page
from app.pipeline.grounding import validate_grounding
from app.pipeline.normalizer import (
    canonical_predicate,
    canonical_subject,
    normalize_period,
    normalize_value,
)
from app.pipeline.relationships import classify_with_rules, fact_summary

ProgressCallback = Callable[[int, int], Awaitable[None]]


async def extract_document_facts(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    document_name: str,
    provider: LLMProvider,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[Fact], list[dict]]:
    await session.execute(delete(Fact).where(Fact.document_id == document_id))
    await session.flush()

    rows = (
        await session.execute(
            select(Page, Evidence)
            .join(Evidence, Evidence.page_id == Page.id)
            .where(Page.document_id == document_id)
            .order_by(Page.page_index, Evidence.created_at, Evidence.id)
        )
    ).all()
    by_page: dict[int, list[Evidence]] = defaultdict(list)
    for page, evidence in rows:
        by_page[page.page_index].append(evidence)

    page_groups = list(by_page.items())
    batch_size = settings.fact_extraction_page_batch_size
    batches = [
        page_groups[index : index + batch_size] for index in range(0, len(page_groups), batch_size)
    ]
    semaphore = asyncio.Semaphore(settings.fact_extraction_concurrency)
    completed = 0
    lock = asyncio.Lock()

    async def extract_batch(page_batch: list[tuple[int, list[Evidence]]]):
        nonlocal completed
        error: dict | None = None
        result = []
        evidence_items = [item for _, items in page_batch for item in items]
        page_indexes = [page_index for page_index, _ in page_batch]
        try:
            async with semaphore:
                result = await provider.extract_facts(
                    document_name=document_name,
                    evidence=[
                        EvidenceInput(id=str(item.id), text=item.quote, page_index=page_index)
                        for page_index, items in page_batch
                        for item in items
                    ],
                    limit=settings.facts_per_page_limit * len(page_batch),
                )
        except Exception as exc:
            error = {
                "page_indexes": page_indexes,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        finally:
            async with lock:
                completed += 1
                if progress_callback:
                    await progress_callback(completed, len(batches))
        return evidence_items, result, error

    page_results = await asyncio.gather(*(extract_batch(batch) for batch in batches))

    accepted: list[Fact] = []
    rejected: list[dict] = []
    batch_error_count = 0
    for evidence_items, candidates, page_error in page_results:
        if page_error:
            rejected.append({"page_error": page_error})
            batch_error_count += 1
            continue
        evidence_map = {str(item.id): item for item in evidence_items}
        for candidate in candidates:
            evidence = evidence_map.get(candidate.evidence_id)
            if evidence is None:
                rejected.append(
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "reasons": ["evidence_id was not supplied for this extraction batch"],
                    }
                )
                continue
            grounding = validate_grounding(candidate, evidence)
            if not grounding.accepted:
                rejected.append(
                    {
                        "candidate": candidate.model_dump(mode="json"),
                        "reasons": grounding.reasons,
                    }
                )
                continue

            normalized_value = normalize_value(candidate.value_raw, candidate.unit)
            normalized_period = normalize_period(candidate.period)
            fact = Fact(
                document_id=document_id,
                evidence_id=evidence.id,
                subject_raw=candidate.subject,
                subject_canonical=canonical_subject(candidate.subject),
                predicate_raw=candidate.predicate,
                predicate_canonical=canonical_predicate(candidate),
                value_raw=candidate.value_raw,
                value_kind=normalized_value.value_kind,
                numeric_value=normalized_value.numeric_value,
                normalized_value=normalized_value.normalized_value,
                unit_raw=candidate.unit,
                unit_canonical=normalized_value.unit_canonical,
                canonical_numeric_value=normalized_value.canonical_numeric_value,
                claim_kind=candidate.claim_kind,
                period_start=normalized_period.start,
                period_end=normalized_period.end,
                period_label=normalized_period.label,
                estimate_vintage=candidate.estimate_vintage,
                context={
                    "scope": candidate.scope,
                    "period_raw": candidate.period,
                    "supporting_quote": candidate.supporting_quote,
                },
                confidence=candidate.confidence,
                status="VALIDATED",
                extractor_version=f"gemini:{settings.gemini_model}",
                schema_version=1,
            )
            session.add(fact)
            accepted.append(fact)
    if batches and batch_error_count == len(batches):
        raise RuntimeError("Gemini fact extraction failed for every page batch")
    await session.flush()
    return accepted, rejected


async def embed_facts(
    session: AsyncSession,
    *,
    facts: list[Fact],
    provider: LLMProvider,
    batch_size: int = 90,
    items_per_minute: int = 0,
    progress_callback: ProgressCallback | None = None,
) -> int:
    embedded = 0
    window_started = time.monotonic()
    items_in_window = 0
    for offset in range(0, len(facts), batch_size):
        batch = facts[offset : offset + batch_size]
        if items_per_minute and items_in_window + len(batch) > items_per_minute:
            remaining = 60 - (time.monotonic() - window_started)
            if remaining > 0:
                await asyncio.sleep(remaining)
            window_started = time.monotonic()
            items_in_window = 0
        vectors = await provider.embed([fact_summary(fact) for fact in batch])
        if len(vectors) != len(batch):
            raise RuntimeError("Gemini returned an unexpected embedding count")
        for fact, vector in zip(batch, vectors, strict=True):
            fact.embedding = vector
            embedded += 1
        items_in_window += len(batch)
        await session.flush()
        if progress_callback:
            await progress_callback(embedded, len(facts))
    return embedded


async def build_relationships(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    project_id: uuid.UUID,
    facts: list[Fact],
    provider: LLMProvider,
    settings: Settings,
) -> tuple[list[FactRelationship], int]:
    created: list[FactRelationship] = []
    evidence_cache: dict[uuid.UUID, Evidence] = {}
    llm_calls = 0
    classification_failures = 0

    async def evidence_for(fact: Fact) -> Evidence:
        if fact.evidence_id not in evidence_cache:
            evidence = await session.get(Evidence, fact.evidence_id)
            if evidence is None:
                raise RuntimeError(f"Evidence {fact.evidence_id} is missing")
            evidence_cache[fact.evidence_id] = evidence
        return evidence_cache[fact.evidence_id]

    for fact in facts:
        if fact.embedding is None:
            continue
        distance = Fact.embedding.cosine_distance(fact.embedding).label("distance")
        candidates = (
            await session.execute(
                select(Fact, distance)
                .join(Document, Document.id == Fact.document_id)
                .where(
                    Fact.document_id != document_id,
                    Document.project_id == project_id,
                    Fact.embedding.is_not(None),
                    Fact.status == "VALIDATED",
                )
                .order_by(distance)
                .limit(settings.candidates_per_fact)
            )
        ).all()

        for other, raw_distance in candidates:
            similarity = max(0.0, 1.0 - float(raw_distance))
            same_subject = fact.subject_canonical == other.subject_canonical
            same_predicate = fact.predicate_canonical == other.predicate_canonical
            if similarity < settings.min_candidate_similarity and not (
                same_subject and same_predicate
            ):
                continue
            if not same_subject and not (same_predicate and similarity >= 0.75):
                continue

            first, second = sorted((fact, other), key=lambda item: str(item.id))
            first_id, second_id = first.id, second.id
            exists = await session.scalar(
                select(FactRelationship.id).where(
                    FactRelationship.fact_a_id == first_id,
                    FactRelationship.fact_b_id == second_id,
                )
            )
            if exists:
                continue

            rule = classify_with_rules(first, second)
            if rule:
                relation = rule.relation
                confidence = rule.confidence
                explanation = rule.explanation
                differences = rule.differences
                comparison = rule.comparison
                classifier_version = "rules-v1"
            else:
                if (
                    similarity < settings.min_llm_relationship_similarity
                    or llm_calls >= settings.max_llm_relationships_per_document
                ):
                    continue
                evidence_a = await evidence_for(first)
                evidence_b = await evidence_for(second)
                llm_calls += 1
                try:
                    llm_result = await provider.classify_relationship(
                        fact_a=fact_summary(first),
                        evidence_a=evidence_a.quote,
                        fact_b=fact_summary(second),
                        evidence_b=evidence_b.quote,
                    )
                except Exception:
                    classification_failures += 1
                    continue
                relation = llm_result.relation
                confidence = llm_result.confidence
                explanation = llm_result.explanation
                differences = [
                    {"dimension": "MODEL_IDENTIFIED", "detail": item}
                    for item in llm_result.differences
                ]
                comparison = {
                    "same_subject": same_subject,
                    "same_predicate": same_predicate,
                }
                classifier_version = f"rules-v1+gemini:{settings.gemini_model}"

            candidate_score = min(
                1.0,
                similarity + (0.1 if same_subject else 0) + (0.1 if same_predicate else 0),
            )
            relationship = FactRelationship(
                fact_a_id=first_id,
                fact_b_id=second_id,
                relation=relation,
                confidence=confidence,
                comparison=comparison,
                differences=differences,
                explanation=explanation,
                candidate_score=candidate_score,
                classifier_version=classifier_version,
                status="VALIDATED",
            )
            session.add(relationship)
            created.append(relationship)
    await session.flush()
    return created, classification_failures
