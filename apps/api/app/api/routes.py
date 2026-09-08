import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.enums import JobStage, JobStatus
from app.db import get_session
from app.models import (
    Document,
    Evidence,
    Fact,
    FactRelationship,
    Page,
    PageElement,
    ProcessingJob,
    Project,
)
from app.schemas import (
    DocumentResponse,
    ElementResponse,
    EvidenceResponse,
    FactResponse,
    JobDetailResponse,
    JobResponse,
    PageResponse,
    PageSummaryResponse,
    ProjectCreate,
    ProjectResponse,
    RelationshipResponse,
    UploadResponse,
)

router = APIRouter()
settings = get_settings()


async def _project_or_404(session: AsyncSession, project_id: uuid.UUID) -> Project:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


async def _project_response(session: AsyncSession, project: Project) -> ProjectResponse:
    document_ids = select(Document.id).where(Document.project_id == project.id)
    fact_ids = select(Fact.id).where(Fact.document_id.in_(document_ids))
    document_count = await session.scalar(
        select(func.count(Document.id)).where(Document.project_id == project.id)
    )
    completed_document_count = await session.scalar(
        select(func.count(Document.id)).where(
            Document.project_id == project.id, Document.status == "COMPLETE"
        )
    )
    fact_count = await session.scalar(select(func.count(Fact.id)).where(Fact.id.in_(fact_ids)))
    relationship_count = await session.scalar(
        select(func.count(FactRelationship.id)).where(
            FactRelationship.fact_a_id.in_(fact_ids),
            FactRelationship.fact_b_id.in_(fact_ids),
        )
    )
    return ProjectResponse(
        id=project.id,
        name=project.name,
        slug=project.slug,
        description=project.description,
        document_count=document_count or 0,
        completed_document_count=completed_document_count or 0,
        fact_count=fact_count or 0,
        relationship_count=relationship_count or 0,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def _upload_to_project(
    *, file: UploadFile, project: Project, session: AsyncSession
) -> UploadResponse:
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF uploads are supported")

    sha256, size_bytes, storage_path = await _persist_upload(file)
    existing = await session.scalar(
        select(Document).where(
            Document.project_id == project.id,
            Document.sha256 == sha256,
        )
    )
    if existing:
        job = await session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == existing.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        if job is None:
            job = ProcessingJob(document_id=existing.id)
            session.add(job)
            await session.commit()
            await session.refresh(job)
        return UploadResponse(document=existing, job=job, duplicate=True)

    document = Document(
        project_id=project.id,
        sha256=sha256,
        filename=filename,
        content_type="application/pdf",
        size_bytes=size_bytes,
        storage_path=str(storage_path.resolve()),
    )
    session.add(document)
    await session.flush()
    job = ProcessingJob(document_id=document.id)
    session.add(job)
    await session.commit()
    await session.refresh(document)
    await session.refresh(job)
    return UploadResponse(document=document, job=job, duplicate=False)


async def _persist_upload(upload: UploadFile) -> tuple[str, int, Path]:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = settings.upload_dir / f"upload-{uuid.uuid4()}.tmp"
    digest = hashlib.sha256()
    size = 0

    try:
        async with aiofiles.open(temporary_path, "wb") as output:
            first_chunk = True
            while chunk := await upload.read(1024 * 1024):
                if first_chunk and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(status_code=415, detail="File is not a valid PDF")
                first_chunk = False
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"PDF exceeds {settings.max_upload_bytes} bytes",
                    )
                digest.update(chunk)
                await output.write(chunk)

        if first_chunk:
            raise HTTPException(status_code=415, detail="Uploaded PDF is empty")

        sha256 = digest.hexdigest()
        final_path = settings.upload_dir / f"{sha256}.pdf"
        if not final_path.exists():
            os.replace(temporary_path, final_path)
        else:
            temporary_path.unlink(missing_ok=True)
        return sha256, size, final_path
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ProjectResponse]:
    projects = list(
        (
            await session.scalars(select(Project).order_by(Project.created_at, Project.name))
        ).all()
    )
    return [await _project_response(session, project) for project in projects]


