from typing import Any, Optional
import os

from langchain_anthropic import ChatAnthropic

from .base_client import BaseLLMClient, normalize_content
from .validators import validate_model


class NormalizedChatAnthropic(ChatAnthropic):
    """Anthropic wrapper that normalizes structured content to text."""

    def invoke(self, input, config=None, **kwargs):
        return normalize_content(super().invoke(input, config, **kwargs))


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude models."""

    def __init__(
        self,
        model: str,
        base_url: Optional[str] = None,
        provider: str = "anthropic",
        **kwargs,
    ):
        super().__init__(model, base_url, **kwargs)
        self.provider = provider.lower()

    def get_llm(self) -> Any:
        self.warn_if_unknown_model()
        llm_kwargs = {"model": self.model}

        if self.base_url:
            llm_kwargs["base_url"] = self.base_url

        for key in ("timeout", "max_retries", "callbacks", "http_client", "http_async_client"):
            if key in self.kwargs:
                llm_kwargs[key] = self.kwargs[key]

        # API key from kwargs or environment
        if self.provider == "minimax":
            env_key = "MINIMAX_API_KEY"
        else:
            env_key = "ANTHROPIC_API_KEY"
        api_key = self.kwargs.get("api_key") or os.environ.get(env_key)
        if api_key:
            llm_kwargs["api_key"] = api_key

        return NormalizedChatAnthropic(**llm_kwargs)

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)
