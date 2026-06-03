"""
utils/ollama_client.py

Backward-compatibility shim.

All agent code imports OllamaClient — we keep that name but now it
delegates to MultiProviderLLMClient (HuggingFace + Groq fallback chain).
The context_manager truncation and retry logic are preserved.
"""

from memory.context_manager import ContextManager
from utils.llm_client import MultiProviderLLMClient
from utils.runtime_tracer import get_tracer


class OllamaClient:
    """
    Same public interface as before (.chat, .is_available, .list_models, .model).
    Internally uses MultiProviderLLMClient instead of Ollama.
    """

    def __init__(self, llm_name: str = "") -> None:
        self._client         = MultiProviderLLMClient(model_hint=llm_name)
        self.model           = self._client.model
        self.context_manager = ContextManager()
        self._tracer         = get_tracer()

    def chat(
        self,
        system_prompt: str,
        user_prompt:   str,
        expect_json:   bool = False,
    ) -> str:
        # Truncate to fit context window before sending
        system_prompt, user_prompt = self.context_manager.truncate_prompt(
            system_prompt, user_prompt
        )
        return self._client.chat(system_prompt, user_prompt, expect_json)

    def is_available(self) -> bool:
        return self._client.is_available()

    def list_models(self) -> list:
        return self._client.list_models()