@router.post("/projects", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectResponse:
    name = " ".join(payload.name.split())
    base_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    slug = base_slug
    suffix = 2
    while await session.scalar(select(Project.id).where(Project.slug == slug)):
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    project = Project(name=name, slug=slug, description=payload.description)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return await _project_response(session, project)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectResponse:
    return await _project_response(session, await _project_or_404(session, project_id))


@router.get("/projects/{project_id}/documents", response_model=list[DocumentResponse])
async def list_project_documents(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[Document]:
    await _project_or_404(session, project_id)
    return list(
        (
            await session.scalars(
                select(Document)
                .where(Document.project_id == project_id)
                .order_by(Document.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )


@router.post(
    "/projects/{project_id}/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_project_document(
    project_id: uuid.UUID,
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadResponse:
    project = await _project_or_404(session, project_id)
    return await _upload_to_project(file=file, project=project, session=session)


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
    project_id: uuid.UUID | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[Document]:
    statement = select(Document)
    if project_id:
        await _project_or_404(session, project_id)
        statement = statement.where(Document.project_id == project_id)
    return list(
        (
            await session.scalars(
                statement.order_by(Document.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )


@router.post(
    "/documents",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadResponse:
    project = await session.scalar(select(Project).order_by(Project.created_at).limit(1))
    if project is None:
        raise HTTPException(status_code=409, detail="Create a project before uploading documents")
    return await _upload_to_project(file=file, project=project, session=session)


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents/{document_id}/file", response_class=FileResponse)
async def get_document_file(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> FileResponse:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        document.storage_path, media_type="application/pdf", filename=document.filename
    )


@router.get("/documents/{document_id}/pages", response_model=list[PageSummaryResponse])
async def list_pages(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[Page]:
    return list(
        (
            await session.scalars(
                select(Page).where(Page.document_id == document_id).order_by(Page.page_index)
            )
        ).all()
    )


@router.get("/pages/{page_id}", response_model=PageResponse)
async def get_page(
    page_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Page:
    page = await session.get(Page, page_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found")
    return page


@router.get("/pages/{page_id}/elements", response_model=list[ElementResponse])
async def list_page_elements(
    page_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[PageElement]:
    return list(
        (
            await session.scalars(
                select(PageElement)
                .where(PageElement.page_id == page_id)
                .order_by(PageElement.reading_order)
            )
        ).all()
    )


@router.get("/documents/{document_id}/evidence", response_model=list[EvidenceResponse])
async def list_evidence(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[Evidence]:
    return list(
        (
            await session.scalars(
                select(Evidence)
                .where(Evidence.document_id == document_id)
                .order_by(Evidence.created_at, Evidence.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence(
    evidence_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Evidence:
    evidence = await session.get(Evidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return evidence


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job(
    job_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> ProcessingJob:
    job = await session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .options(selectinload(ProcessingJob.events))
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/documents/{document_id}/jobs", response_model=list[JobResponse])
async def list_document_jobs(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> list[ProcessingJob]:
    return list(
        (
            await session.scalars(
                select(ProcessingJob)
                .where(ProcessingJob.document_id == document_id)
                .order_by(ProcessingJob.created_at.desc())
            )
        ).all()
    )


@router.post(
    "/documents/{document_id}/process",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_document(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> ProcessingJob:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    active = await session.scalar(
        select(ProcessingJob.id).where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
        )
    )
    if active:
        raise HTTPException(status_code=409, detail="Document already has an active job")
    resumable = await session.scalar(
        select(ProcessingJob)
        .where(
            ProcessingJob.document_id == document_id,
            ProcessingJob.status == JobStatus.FAILED,
        )
        .order_by(ProcessingJob.created_at.desc())
    )
    if resumable and (resumable.result or {}).get("checkpoint"):
        resumable.status = JobStatus.QUEUED
        resumable.stage = JobStage.QUEUED
        resumable.error_code = None
        resumable.error_message = None
        resumable.worker_id = None
        resumable.leased_until = None
        resumable.completed_at = None
        await session.commit()
        await session.refresh(resumable)
        return resumable
    job = ProcessingJob(document_id=document_id)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@router.get("/documents/{document_id}/facts", response_model=list[FactResponse])
async def list_facts(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[Fact]:
    return list(
        (
            await session.scalars(
                select(Fact)
                .where(Fact.document_id == document_id)
                .order_by(Fact.created_at, Fact.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )


@router.get("/projects/{project_id}/facts", response_model=list[FactResponse])
async def list_project_facts(
    project_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[Fact]:
    await _project_or_404(session, project_id)
    document_ids = select(Document.id).where(Document.project_id == project_id)
    return list(
        (
            await session.scalars(
                select(Fact)
                .where(Fact.document_id.in_(document_ids))
                .order_by(Fact.created_at.desc(), Fact.id)
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )


@router.get("/facts/{fact_id}", response_model=FactResponse)
async def get_fact(
    fact_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_session)]
) -> Fact:
    fact = await session.get(Fact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")
    return fact


@router.get("/relationships", response_model=list[RelationshipResponse])
async def list_relationships(
    session: Annotated[AsyncSession, Depends(get_session)],
    document_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    relation: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=250)] = 100,
) -> list[FactRelationship]:
    statement = select(FactRelationship)
    if project_id:
        await _project_or_404(session, project_id)
        project_document_ids = select(Document.id).where(Document.project_id == project_id)
        project_fact_ids = select(Fact.id).where(Fact.document_id.in_(project_document_ids))
        statement = statement.where(
            FactRelationship.fact_a_id.in_(project_fact_ids),
            FactRelationship.fact_b_id.in_(project_fact_ids),
        )
    if document_id:
        fact_ids = select(Fact.id).where(Fact.document_id == document_id)
        statement = statement.where(
            or_(
                FactRelationship.fact_a_id.in_(fact_ids),
                FactRelationship.fact_b_id.in_(fact_ids),
            )
        )
    if relation:
        statement = statement.where(FactRelationship.relation == relation.upper())
    return list(
        (
            await session.scalars(
                statement.order_by(FactRelationship.created_at.desc()).offset(offset).limit(limit)
            )
        ).all()
    )
