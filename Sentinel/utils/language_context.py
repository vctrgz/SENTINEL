from __future__ import annotations

import re


_SPANISH_HINTS = (
    r"\b(el|la|los|las|un|una|de|del|que|por|para|con|sin|como|cu[aá]l|ultimo|[uú]ltimo|informaci[oó]n|vulnerabilidad|publicado|respuesta|idioma|red|dispositivos)\b",
)
_ENGLISH_HINTS = (
    r"\b(the|a|an|of|for|with|without|what|which|latest|current|published|vulnerability|information|answer|language|network|devices)\b",
)
_PORTUGUESE_HINTS = (
    r"\b(o|a|os|as|de|do|da|que|com|sem|qual|ultimo|[uú]ltimo|informa[cç][aã]o|vulnerabilidade|publicado|resposta|idioma|rede|dispositivos)\b",
)
_FRENCH_HINTS = (
    r"\b(le|la|les|de|du|des|que|avec|sans|quel|quelle|dernier|information|vuln[eé]rabilit[eé]|publi[eé]|r[eé]ponse|langue|r[eé]seau|appareils)\b",
)

_LANGUAGE_NAMES = {
    "es": "Spanish",
    "en": "English",
    "pt": "Portuguese",
    "fr": "French",
}


def detect_language(text: str) -> str:
    normalized = (text or "").lower()
    if any(re.search(pattern, normalized) for pattern in _SPANISH_HINTS):
        return "es"
    if any(re.search(pattern, normalized) for pattern in _PORTUGUESE_HINTS):
        return "pt"
    if any(re.search(pattern, normalized) for pattern in _FRENCH_HINTS):
        return "fr"
    if any(re.search(pattern, normalized) for pattern in _ENGLISH_HINTS):
        return "en"
    return "en"


def build_language_context(text: str | None = None, language: str | None = None) -> dict:
    code = (language or detect_language(text or "") or "en").lower()
    if code not in _LANGUAGE_NAMES:
        code = "en"

    return {
        "code": code,
        "name": _LANGUAGE_NAMES[code],
        "instruction": (
            f"Respond entirely in {_LANGUAGE_NAMES[code]}. "
            "Do not mix languages unless quoting source material, commands, code, product names, "
            "or protocol identifiers. Keep the same language even if intermediate tools, logs, "
            "or prompts use another language."
        ),
    }


def get_language_instruction(language_context: dict | None) -> str:
    if not language_context:
        language_context = build_language_context(language="en")
    return language_context.get("instruction", build_language_context(language="en")["instruction"])
