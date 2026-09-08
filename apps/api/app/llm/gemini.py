from google import genai
from google.genai import types

from app.core.config import Settings
from app.llm.base import EvidenceInput
from app.llm.schemas import ExtractedFact, ExtractionBatch, RelationshipClassification


class GeminiProvider:
    def __init__(self, settings: Settings):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is required for fact extraction")
        self.settings = settings
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=settings.gemini_timeout_ms,
                retry_options=types.HttpRetryOptions(
                    attempts=settings.gemini_retry_attempts,
                    initial_delay=1,
                    max_delay=10,
                    exp_base=2,
                    jitter=1,
                    http_status_codes=[429, 500, 502, 503, 504],
                ),
            ),
        )

    async def extract_facts(
        self,
        *,
        document_name: str,
        evidence: list[EvidenceInput],
        limit: int,
    ) -> list[ExtractedFact]:
        evidence_text = "\n\n".join(
            f'<evidence id="{item.id}" page="{item.page_index + 1}">\n{item.text}\n</evidence>'
            for item in evidence
        )
        page_numbers = sorted({item.page_index + 1 for item in evidence})
        prompt = f"""
Extract up to {limit} meaningful, independently checkable numerical or semantic facts from
PDF pages {page_numbers} of {document_name}.

Use only the supplied evidence. Ignore decorative text, page furniture, legal boilerplate,
and facts that cannot be tied to one evidence id. Keep values and supporting quotes verbatim.
The supporting quote must be an exact contiguous substring of that evidence. Do not calculate
or normalize values. Capture periods, scope, whether a claim is an observation, estimate,
forecast, target, or opinion, and estimate vintage when stated. The subject must be the entity
the claim concerns (for example Delhivery, India, or a business segment), never a period, value,
or metric name. Prefer decision-useful facts over administrative metadata. Use conservative
confidence.

{evidence_text}
""".strip()
        response = await self.client.aio.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ExtractionBatch,
                temperature=0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, ExtractionBatch):
            return parsed.facts
        return ExtractionBatch.model_validate_json(response.text).facts

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self.client.aio.models.embed_content(
            model=self.settings.gemini_embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="SEMANTIC_SIMILARITY",
                output_dimensionality=self.settings.embedding_dimensions,
            ),
        )
        embeddings = response.embeddings or []
        return [list(item.values or []) for item in embeddings]

    async def classify_relationship(
        self, *, fact_a: str, evidence_a: str, fact_b: str, evidence_b: str
    ) -> RelationshipClassification:
        prompt = f"""
Classify the relationship between two evidence-grounded facts. Prefer NOT_COMPARABLE when
period, scope, metric, or claim type prevents a meaningful comparison. A changed estimate
vintage is normally RECONCILABLE. Two forecasts for the same period may CONTRADICT while
still representing model disagreement rather than bad historical reporting. Do not add facts
not present below.

FACT A:
{fact_a}
EVIDENCE A:
{evidence_a}

FACT B:
{fact_b}
EVIDENCE B:
{evidence_b}
""".strip()
        response = await self.client.aio.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RelationshipClassification,
                temperature=0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        parsed = response.parsed
        if isinstance(parsed, RelationshipClassification):
            return parsed
        return RelationshipClassification.model_validate_json(response.text)

    async def close(self) -> None:
        await self.client.aio.aclose()
