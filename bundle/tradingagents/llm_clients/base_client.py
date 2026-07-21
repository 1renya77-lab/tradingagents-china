from abc import ABC, abstractmethod
from typing import Any, Optional
import warnings
import json


def normalize_content(response):
    """Normalize typed content blocks returned by some providers to plain text.

    Also handles tool_calls where args may be stringified JSON instead of dict.
    """
    content = getattr(response, "content", None)
    if isinstance(content, list):
        texts = [
            item.get("text", "") if isinstance(item, dict) and item.get("type") == "text"
            else item if isinstance(item, str) else ""
            for item in content
        ]
        response.content = "\n".join(text for text in texts if text)

    # Fix tool_calls where args is a string instead of dict (common with local models)
    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls and isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict) and "args" in tc:
                args = tc["args"]
                if isinstance(args, str):
                    try:
                        tc["args"] = json.loads(args)
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON

    return response


class BaseLLMClient(ABC):
    """Minimal provider wrapper used by CLI and future graph integration."""

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        self.model = model
        self.base_url = base_url
        self.kwargs = kwargs

    def get_provider_name(self) -> str:
        provider = getattr(self, "provider", None)
        if provider:
            return str(provider)
        return self.__class__.__name__.removesuffix("Client").lower()

    def warn_if_unknown_model(self) -> None:
        if self.validate_model():
            return

        warnings.warn(
            (
                f"Model '{self.model}' is not in the known model list for "
                f"provider '{self.get_provider_name()}'. Continuing anyway."
            ),
            RuntimeWarning,
            stacklevel=2,
        )

    @abstractmethod
    def get_llm(self) -> Any:
        """Return the configured LangChain client."""

    @abstractmethod
    def validate_model(self) -> bool:
        """Return whether the model is known for the provider."""
