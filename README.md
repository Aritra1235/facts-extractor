# Fact Knowledge Layer

An evidence-first backend that turns PDFs into auditable facts and cross-document
relationships. This is intentionally a small fact compiler rather than a generic RAG chatbot:

```text
project -> PDFs -> page elements -> evidence -> grounded facts -> normalization
        -> project-scoped pgvector candidates -> rules-first relationships -> explanations
```

The backend lives in [`apps/api`](apps/api) and the reviewer workspace lives in
[`apps/web`](apps/web). The stack uses FastAPI, Next.js, shadcn components, PostgreSQL + pgvector,
PyMuPDF, Pydantic, and the Gemini API.

## Run

```bash
cp apps/api/.env.example .env
# Set GEMINI_API_KEY in .env
docker compose up --build
```

API docs: <http://localhost:8001/docs>

Reviewer workspace: <http://localhost:3000>

```bash
curl http://localhost:8001/api/v1/projects

curl -F 'file=@/absolute/path/document.pdf' \
  http://localhost:8001/api/v1/projects/PROJECT_ID/documents

curl http://localhost:8001/api/v1/jobs/JOB_ID
```

See [`apps/api/README.md`](apps/api/README.md) for the polling contract, endpoints, and local
development commands.

## Engineering decisions

- PostgreSQL records are the knowledge layer. Embeddings only retrieve possible comparison
  candidates; they do not determine truth.
- Projects are independent knowledge layers. Documents deduplicate within a project, and candidate
  retrieval never compares a project against another project's facts.
- Evidence stores source page, exact quote, source element IDs, and normalized bounding boxes.
- Facts retain raw and canonical subject, predicate, value, unit, period, scope, claim kind, and
  estimate vintage.
- Gemini structured output is behind a provider protocol. Deterministic validation rejects facts
  whose evidence ID, quote, or raw value cannot be verified locally.
- Unit conversion and Indian fiscal-period parsing happen in deterministic code.
- Relationship rules handle comparable values, rounding, period differences, reporting scope,
  and estimate vintage before a capped Gemini fallback is allowed.
- Uploading creates a PostgreSQL job. A separate worker claims jobs with `SKIP LOCKED`, renews a
  lease, writes progress events, and saves extraction/embedding checkpoints for safe retries.

## Brownie-point support

- **Large PDFs:** page-at-a-time parsing, paginated result APIs, multi-page Gemini batches, and
  rate-aware embedding batches.
- **Many PDFs:** durable relational storage and an HNSW cosine index over fact embeddings.
- **Evolving schema:** flexible JSONB context/differences plus versioned fact and extractor
  schemas; unseen predicates remain data rather than requiring database migrations.
- **Incremental documents:** SHA-256 deduplication and comparison of each new document against
  already indexed facts without rebuilding the existing knowledge layer.

## Starter-dataset evaluation plan

The UI exposes an **Assignment case coverage** panel in every project. It reports whether the
current pipeline output contains each of the four required demonstrations and opens the evidence
review for a found case.

The supplied PDFs contain strong, non-hard-coded targets for validating the system:

- **Corroboration:** Delhivery's FY24 annual report gives consolidated revenue from operations of
  ₹81,415.38 million, while the earnings presentation reports FY24 revenue from services of
  ₹8,142 crore. After unit normalization and noting that FY24 traded-goods revenue is nil, the
  figures agree within rounding. RBI and IMF also both report FY2024/25 average CPI inflation of
  4.6 per cent.
- **Likely contradiction:** RBI projects FY2025/26 real GDP growth at 6.5 per cent while the later
  IMF report projects 6.6 per cent. These are comparable but competing forecasts, not conflicting
  historical observations; the relationship explanation preserves that distinction.
- **Contextual reconciliation:** the Economic Survey's first advance estimate puts FY2024/25 real
  GDP growth at 6.4 per cent, while RBI and IMF later report 6.5 per cent. Estimate vintage explains
  the apparent mismatch.
- **Failure case:** the Delhivery Q4 FY24 presentation's cross-border chart labels its final bar
  `Q3 FY24` even though the page and sequence indicate Q4 FY24. Native text extraction can faithfully
  extract the wrong printed label; resolving it requires layout/sequence checks or a visual model.

These examples are research targets and demo checks, not filename-specific extraction rules. New
projects and unseen PDFs use the same schema, grounding validator, normalizer, retrieval, and
classifier pipeline.

## Current trade-offs and limitations

- Native PDF text is supported; OCR, table reconstruction, and chart vision are future parser
  adapters.
- Entity and predicate canonicalization is deliberately conservative. A production version should
  add a reviewed alias/ontology table.
- API/worker startup currently applies additive SQLAlchemy schema creation. Alembic migrations are
  the next step before production deployment.
- Free-tier Gemini quotas are handled by batching, pacing, retry checkpoints, and capped fallback
  calls, at the cost of longer processing time.

## Verification

The backend test suite covers parsing, exact grounding, unit/fiscal-period normalization, and
rules-first relationships. A real 27-page Delhivery presentation run completed with 270 evidence
regions, 119 grounded facts, and 119 pgvector embeddings. A second source-page run produced
cross-document corroboration relationships, including the rounded FY24 revenue comparison.
