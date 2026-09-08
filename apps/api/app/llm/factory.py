from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.gemini import GeminiProvider


def create_provider(settings: Settings) -> LLMProvider:
    providers = {"gemini": GeminiProvider}
    provider_class = providers.get(settings.llm_provider.casefold())
    if provider_class is None:
        supported = ", ".join(sorted(providers))
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER={settings.llm_provider!r}; supported: {supported}"
        )
    return provider_class(settings)
