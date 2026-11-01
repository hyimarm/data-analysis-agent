from __future__ import annotations

from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from .config import settings

@lru_cache(maxsize=2)
def get_llm(temperature:float|None=None) -> BaseChatModel:
    kwargs = {"temperature": settings.temperature if temperature is None else temperature}

    if settings.llm_provider == "deepseek":
        return init_chat_model(
            settings.llm_model,
            model_provider="openai",
            base_url = settings.llm_base_url,
            api_key = settings.llm_api_key,
            **kwargs,
        )

    return init_chat_model(
        settings.llm_model,
        model_provider="ollama",
        base_url=settings.llm_base_url,
        **kwargs,
    )