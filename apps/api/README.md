# Fact Knowledge Layer

Evidence-first PDF ingestion backend for the Superjoin engineering assignment.

The backend is an auditable asynchronous knowledge pipeline:

1. Create or select an isolated knowledge project.
2. Accept a PDF upload and hash it for project-local deduplication.
3. Create a durable PostgreSQL processing job.
4. Let a separate worker claim jobs with `FOR UPDATE SKIP LOCKED`.
5. Parse every page with PyMuPDF and persist normalized bounding boxes.
6. Build evidence regions from physical page blocks.
7. Extract typed facts with Gemini structured output.
8. Reject facts that are not deterministically grounded in their evidence.
9. Normalize values, units, fiscal periods, subjects, and predicates.
10. Embed facts with Gemini and retrieve candidates from the same project through pgvector.
11. Classify relationships with deterministic rules first and Gemini for ambiguous pairs.
12. Expose job progress and an event trace for frontend polling.

PostgreSQL is the source of truth. The `facts.embedding` pgvector column is reserved for
candidate retrieval; vectors do not determine fact truth or relationship labels.

The extraction contract is provider-independent (`LLMProvider`). Gemini is the configured
implementation and uses `gemini-3.5-flash-lite` for typed JSON extraction and
`gemini-embedding-001` for 384-dimensional semantic-similarity vectors.

## Run

From the repository root, copy `apps/api/.env.example` to `.env`, set `GEMINI_API_KEY`, then run
`docker compose up --build`.

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

If `GEMINI_API_KEY` is missing, document parsing remains persisted and the job fails explicitly at
`EXTRACTING_FACTS`; it can then be restarted through `POST /documents/{id}/process`.

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
failed job resumes from the latest checkpoint instead of spending Gemini quota on completed work.

Extraction groups several PDF pages into each model request. Embeddings are paced by
`EMBEDDING_ITEMS_PER_MINUTE` (90 by default) so the starter configuration also works with Gemini
free-tier rate limits; set it to `0` to disable pacing on a higher-quota project. Ambiguous
relationship adjudication has both a similarity threshold and a per-document call cap.

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
