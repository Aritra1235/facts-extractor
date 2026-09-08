# Fact Knowledge Reviewer Workspace

The Next.js interface for reviewing the evidence-first PDF pipeline. It connects to the FastAPI
service through a same-origin `/api/*` rewrite, so browser requests do not need separate CORS
configuration.

## Run locally

Start the API, worker, and PostgreSQL services from the repository root, then run the UI:

```bash
docker compose up -d db api worker
cd apps/web
pnpm install
pnpm dev
```

Open <http://localhost:3000>. The default development API origin is
`http://localhost:8001`; override it with `API_ORIGIN` if needed.

To run the complete stack in containers:

```bash
docker compose up --build
```

## Workspace coverage

- PDF upload with asynchronous processing status and automatic polling
- Corpus inventory and relationship distribution
- Searchable fact browser with raw and normalized values
- Exact evidence quotes, page numbers, element IDs, and bounding-box locator
- Embedded source-PDF inspection
- Job progress, checkpoint events, failure details, and retry controls
- Cross-document relationship filtering and side-by-side evidence comparison
- Responsive shadcn sidebar and reviewer-focused empty, loading, and error states

## Verify

```bash
pnpm format
pnpm lint
pnpm build
```
