"""
utils/llm_client.py

Multi-provider LLM client with provider fallback.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv

from utils.logger import logger
from utils.runtime_tracer import get_tracer


_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)


def _clean_key(raw: str | None) -> str:
    if not raw:
        return ""
    cleaned = raw.strip()
    cleaned = cleaned.replace("\r", "").replace("\n", "").replace("\t", "")
    cleaned = cleaned.strip("\"'")
    if not cleaned or cleaned.startswith("#"):
        return ""
    placeholder_markers = (
        "your_",
        "tu_",
        "changeme",
        "replace",
        "placeholder",
        "pon_",
    )
    if any(marker in cleaned.lower() for marker in placeholder_markers):
        return ""
    return cleaned


_EMPTY_RESPONSE_RETRIES = int(_clean_key(os.getenv("LLM_EMPTY_RESPONSE_RETRIES", "1")) or "1")


class Provider:
    def __init__(self, name: str, model: str, api_key_env: str) -> None:
        self.name = name
        self.model = model
        self.api_key_env = api_key_env

    @property
    def api_key(self) -> str:
        return _clean_key(os.getenv(self.api_key_env, ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.api_key)

    def chat_url(self) -> str:
        if self.name == "openai":
            return "https://api.openai.com/v1/chat/completions"
        if self.name == "huggingface":
            return "https://router.huggingface.co/v1/chat/completions"
        if self.name == "groq":
            return "https://api.groq.com/openai/v1/chat/completions"
        if self.name == "openrouter":
            return "https://openrouter.ai/api/v1/chat/completions"
        raise ValueError(f"Unknown provider: {self.name}")

    def __str__(self) -> str:
        return f"{self.name}/{self.model}"


def _build_providers() -> List[Provider]:
    providers: List[Provider] = []
    seen: set[tuple[str, str]] = set()

    def _add_provider(name: str, model_env: str, default_model: str, api_key_env: str) -> None:
        model = _clean_key(os.getenv(model_env, default_model))
        key = (name, model)
        if model and key not in seen:
            seen.add(key)
            providers.append(Provider(name=name, model=model, api_key_env=api_key_env))

    _add_provider("openrouter", "OPENROUTER_MODEL_PRIMARY", "meta-llama/llama-3.3-70b-instruct", "OPENROUTER_API_KEY")
    _add_provider("openrouter", "OPENROUTER_MODEL_FALLBACK", "", "OPENROUTER_API_KEY")
    _add_provider("openrouter", "OPENROUTER_MODEL_SECONDARY", "", "OPENROUTER_API_KEY")
    _add_provider("huggingface", "HF_MODEL_PRIMARY", "mistralai/Mistral-7B-Instruct-v0.3", "HF_API_TOKEN")
    _add_provider("huggingface", "HF_MODEL_FALLBACK", "HuggingFaceH4/zephyr-7b-beta", "HF_API_TOKEN")
    _add_provider("groq", "GROQ_MODEL_PRIMARY", "llama-3.1-8b-instant", "GROQ_API_KEY")
    _add_provider("groq", "GROQ_MODEL_FALLBACK", "llama-3.3-70b-versatile", "GROQ_API_KEY")
    _add_provider("groq", "GROQ_MODEL_TERTIARY", "groq/compound", "GROQ_API_KEY")
    _add_provider("openai", "OPENAI_MODEL", "gpt-4.1-mini", "OPENAI_API_KEY")
    return providers


def _extract_message_content(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    text_parts.append(text.strip())
        return "\n".join(text_parts).strip()
    return ""


_TIMEOUT = int(_clean_key(os.getenv("LLM_TIMEOUT", "60")) or "60")


def _do_chat(
    provider: Provider,
    system: str,
    user: str,
    expect_json: bool = False,
    max_tokens: int = 2048,
) -> str:
    headers: Dict[str, str] = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }

    messages: List[Dict[str, str]] = []
    if system.strip():
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    payload: Dict[str, Any] = {
        "model": provider.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    if provider.name == "groq":
        payload["stream"] = False
    if expect_json:
        payload["response_format"] = {"type": "json_object"}

    attempts = 1 + _EMPTY_RESPONSE_RETRIES
    last_error = ""
    for attempt in range(attempts):
        current_payload = dict(payload)
        resp = requests.post(provider.chat_url(), json=current_payload, headers=headers, timeout=_TIMEOUT)

        if resp.status_code == 422 and provider.name == "huggingface" and expect_json:
            current_payload.pop("response_format", None)
            resp = requests.post(provider.chat_url(), json=current_payload, headers=headers, timeout=_TIMEOUT)

        if resp.status_code != 200:
            raise RuntimeError(f"[{provider}] HTTP {resp.status_code}: {resp.text[:400]}")

        data = resp.json()
        if isinstance(data, list) and data:
            text = data[0].get("generated_text", "")
            if system and system in text:
                text = text.replace(system, "").strip()
            if user and user in text:
                text = text.replace(user, "").strip()
            if text.strip():
                return text.strip()
            last_error = f"[{provider}] Empty legacy response content"
        else:
            content = _extract_message_content(data)
            if content:
                return content
            last_error = f"[{provider}] Empty response content"

        if attempt < attempts - 1:
            time.sleep(0.4 * (attempt + 1))

    raise RuntimeError(last_error or f"[{provider}] Empty response content")


class MultiProviderLLMClient:
    def __init__(self, model_hint: str = "") -> None:
        self._tracer = get_tracer()
        self._providers = _build_providers()
        self.model = next((p.model for p in self._providers if p.is_configured), "none")

        for provider in self._providers:
            if provider.is_configured:
                logger.info(f"[LLMClient] configured provider={provider} url={provider.chat_url()}")
            else:
                logger.warning(
                    f"[LLMClient] provider={provider} {provider.api_key_env} not set or empty"
                )

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        expect_json: bool = False,
    ) -> str:
        errors: List[str] = []

        for provider in self._providers:
            if not provider.is_configured:
                continue

            self._tracer.log("llm", f"attempt:{provider}", {"expect_json": expect_json})
            started = time.monotonic()

            try:
                content = _do_chat(provider, system_prompt, user_prompt, expect_json)
                duration = time.monotonic() - started
                self._tracer.log_llm_call(
                    model=provider.model,
                    agent=provider.name,
                    duration_s=duration,
                    tokens_est=len(content) // 4,
                    expect_json=expect_json,
                )
                return content
            except requests.exceptions.Timeout:
                err = f"{provider}: timeout after {_TIMEOUT}s"
            except requests.exceptions.ConnectionError as exc:
                err = f"{provider}: connection error - {exc}"
            except RuntimeError as exc:
                err = str(exc)
            except Exception as exc:
                err = f"{provider}: unexpected - {exc}"

            logger.warning(f"[LLMClient] {err} -> trying next provider")
            self._tracer.log("llm", f"provider_failed:{provider}", {"error": err[:150]}, level="WARN")
            errors.append(err)

        raise RuntimeError("All LLM providers failed:\n" + "\n".join(f"  - {e}" for e in errors))

    def is_available(self) -> bool:
        return any(provider.is_configured for provider in self._providers)

    def list_models(self) -> List[str]:
        return [f"{provider.name}/{provider.model}" for provider in self._providers if provider.is_configured]
