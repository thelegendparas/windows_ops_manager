"""Model construction via OpenRouter (OpenAI-compatible API).

Keeping the model behind OpenRouter means the agent architecture never
marries to one vendor: GLM today, Claude/GPT/DeepSeek tomorrow — all by
changing MODEL_NAME in .env, no code changes.
"""

from __future__ import annotations

from agent.config import Settings


def make_model(settings: Settings):
    from pydantic_ai.models.openai import OpenAIModel
    from pydantic_ai.providers.openai import OpenAIProvider

    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Copy env.example to .env and add your key."
        )
    return OpenAIModel(
        settings.model_name,
        provider=OpenAIProvider(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        ),
    )