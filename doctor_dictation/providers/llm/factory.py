"""make_llm: turns Settings into a provider, or None when no key is configured."""
from __future__ import annotations

from ...config import Settings
from .base import LlmProvider
from .openai_compat import OpenAICompatLlm
from .stub import StubLlm


def make_llm(s: Settings, *, vision: bool = False) -> LlmProvider | None:
    """An unknown LLM_PROVIDER acts like "openai" (today's default branch).

    `vision=True` prefers `llm_vision_model`; blank falls back to the text model.
    """
    if s.llm_provider == "stub":
        if not s.allow_stub_providers:
            raise ValueError("LLM_PROVIDER=stub requires ALLOW_STUB_PROVIDERS=1")
        return StubLlm.from_env()
    if s.llm_provider == "deepseek":
        name, base, model = "deepseek", s.deepseek_base_url, s.deepseek_model
        key, seed = s.deepseek_api_key, s.deepseek_seed
    else:
        name, base, model = "openai", s.openai_base_url, s.llm_model
        key, seed = s.openai_api_key, s.llm_seed
    if not key:
        return None
    if vision:
        model = (s.llm_vision_model or "").strip() or model
    return OpenAICompatLlm(name=name, base_url=base, model=model, api_key=key, seed=seed)
