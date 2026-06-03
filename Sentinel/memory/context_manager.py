import re
from typing import Any, Dict, List, Optional
from utils.logger import logger


# Estimación conservadora: 1 token ≈ 4 caracteres (inglés/código)
# Para español/chino puede ser menos, así que usamos 3.5 para ser seguros
CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Estimación rápida de tokens sin necesidad de tokenizador."""
    if not text:
        return 0
    return max(1, int(len(text) / CHARS_PER_TOKEN))


class ContextManager:
    """
    Para tareas largas (SWE-bench Pro: patches de 107 líneas en 4+ archivos)
    el contexto crece indefinidamente hasta superar el límite del modelo.
    
    Este módulo:
    1. Estima el tamaño del contexto en tokens
    2. Trunca o resume el historial cuando se acerca al límite
    3. Garantiza que siempre quepan: objetivo + instrucciones + respuesta
    """

    # Límites por defecto conservadores (ajustar según el modelo)
    DEFAULT_MAX_TOKENS    = 8_000   # total del contexto
    RESPONSE_RESERVE      = 1_500   # tokens reservados para la respuesta
    SYSTEM_PROMPT_RESERVE = 2_000   # estimado del system prompt + skills

    def __init__(
        self,
        max_context_tokens: int = DEFAULT_MAX_TOKENS,
        response_reserve: int   = RESPONSE_RESERVE,
    ):
        self.max_context_tokens = max_context_tokens
        self.response_reserve   = response_reserve
        # Tokens disponibles para el user prompt
        self.available_tokens = (
            max_context_tokens
            - response_reserve
            - self.SYSTEM_PROMPT_RESERVE
        )

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def prepare_task_context(self, task: dict) -> dict:
        """
        Prepara el contexto de una tarea asegurando que cabe en la
        ventana de contexto. Trunca el historial si es necesario.
        """
        context = task.get("context", {})

        # Serializar para medir
        context_str = str(context)
        current_tokens = estimate_tokens(context_str)

        if current_tokens <= self.available_tokens:
            return context  # cabe sin modificar

        logger.warning(
            f"[ContextManager] Contexto ({current_tokens} tokens) supera el límite "
            f"({self.available_tokens} tokens). Aplicando truncación."
        )

        return self._truncate_context(context)

    def fits_in_window(self, system_prompt: str, user_prompt: str) -> bool:
        """Verifica si el par system+user cabe en la ventana."""
        total = estimate_tokens(system_prompt) + estimate_tokens(user_prompt)
        return total <= (self.max_context_tokens - self.response_reserve)

    def truncate_prompt(self, system_prompt: str, user_prompt: str) -> tuple[str, str]:
        """
        Si el par system+user no cabe, trunca el user_prompt preservando
        el principio (objetivo) y el final (contexto más reciente).
        """
        if self.fits_in_window(system_prompt, user_prompt):
            return system_prompt, user_prompt

        system_tokens = estimate_tokens(system_prompt)
        available_for_user = (
            self.max_context_tokens
            - self.response_reserve
            - system_tokens
            - 100  # margen de seguridad
        )

        if available_for_user < 200:
            logger.error("[ContextManager] System prompt demasiado largo para dejar espacio al user prompt.")
            return system_prompt, user_prompt[:200] + "\n[contexto truncado por límite de tokens]"

        max_chars = int(available_for_user * CHARS_PER_TOKEN)

        if len(user_prompt) <= max_chars:
            return system_prompt, user_prompt

        # Truncación inteligente: preservar inicio y final
        keep_start = int(max_chars * 0.6)
        keep_end   = max_chars - keep_start - 50

        truncated = (
            user_prompt[:keep_start]
            + "\n\n[... contexto intermedio truncado por límite de tokens ...]\n\n"
            + user_prompt[-keep_end:]
        )

        logger.info(
            f"[ContextManager] User prompt truncado: "
            f"{len(user_prompt)} → {len(truncated)} chars"
        )

        return system_prompt, truncated

    # ------------------------------------------------------------------ #
    # Helpers internos                                                     #
    # ------------------------------------------------------------------ #

    def _truncate_context(self, context: dict) -> dict:
        """
        Trunca el contexto de la tarea manteniendo lo más relevante:
        - errors: últimos 3 (los más recientes)
        - history: últimas 3 entradas
        - memory_summary: ya es un resumen, se respetas
        """
        truncated = dict(context)

        history = context.get("history", [])
        if len(history) > 3:
            truncated["history"] = history[-3:]
            truncated["history_note"] = f"[{len(history) - 3} entradas anteriores omitidas]"

        errors = context.get("errors", [])
        if len(errors) > 3:
            truncated["errors"] = errors[-3:]
            truncated["errors_note"] = f"[{len(errors) - 3} errores anteriores omitidos]"

        return truncated