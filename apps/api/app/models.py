import uuid
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.core.enums import DocumentStatus, JobStage, JobStatus


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="project")


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("project_id", "sha256", name="uq_documents_project_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.UPLOADED)
    parser_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    project: Mapped[Project] = relationship(back_populates="documents")
    jobs: Mapped[list["ProcessingJob"]] = relationship(back_populates="document")
    pages: Mapped[list["Page"]] = relationship(back_populates="document")


class ProcessingJob(TimestampMixin, Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    job_type: Mapped[str] = mapped_column(String(64), default="DOCUMENT_INGESTION")
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED, index=True)
    stage: Mapped[str] = mapped_column(String(64), default=JobStage.QUEUED)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)

    document: Mapped[Document] = relationship(back_populates="jobs")
    events: Mapped[list["ProcessingEvent"]] = relationship(
        back_populates="job", order_by="ProcessingEvent.created_at"
    )


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[str] = mapped_column(String(64))
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    message: Mapped[str] = mapped_column(Text)
    progress: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[ProcessingJob] = relationship(back_populates="events")


class Page(TimestampMixin, Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("document_id", "page_index"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_index: Mapped[int] = mapped_column(Integer)
    printed_page_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[float] = mapped_column(Float)
    height: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(64))

    document: Mapped[Document] = relationship(back_populates="pages")
    elements: Mapped[list["PageElement"]] = relationship(back_populates="page")


class PageElement(Base):
    __tablename__ = "page_elements"
    __table_args__ = (UniqueConstraint("page_id", "reading_order"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    element_type: Mapped[str] = mapped_column(String(32), default="TEXT")
    text: Mapped[str] = mapped_column(Text)
    bbox: Mapped[list[float]] = mapped_column(JSONB)
    reading_order: Mapped[int] = mapped_column(Integer)
    extraction_method: Mapped[str] = mapped_column(String(32), default="NATIVE_TEXT")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)

    page: Mapped[Page] = relationship(back_populates="elements")


class Evidence(TimestampMixin, Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"))
    quote: Mapped[str] = mapped_column(Text)
    element_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    bboxes: Mapped[list[list[float]]] = mapped_column(JSONB, default=list)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    table_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    column_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    footnotes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    attributes: Mapped[dict] = mapped_column(JSONB, default=dict)


class Fact(TimestampMixin, Base):
    __tablename__ = "facts"
    __table_args__ = (
        Index("ix_facts_subject_predicate", "subject_canonical", "predicate_canonical"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence.id", ondelete="CASCADE"), index=True
    )
    subject_raw: Mapped[str] = mapped_column(Text)
    subject_canonical: Mapped[str] = mapped_column(Text, index=True)
    predicate_raw: Mapped[str] = mapped_column(Text)
    predicate_canonical: Mapped[str] = mapped_column(Text, index=True)
    value_raw: Mapped[str] = mapped_column(Text)
    value_kind: Mapped[str] = mapped_column(String(32))
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_canonical: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    claim_kind: Mapped[str] = mapped_column(String(32), default="OBSERVATION")
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    estimate_vintage: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[dict] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED")
    extractor_version: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dimensions), nullable=True
    )


class FactRelationship(TimestampMixin, Base):
    __tablename__ = "fact_relationships"
    __table_args__ = (UniqueConstraint("fact_a_id", "fact_b_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fact_a_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))
    fact_b_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"))
    relation: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[float] = mapped_column(Float)
    comparison: Mapped[dict] = mapped_column(JSONB, default=dict)
    differences: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    explanation: Mapped[str] = mapped_column(Text)
    candidate_score: Mapped[float] = mapped_column(Float)
    classifier_version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED")
