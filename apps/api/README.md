# Fact Knowledge Layer

Evidence-first PDF ingestion backend for the Superjoin engineering assignment.

The backend is an auditable asynchronous knowledge pipeline:

1. Create or select an isolated knowledge project.
2. Accept a PDF upload and hash it for project-local deduplication.
3. Create a durable PostgreSQL processing job.
4. Let a separate worker claim jobs with `FOR UPDATE SKIP LOCKED`.
5. Parse every page with PyMuPDF and persist normalized bounding boxes.
6. Build evidence regions from physical page blocks.
7. Extract typed facts through OpenRouter structured output.
8. Reject facts that are not deterministically grounded in their evidence.
9. Normalize values, units, fiscal periods, subjects, and predicates.
10. Embed facts through OpenRouter and retrieve candidates from the same project through pgvector.
11. Classify relationships with deterministic rules first and OpenRouter for ambiguous pairs.
12. Expose job progress and an event trace for frontend polling.

PostgreSQL is the source of truth. The `facts.embedding` pgvector column is reserved for
candidate retrieval; vectors do not determine fact truth or relationship labels.

The extraction contract is provider-independent (`LLMProvider`). OpenRouter is the configured
implementation. The text model, embedding model, and vector dimensions are supplied through the
environment rather than compiled into the application.

## Run

From the repository root, copy `apps/api/.env.example` to `.env`, set `OPENROUTER_API_KEY`,
`OPENROUTER_TEXT_MODEL`, and `OPENROUTER_EMBEDDING_MODEL`, then run `docker compose up --build`.
The text model must support strict JSON-schema responses. The embedding model must support the
configured `EMBEDDING_DIMENSIONS`, because PostgreSQL's vector column has that fixed width.

Open the API documentation at <http://localhost:8001/docs>.
PostgreSQL is exposed on host port `5433` to avoid colliding with a typical local installation.

List projects, then upload a document into one project:

```bash
curl http://localhost:8001/api/v1/projects

curl -F 'file=@../starter-datasets/delhivery/03-delhivery-q4-fy24-earnings-presentation.pdf' \
  http://localhost:8001/api/v1/projects/PROJECT_ID/documents
```

The response contains both a `document.id` and `job.id`. Poll:

```bash
curl http://localhost:8001/api/v1/jobs/JOB_ID
```

The job moves through:

```text
QUEUED → PARSING → BUILDING_EVIDENCE → EXTRACTING_FACTS →
NORMALIZING → INDEXING → COMPARING → COMPLETE
```

If required OpenRouter configuration is missing, document parsing remains persisted and the job
fails explicitly at `EXTRACTING_FACTS`; it can then be restarted through
`POST /documents/{id}/process`.

Useful result endpoints:

```text
GET /api/v1/projects
POST /api/v1/projects
GET /api/v1/projects/{project_id}/documents
GET /api/v1/documents/{document_id}/facts
GET /api/v1/evidence/{evidence_id}
GET /api/v1/relationships?project_id={project_id}&relation=CORROBORATES
```

## Polling contract

`GET /api/v1/jobs/{job_id}` returns:

- `status`: lifecycle (`QUEUED`, `RUNNING`, `COMPLETE`, `FAILED`)
- `stage`: current pipeline stage
- `progress`: number from `0` to `1`
- `current_page` and `total_pages`
- structured failure fields
- final result counts
- append-only processing events

Workers renew a lease while processing pages. An abandoned `RUNNING` job becomes claimable after
its lease expires. Successful extraction and embedding stages write durable checkpoints. Retrying a
failed job resumes from the latest checkpoint instead of spending model quota on completed work.

Extraction groups several PDF pages into each model request. Embeddings are paced by
`EMBEDDING_ITEMS_PER_MINUTE` (90 by default); set it to `0` when the selected OpenRouter model and
account can accept unpaced batches. Ambiguous relationship adjudication has both a similarity
threshold and a per-document call cap.

Page list responses contain metadata only. Full text, positioned elements, and evidence are fetched
from per-page and paginated evidence endpoints so large documents do not create oversized responses.

## Development

```bash
cd apps/api
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
```
