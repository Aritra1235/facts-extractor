import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.enums import DocumentStatus, EventLevel, JobStage, JobStatus
from app.db import SessionLocal
from app.llm.base import LLMProvider
from app.llm.factory import create_provider
from app.models import (
    Document,
    Evidence,
    Fact,
    Page,
    PageElement,
    ProcessingEvent,
    ProcessingJob,
)
from app.pipeline.knowledge import build_relationships, embed_facts, extract_document_facts
from app.pipeline.parser import PdfParser

settings = get_settings()


async def add_event(
    job_id: uuid.UUID,
    stage: JobStage,
    message: str,
    progress: float | None = None,
    level: EventLevel = EventLevel.INFO,
    details: dict | None = None,
) -> None:
    async with SessionLocal() as session:
        session.add(
            ProcessingEvent(
                job_id=job_id,
                stage=stage,
                level=level,
                message=message,
                progress=progress,
                details=details or {},
            )
        )
        await session.commit()


async def update_job(job_id: uuid.UUID, **values: object) -> None:
    async with SessionLocal() as session:
        job = await session.get(ProcessingJob, job_id)
        if job is None:
            raise RuntimeError(f"Job {job_id} disappeared")
        for key, value in values.items():
            setattr(job, key, value)
        await session.commit()


async def process_job(job_id: uuid.UUID) -> None:
    provider: LLMProvider | None = None
    async with SessionLocal() as session:
        job = await session.get(ProcessingJob, job_id)
        if job is None:
            return
        document = await session.get(Document, job.document_id)
        if document is None:
            return
        document.status = DocumentStatus.PROCESSING
        await session.commit()
        document_id = document.id
        project_id = document.project_id
        storage_path = Path(document.storage_path)
        resume_page = job.current_page or 0
        resume_checkpoint = (job.result or {}).get("checkpoint")

    try:
        parser = PdfParser(storage_path)
        total_pages = await asyncio.to_thread(parser.page_count)
        await update_job(
            job_id,
            stage=JobStage.PARSING,
            total_pages=total_pages,
            current_page=0,
            progress=0.02,
        )
        await add_event(job_id, JobStage.PARSING, f"Parsing {total_pages} PDF pages", 0.02)

        start_page = min(resume_page, total_pages) if job.attempt_count > 1 else 0
        if start_page:
            await add_event(
                job_id,
                JobStage.PARSING,
                f"Resuming from PDF page {start_page + 1}",
                0.02 + 0.58 * (start_page / total_pages),
                details={"resume_page_index": start_page},
            )

        for page_index in range(start_page, total_pages):
            parsed = await asyncio.to_thread(parser.parse_page, page_index)
            async with SessionLocal() as session:
                existing = await session.scalar(
                    select(Page).where(
                        Page.document_id == document_id,
                        Page.page_index == page_index,
                    )
                )
                rebuild_elements = existing is None
                if existing and (
                    existing.content_hash != parsed.content_hash
                    or existing.parser_version != settings.parser_version
                ):
                    rebuild_elements = True
                    await session.execute(
                        delete(PageElement).where(PageElement.page_id == existing.id)
                    )
                    await session.execute(delete(Evidence).where(Evidence.page_id == existing.id))
                    existing.width = parsed.width
                    existing.height = parsed.height
                    existing.text = parsed.text
                    existing.content_hash = parsed.content_hash
                    existing.parser_version = settings.parser_version
                    existing.printed_page_label = parsed.printed_page_label
                    page_record = existing
                elif existing:
                    page_record = existing
                else:
                    page_record = Page(
                        document_id=document_id,
                        page_index=page_index,
                        printed_page_label=parsed.printed_page_label,
                        width=parsed.width,
                        height=parsed.height,
                        text=parsed.text,
                        content_hash=parsed.content_hash,
                        parser_version=settings.parser_version,
                    )
                    session.add(page_record)
                    await session.flush()

                if rebuild_elements:
                    session.add_all(
                        PageElement(
                            page_id=page_record.id,
                            element_type=element.element_type,
                            text=element.text,
                            bbox=element.bbox,
                            reading_order=element.reading_order,
                            extraction_method=element.extraction_method,
                            confidence=element.confidence,
                            attributes={},
                        )
                        for element in parsed.elements
                    )
                await session.commit()

            progress = 0.02 + 0.58 * ((page_index + 1) / total_pages)
            await update_job(
                job_id,
                current_page=page_index + 1,
                progress=progress,
                leased_until=datetime.now(UTC) + timedelta(seconds=settings.worker_lease_seconds),
            )

        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            document.page_count = total_pages
            document.parser_version = settings.parser_version
            await session.commit()

        await update_job(job_id, stage=JobStage.BUILDING_EVIDENCE, progress=0.62)
        await add_event(
            job_id,
            JobStage.BUILDING_EVIDENCE,
            "Building evidence regions from page blocks",
            0.62,
        )

        async with SessionLocal() as session:
            pages = list(
                (
                    await session.scalars(
                        select(Page)
                        .where(Page.document_id == document_id)
                        .order_by(Page.page_index)
                    )
                ).all()
            )
            evidence_count = 0
            for page in pages:
                elements = list(
                    (
                        await session.scalars(
                            select(PageElement)
                            .where(PageElement.page_id == page.id)
                            .order_by(PageElement.reading_order)
                        )
                    ).all()
                )
                existing_count = await session.scalar(
                    select(func.count(Evidence.id)).where(Evidence.page_id == page.id)
                )
                if not existing_count:
                    for element in elements:
                        if len(element.text) < 20:
                            continue
                        session.add(
                            Evidence(
                                document_id=document_id,
                                page_id=page.id,
                                quote=element.text,
                                element_ids=[str(element.id)],
                                bboxes=[element.bbox],
                                attributes={"builder": "block-v1"},
                            )
                        )
                        evidence_count += 1
                else:
                    evidence_count += existing_count
            await session.commit()

        provider = create_provider(settings)
        if resume_checkpoint in {"FACTS_EXTRACTED", "FACTS_EMBEDDED"}:
            async with SessionLocal() as session:
                facts = list(
                    (
                        await session.scalars(select(Fact).where(Fact.document_id == document_id))
                    ).all()
                )
            rejected = []
            await update_job(job_id, stage=JobStage.EXTRACTING_FACTS, progress=0.80)
            await add_event(
                job_id,
                JobStage.EXTRACTING_FACTS,
                f"Reusing {len(facts)} facts from the durable extraction checkpoint",
                0.80,
            )
        else:
            await update_job(job_id, stage=JobStage.EXTRACTING_FACTS, progress=0.64)
            await add_event(
                job_id,
                JobStage.EXTRACTING_FACTS,
                f"Extracting facts with {settings.openrouter_text_model} via OpenRouter",
                0.64,
            )

            async def extraction_progress(done: int, total: int) -> None:
                progress = 0.64 + 0.16 * (done / max(total, 1))
                await update_job(
                    job_id,
                    progress=progress,
                    leased_until=datetime.now(UTC)
                    + timedelta(seconds=settings.worker_lease_seconds),
                )

            async with SessionLocal() as session:
                facts, rejected = await extract_document_facts(
                    session,
                    document_id=document_id,
                    document_name=document.filename,
                    provider=provider,
                    settings=settings,
                    progress_callback=extraction_progress,
                )
                await session.commit()
            await update_job(
                job_id,
                result={
                    "checkpoint": "FACTS_EXTRACTED",
                    "facts": len(facts),
                    "rejected_fact_candidates": len(rejected),
                },
            )

        await update_job(job_id, stage=JobStage.NORMALIZING, progress=0.82)
        await add_event(
            job_id,
            JobStage.NORMALIZING,
            f"Accepted {len(facts)} grounded facts; rejected {len(rejected)} candidates",
            0.82,
            level=EventLevel.WARNING if rejected else EventLevel.INFO,
            details={"rejected_count": len(rejected), "samples": rejected[:10]},
        )

        await update_job(job_id, stage=JobStage.INDEXING, progress=0.85)
        await add_event(
            job_id,
            JobStage.INDEXING,
            f"Embedding {len(facts)} facts with "
            f"{settings.openrouter_embedding_model} via OpenRouter",
            0.85,
        )

        async def embedding_progress(done: int, total: int) -> None:
            progress = 0.85 + 0.06 * (done / max(total, 1))
            await update_job(
                job_id,
                progress=progress,
                leased_until=datetime.now(UTC) + timedelta(seconds=settings.worker_lease_seconds),
            )

        if resume_checkpoint == "FACTS_EMBEDDED":
            embedded_count = len(facts)
            await add_event(
                job_id,
                JobStage.INDEXING,
                f"Reusing {embedded_count} embeddings from the durable checkpoint",
                0.91,
            )
        else:
            async with SessionLocal() as session:
                persisted_facts = list(
                    (
                        await session.scalars(
                            select(Fact)
                            .where(Fact.document_id == document_id)
                            .order_by(Fact.created_at, Fact.id)
                        )
                    ).all()
                )
                embedded_count = await embed_facts(
                    session,
                    facts=persisted_facts,
                    provider=provider,
                    batch_size=settings.embedding_batch_size,
                    items_per_minute=settings.embedding_items_per_minute,
                    progress_callback=embedding_progress,
                )
                await session.commit()
            await update_job(
                job_id,
                result={
                    "checkpoint": "FACTS_EMBEDDED",
                    "facts": len(facts),
                    "rejected_fact_candidates": len(rejected),
                    "embedded_facts": embedded_count,
                },
            )

        await update_job(job_id, stage=JobStage.COMPARING, progress=0.92)
        await add_event(
            job_id,
            JobStage.COMPARING,
            "Retrieving comparable facts from pgvector and classifying relationships",
            0.92,
        )
        async with SessionLocal() as session:
            persisted_facts = list(
                (
                    await session.scalars(
                        select(Fact)
                        .where(Fact.document_id == document_id)
                        .order_by(Fact.created_at, Fact.id)
                    )
                ).all()
            )
            relationships, relationship_failures = await build_relationships(
                session,
                document_id=document_id,
                project_id=project_id,
                facts=persisted_facts,
                provider=provider,
                settings=settings,
            )
            await session.commit()

        completed_at = datetime.now(UTC)
        result = {
            "pages": total_pages,
            "evidence_regions": evidence_count,
            "facts": len(facts),
            "rejected_fact_candidates": len(rejected),
            "embedded_facts": embedded_count,
            "relationships": len(relationships),
            "relationship_classification_failures": relationship_failures,
            "pipeline_version": "knowledge-v1",
        }
        await update_job(
            job_id,
            status=JobStatus.COMPLETE,
            stage=JobStage.COMPLETE,
            progress=1.0,
            completed_at=completed_at,
            leased_until=None,
            result=result,
        )
        async with SessionLocal() as session:
            document = await session.get(Document, document_id)
            document.status = DocumentStatus.COMPLETE
            await session.commit()
        await add_event(
            job_id, JobStage.COMPLETE, "Document ingestion complete", 1.0, details=result
        )
    except Exception as exc:
        await update_job(
            job_id,
            status=JobStatus.FAILED,
            stage=JobStage.FAILED,
            error_code=type(exc).__name__,
            error_message=str(exc),
            completed_at=datetime.now(UTC),
            leased_until=None,
        )
        async with SessionLocal() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is not None:
                document = await session.get(Document, job.document_id)
                if document is not None:
                    document.status = DocumentStatus.FAILED
                    await session.commit()
        await add_event(
            job_id,
            JobStage.FAILED,
            "Document ingestion failed",
            level=EventLevel.ERROR,
            details={"error_type": type(exc).__name__, "error": str(exc)},
        )
    finally:
        if provider is not None:
            try:
                await provider.close()
            except Exception:
                pass
