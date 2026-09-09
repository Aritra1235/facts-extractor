import asyncio
import json
from collections.abc import Mapping
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import Settings
from app.llm.base import EvidenceInput
from app.llm.schemas import ExtractedFact, ExtractionBatch, RelationshipClassification

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class OpenRouterError(RuntimeError):
    pass


class OpenRouterProvider:
    _retryable_statuses = {429, 500, 502, 503, 504, 524, 529}

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None):
        missing = [
            name
            for name, value in (
                ("OPENROUTER_API_KEY", settings.openrouter_api_key),
                ("OPENROUTER_TEXT_MODEL", settings.openrouter_text_model),
                ("OPENROUTER_EMBEDDING_MODEL", settings.openrouter_embedding_model),
            )
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing required OpenRouter settings: {', '.join(missing)}")

        self.settings = settings
        self._owns_client = client is None
        self.headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "X-Title": settings.openrouter_app_name,
        }
        if settings.openrouter_site_url:
            self.headers["HTTP-Referer"] = settings.openrouter_site_url
        self.client = client or httpx.AsyncClient(
            base_url=settings.openrouter_base_url.rstrip("/"),
            timeout=settings.openrouter_timeout_ms / 1_000,
        )

    async def extract_facts(
        self,
        *,
        document_name: str,
        evidence: list[EvidenceInput],
        limit: int,
    ) -> list[ExtractedFact]:
        evidence_text = "\n\n".join(
            f'<evidence id="{item.id}" page="{item.page_index + 1}">\n'
            f"{item.text}\n</evidence>"
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
        parsed = await self._structured_completion(
            prompt=prompt,
            response_model=ExtractionBatch,
            schema_name="fact_extraction_batch",
        )
        return parsed.facts

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = {
            "model": self.settings.openrouter_embedding_model,
            "input": texts,
            "dimensions": self.settings.embedding_dimensions,
            "encoding_format": "float",
        }
        data = await self._post("/embeddings", payload)
        raw_embeddings = data.get("data")
        if not isinstance(raw_embeddings, list):
            raise OpenRouterError("OpenRouter returned no embedding data")

        try:
            ordered = sorted(raw_embeddings, key=lambda item: int(item["index"]))
            embeddings = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as error:
            raise OpenRouterError("OpenRouter returned malformed embedding data") from error

        if len(embeddings) != len(texts):
            raise OpenRouterError(
                f"OpenRouter returned {len(embeddings)} embeddings for {len(texts)} inputs"
            )
        invalid_dimensions = [
            len(vector)
            for vector in embeddings
            if len(vector) != self.settings.embedding_dimensions
        ]
        if invalid_dimensions:
            raise OpenRouterError(
                "OpenRouter embedding dimensions do not match EMBEDDING_DIMENSIONS: "
                f"expected {self.settings.embedding_dimensions}, got {invalid_dimensions[0]}"
            )
        return embeddings

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
        return await self._structured_completion(
            prompt=prompt,
            response_model=RelationshipClassification,
            schema_name="fact_relationship",
        )

    async def _structured_completion(
        self,
        *,
        prompt: str,
        response_model: type[StructuredResponse],
        schema_name: str,
    ) -> StructuredResponse:
        payload = {
            "model": self.settings.openrouter_text_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": self._strict_json_schema(response_model),
                },
            },
            "provider": {"require_parameters": True},
        }
        data = await self._post("/chat/completions", payload)
        try:
            message = data["choices"][0]["message"]
            content = message["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise OpenRouterError("OpenRouter returned no chat completion content") from error
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("OpenRouter returned empty chat completion content")
        return response_model.model_validate_json(self._strip_code_fence(content))

    async def _post(self, path: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        attempts = self.settings.openrouter_retry_attempts
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await self.client.post(path, json=payload, headers=self.headers)
            except httpx.TransportError as error:
                last_error = error
                if attempt + 1 == attempts:
                    break
                await asyncio.sleep(2**attempt)
                continue

            if response.is_success:
                try:
                    body = response.json()
                except json.JSONDecodeError as error:
                    raise OpenRouterError("OpenRouter returned invalid JSON") from error
                if not isinstance(body, dict):
                    raise OpenRouterError("OpenRouter returned an unexpected response shape")
                return body

            error = self._http_error(response)
            if response.status_code not in self._retryable_statuses or attempt + 1 == attempts:
                raise error
            last_error = error
            await asyncio.sleep(self._retry_delay(response, attempt))

        raise OpenRouterError(
            f"OpenRouter request failed after {attempts} attempts"
        ) from last_error

    @staticmethod
    def _http_error(response: httpx.Response) -> OpenRouterError:
        message: str | None = None
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict) and isinstance(error.get("message"), str):
                    message = error["message"]
        except json.JSONDecodeError:
            pass
        detail = message or response.text or response.reason_phrase
        return OpenRouterError(
            f"OpenRouter request failed ({response.status_code}): {detail[:1000]}"
        )

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return min(10.0, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return min(10.0, float(2**attempt))

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            first_newline = stripped.find("\n")
            if first_newline != -1:
                return stripped[first_newline + 1 : -3].strip()
        return stripped

    @staticmethod
    def _strict_json_schema(response_model: type[BaseModel]) -> dict[str, Any]:
        schema = response_model.model_json_schema()

        def tighten(node: Any) -> None:
            if isinstance(node, dict):
                properties = node.get("properties")
                if isinstance(properties, dict):
                    node["additionalProperties"] = False
                    node["required"] = list(properties)
                for value in node.values():
                    tighten(value)
            elif isinstance(node, list):
                for value in node:
                    tighten(value)

        tighten(schema)
        return schema

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()
