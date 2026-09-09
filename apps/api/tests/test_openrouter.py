import json

import httpx
import pytest

from app.core.config import Settings
from app.llm.base import EvidenceInput
from app.llm.openrouter import OpenRouterError, OpenRouterProvider


def settings(**overrides: object) -> Settings:
    values = {
        "openrouter_api_key": "test-key",
        "openrouter_text_model": "test/text-model",
        "openrouter_embedding_model": "test/embedding-model",
        "embedding_dimensions": 3,
        "openrouter_retry_attempts": 1,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_extract_facts_uses_openrouter_structured_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test/text-model"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["response_format"]["json_schema"]["strict"] is True
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["facts"]
        extracted_fact_schema = schema["$defs"]["ExtractedFact"]
        assert extracted_fact_schema["additionalProperties"] is False
        assert set(extracted_fact_schema["required"]) == set(
            extracted_fact_schema["properties"]
        )
        assert payload["provider"] == {"require_parameters": True}
        content = {
            "facts": [
                {
                    "evidence_id": "evidence-1",
                    "subject": "India",
                    "predicate": "Real GDP growth",
                    "predicate_canonical": "macroeconomic.real_gdp_growth",
                    "value_raw": "6.5 per cent",
                    "unit": "per cent",
                    "period": "FY2024/25",
                    "scope": "national",
                    "claim_kind": "OBSERVATION",
                    "estimate_vintage": None,
                    "supporting_quote": "Real GDP growth was 6.5 per cent.",
                    "confidence": 0.96,
                }
            ]
        }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(content)}}]},
        )

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterProvider(settings(), client=client)

    facts = await provider.extract_facts(
        document_name="report.pdf",
        evidence=[
            EvidenceInput(
                id="evidence-1",
                text="Real GDP growth was 6.5 per cent.",
                page_index=0,
            )
        ],
        limit=8,
    )

    assert len(facts) == 1
    assert facts[0].subject == "India"
    await client.aclose()


@pytest.mark.asyncio
async def test_embeddings_preserve_openrouter_index_order() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/embeddings"
        payload = json.loads(request.content)
        assert payload == {
            "model": "test/embedding-model",
            "input": ["first", "second"],
            "dimensions": 3,
            "encoding_format": "float",
        }
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.4, 0.5, 0.6]},
                    {"index": 0, "embedding": [0.1, 0.2, 0.3]},
                ]
            },
        )

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterProvider(settings(), client=client)

    embeddings = await provider.embed(["first", "second"])

    assert embeddings == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    await client.aclose()


@pytest.mark.asyncio
async def test_embedding_dimension_mismatch_fails_before_pgvector_write() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})

    client = httpx.AsyncClient(
        base_url="https://openrouter.ai/api/v1",
        transport=httpx.MockTransport(handler),
    )
    provider = OpenRouterProvider(settings(), client=client)

    with pytest.raises(OpenRouterError, match="EMBEDDING_DIMENSIONS"):
        await provider.embed(["fact"])
    await client.aclose()


def test_provider_requires_key_and_both_models() -> None:
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        OpenRouterProvider(
            settings(
                openrouter_api_key=None,
                openrouter_text_model=None,
                openrouter_embedding_model=None,
            )
        )
