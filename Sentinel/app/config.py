"""
app/config.py

Configuration for SentinelAI.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(dotenv_path=DOTENV_PATH, override=True)


def _clean_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if not value:
        return ""
    cleaned = value.strip().replace("\r", "").replace("\n", "").replace("\t", "").strip("\"'")
    if not cleaned or cleaned.startswith("#"):
        return ""
    placeholder_markers = ("your_", "tu_", "changeme", "replace", "placeholder", "pon_")
    if any(marker in cleaned.lower() for marker in placeholder_markers):
        return ""
    return cleaned


class Config:
    OPENAI_API_KEY = _clean_env_value("OPENAI_API_KEY")
    HF_API_TOKEN = _clean_env_value("HF_API_TOKEN")
    GROQ_API_KEY = _clean_env_value("GROQ_API_KEY")
    OPENROUTER_API_KEY = _clean_env_value("OPENROUTER_API_KEY")

    OPENAI_MODEL = _clean_env_value("OPENAI_MODEL", "gpt-4.1-mini")

    # Wazuh
    WAZUH_HOST = _clean_env_value("WAZUH_HOST") or _clean_env_value("WAZUH_API_URL")
    WAZUH_USER = _clean_env_value("WAZUH_USER", "wazuh-wui") or "wazuh-wui"
    WAZUH_PASSWORD = _clean_env_value("WAZUH_PASSWORD") or _clean_env_value("WAZUH_PASS")
    WAZUH_VERIFY_SSL = os.getenv("WAZUH_VERIFY_SSL", "false").lower() == "true"
    WAZUH_ALERT_LEVEL_MIN = int(os.getenv("WAZUH_ALERT_LEVEL_MIN", "10"))
    WAZUH_POLL_INTERVAL = int(os.getenv("WAZUH_POLL_INTERVAL", "60"))
    WAZUH_INDEXER_URL = _clean_env_value("WAZUH_INDEXER_URL") or _clean_env_value("OPENSEARCH_URL")
    WAZUH_INDEXER_USER = _clean_env_value("WAZUH_INDEXER_USER") or _clean_env_value("OPENSEARCH_USER", "admin") or "admin"
    WAZUH_INDEXER_PASSWORD = (
        _clean_env_value("WAZUH_INDEXER_PASSWORD")
        or _clean_env_value("OPENSEARCH_PASSWORD")
        or _clean_env_value("OS_PASS")
        or _clean_env_value("WAZUH_PASS")
    )
    WAZUH_ALERTS_INDEX = _clean_env_value("WAZUH_ALERTS_INDEX", "wazuh-alerts-4.x-*") or "wazuh-alerts-4.x-*"

    HF_MODEL_PRIMARY = _clean_env_value("HF_MODEL_PRIMARY", "mistralai/Mistral-7B-Instruct-v0.3")
    HF_MODEL_FALLBACK = _clean_env_value("HF_MODEL_FALLBACK", "HuggingFaceH4/zephyr-7b-beta")

    GROQ_MODEL_PRIMARY = _clean_env_value("GROQ_MODEL_PRIMARY", "llama-3.1-8b-instant")
    GROQ_MODEL_FALLBACK = _clean_env_value("GROQ_MODEL_FALLBACK", "llama-3.3-70b-versatile")
    GROQ_MODEL_TERTIARY = _clean_env_value("GROQ_MODEL_TERTIARY", "groq/compound")

    OPENROUTER_MODEL_PRIMARY = _clean_env_value("OPENROUTER_MODEL_PRIMARY", "meta-llama/llama-3.3-70b-instruct")
    OPENROUTER_MODEL_FALLBACK = _clean_env_value("OPENROUTER_MODEL_FALLBACK")
    OPENROUTER_MODEL_SECONDARY = _clean_env_value("OPENROUTER_MODEL_SECONDARY")

    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
    LLM_EMPTY_RESPONSE_RETRIES = int(os.getenv("LLM_EMPTY_RESPONSE_RETRIES", "1"))

    DEFAULT_MODEL = "balanceado"
    MODELS = {
        "defensivo": "mistralai/Mistral-7B-Instruct-v0.3",
        "ofensivo": "HuggingFaceH4/zephyr-7b-beta",
        "balanceado": "llama-3.1-8b-instant",
    }

    MAX_ITERATIONS = int(os.getenv("MAX_ITERATIONS", "5"))
    TIMEOUT = int(os.getenv("TIMEOUT", "60"))

    REQUIRE_CONFIRMATION = os.getenv("REQUIRE_CONFIRMATION", "true").lower() == "true"
    ALLOW_DANGEROUS_COMMANDS = os.getenv("ALLOW_DANGEROUS_COMMANDS", "false").lower() == "true"

    LOG_DIR = os.path.join(BASE_DIR, "logs")
    MEMORY_DIR = os.path.join(BASE_DIR, "memory")
    SANDBOX_PATH = os.path.join(BASE_DIR, "sandbox")

    SANDBOX_MODE = os.getenv("SANDBOX_MODE", "true").lower() == "true"
    DOCKER_IMAGE = os.getenv("DOCKER_IMAGE", "python:3.11-slim")

    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    @classmethod
    def validate(cls) -> list[str]:
        warnings: list[str] = []

        if not os.path.exists(DOTENV_PATH):
            warnings.append(f"No se encontro .env en {DOTENV_PATH}")

        if not cls.WAZUH_HOST:
            warnings.append("WAZUH_HOST no configurado - integracion Wazuh deshabilitada.")
        if not cls.OPENAI_API_KEY:
            warnings.append(
                "OPENAI_API_KEY no configurado - OpenAI deshabilitado. "
                "Obten uno en: https://platform.openai.com/api-keys"
            )
        if not cls.OPENROUTER_API_KEY:
            warnings.append(
                "OPENROUTER_API_KEY no configurado - OpenRouter deshabilitado. "
                "Obten uno en: https://openrouter.ai/keys"
            )
        if not cls.HF_API_TOKEN:
            warnings.append(
                "HF_API_TOKEN no configurado - HuggingFace deshabilitado. "
                "Obten uno en: https://huggingface.co/settings/tokens"
            )
        if not cls.GROQ_API_KEY:
            warnings.append(
                "GROQ_API_KEY no configurado - Groq deshabilitado. "
                "Obten uno en: https://console.groq.com/keys"
            )
        if not cls.OPENAI_API_KEY and not cls.OPENROUTER_API_KEY and not cls.HF_API_TOKEN and not cls.GROQ_API_KEY:
            warnings.append("Ningun proveedor LLM configurado. El sistema no podra generar respuestas.")
        if cls.MAX_ITERATIONS < 1:
            warnings.append("MAX_ITERATIONS debe ser >= 1")
        if cls.TIMEOUT < 5:
            warnings.append("TIMEOUT muy bajo (< 5s)")

        return warnings
