import re
from dataclasses import dataclass, field
from typing import List, Optional
from utils.logger import logger


PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(previous|all|above)\s+instructions?",
    r"disregard\s+(your|the)\s+(previous|system|above)",
    r"forget\s+(everything|your\s+instructions?)",
    r"you\s+are\s+now\s+(a|an)\s+",
    r"act\s+as\s+(if\s+you\s+are|a|an)",
    r"new\s+system\s+prompt",
    r"jailbreak",
    r"DAN\s*(mode)?",
    r"developer\s+mode",
    r"override\s+(your|all)\s+(instructions?|rules?)",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"###\s*System",
]

DANGEROUS_PAYLOAD_PATTERNS = [
    r"rm\s+-rf\s+/",
    r":()\{.*\|.*&\}",
    r"dd\s+if=/dev/zero",
    r"mkfs\.",
    r">\s*/dev/sd[a-z]",
    r"chmod\s+-R\s+777\s+/",
]


@dataclass
class ValidationResult:
    valid:        bool
    clean_input:  str
    warnings:     List[str]      = field(default_factory=list)
    blocked:      bool           = False
    block_reason: Optional[str]  = None


class InputValidator:

    MAX_INPUT_LENGTH = 4_000
    MIN_INPUT_LENGTH = 1

    def __init__(self) -> None:
        self._injection_re = [
            re.compile(p, re.IGNORECASE | re.DOTALL)
            for p in PROMPT_INJECTION_PATTERNS
        ]
        self._dangerous_re = [
            re.compile(p, re.IGNORECASE)
            for p in DANGEROUS_PAYLOAD_PATTERNS
        ]

    def validate(self, user_input: Optional[str]) -> ValidationResult:  # ← Fix: Optional[str]
        """
        Valida y sanitiza el input. Acepta None explícitamente
        para que los tests y el código de llamada sean type-safe.
        """
        # Capa 0: tipo incorrecto (None, int, etc.)
        if not isinstance(user_input, str):
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True, block_reason="El input debe ser texto"
            )

        # Capa 1: longitud
        if len(user_input) < self.MIN_INPUT_LENGTH:
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True, block_reason="Input vacío"
            )

        if len(user_input) > self.MAX_INPUT_LENGTH:
            return ValidationResult(
                valid=True,
                clean_input=user_input[:self.MAX_INPUT_LENGTH],
                warnings=[f"Input truncado a {self.MAX_INPUT_LENGTH} caracteres"],
            )

        # Capa 2: sanitización
        clean    = self._sanitize(user_input)
        warnings: List[str] = []

        # Capa 3: prompt injection
        injection = self._detect_injection(clean)
        if injection:
            logger.warning(f"[InputValidator] Prompt injection: {injection}")
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True,
                block_reason=f"Input bloqueado: posible prompt injection ({injection})"
            )

        # Capa 4: payloads peligrosos
        dangerous = self._detect_dangerous(clean)
        if dangerous:
            logger.warning(f"[InputValidator] Payload peligroso: {dangerous}")
            return ValidationResult(
                valid=False, clean_input="",
                blocked=True,
                block_reason="Input bloqueado: payload de comando peligroso detectado"
            )

        if len(clean) > 1000:
            warnings.append("Input largo — considera dividirlo en consultas más específicas")

        return ValidationResult(valid=True, clean_input=clean, warnings=warnings)

    def _sanitize(self, text: str) -> str:
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        return re.sub(r'  +', ' ', cleaned).strip()

    def _detect_injection(self, text: str) -> Optional[str]:
        for pattern in self._injection_re:
            m = pattern.search(text)
            if m:
                return m.group(0)[:50]
        return None

    def _detect_dangerous(self, text: str) -> Optional[str]:
        for pattern in self._dangerous_re:
            m = pattern.search(text)
            if m:
                return m.group(0)[:50]
        return None