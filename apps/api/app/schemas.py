import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    document_count: int = 0
    completed_document_count: int = 0
    fact_count: int = 0
    relationship_count: int = 0
    created_at: datetime
    updated_at: datetime


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    stage: str
    level: str
    message: str
    progress: float | None
    details: dict
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    status: str
    stage: str
    progress: float = Field(ge=0, le=1)
    current_page: int | None
    total_pages: int | None
    attempt_count: int
    error_code: str | None
    error_message: str | None
    result: dict
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobDetailResponse(JobResponse):
    events: list[EventResponse]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    sha256: str
    filename: str
    content_type: str
    size_bytes: int
    title: str | None
    page_count: int | None
    status: str
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    document: DocumentResponse
    job: JobResponse
    duplicate: bool


class PageSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_index: int
    printed_page_label: str | None
    width: float
    height: float


class PageResponse(PageSummaryResponse):
    text: str


class ElementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_id: uuid.UUID
    element_type: str
    text: str
    bbox: list[float]
    reading_order: int
    extraction_method: str
    confidence: float
    attributes: dict


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    page_id: uuid.UUID
    quote: str
    element_ids: list[str]
    bboxes: list[list[float]]
    section: str | None
    table_title: str | None
    row_label: str | None
    column_label: str | None
    footnotes: list[str]
    attributes: dict


class FactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    evidence_id: uuid.UUID
    subject_raw: str
    subject_canonical: str
    predicate_raw: str
    predicate_canonical: str
    value_raw: str
    value_kind: str
    numeric_value: float | None
    normalized_value: str | None
    unit_raw: str | None
    unit_canonical: str | None
    canonical_numeric_value: float | None
    claim_kind: str
    period_start: datetime | None
    period_end: datetime | None
    period_label: str | None
    estimate_vintage: str | None
    context: dict
    confidence: float
    status: str


class RelationshipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fact_a_id: uuid.UUID
    fact_b_id: uuid.UUID
    relation: str
    confidence: float
    comparison: dict
    differences: list[dict]
    explanation: str
    candidate_score: float
    classifier_version: str
    status: str
