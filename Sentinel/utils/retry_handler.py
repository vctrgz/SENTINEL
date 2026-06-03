import time
import random
import functools
from typing import Any, Callable, Optional, Tuple
from utils.logger import logger


# ------------------------------------------------------------------ #
# Clasificación de errores                                             #
# ------------------------------------------------------------------ #

CONNECTION_ERRORS = (
    "ConnectionError", "ConnectionRefusedError", "Timeout",
    "No se puede conectar", "ConnectTimeout", "ReadTimeout"
)
RATE_LIMIT_ERRORS = ("429", "rate limit", "too many requests")
FATAL_ERRORS = (
    "ImportError", "SyntaxError", "PermissionError",
    "comando no encontrado", "FileNotFoundError"
)


def classify_error(error: Exception) -> str:
    msg = str(error).lower()
    if any(e.lower() in msg for e in FATAL_ERRORS):
        return "fatal"
    if any(e.lower() in msg for e in CONNECTION_ERRORS):
        return "connection"
    if any(e.lower() in msg for e in RATE_LIMIT_ERRORS):
        return "rate_limit"
    return "transient"


# ------------------------------------------------------------------ #
# RetryHandler                                                         #
# ------------------------------------------------------------------ #

class RetryHandler:
    """
    Backoff exponencial con jitter:
        wait = min(base_wait * 2^attempt, max_wait) + random(0, jitter)
    """

    # (base_wait, max_wait, jitter)
    STRATEGIES = {
        "connection":  (1.0,  16.0,  0.5),
        "rate_limit":  (30.0, 120.0, 5.0),
        "transient":   (2.0,  30.0,  1.0),
        "fatal":       (0.0,  0.0,   0.0),
    }

    def __init__(
        self,
        max_retries: int   = 3,
        base_wait:   float = 2.0,
        max_wait:    float = 30.0,
        jitter:      float = 1.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_wait   = base_wait
        self.max_wait    = max_wait
        self.jitter      = jitter

    def execute_with_retry(
        self,
        func: Callable,
        *args: Any,
        operation_name: str = "operación",
        **kwargs: Any,
    ) -> Tuple[bool, Any]:               # ← Fix: era Tuple[bool, any] (builtin)
        last_exception: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"[RetryHandler] '{operation_name}' exitoso en intento {attempt + 1}")
                return True, result

            except Exception as e:
                last_exception = e
                error_type     = classify_error(e)

                if error_type == "fatal":
                    logger.error(f"[RetryHandler] Error fatal en '{operation_name}': {e}. No se reintenta.")
                    return False, e

                if attempt < self.max_retries:
                    wait = self._calculate_wait(attempt, error_type)
                    logger.warning(
                        f"[RetryHandler] '{operation_name}' falló ({error_type}): {e}. "
                        f"Reintento {attempt + 1}/{self.max_retries} en {wait:.1f}s..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[RetryHandler] '{operation_name}' agotó {self.max_retries} reintentos. "
                        f"Último error: {e}"
                    )

        return False, last_exception

    def _calculate_wait(self, attempt: int, error_type: str) -> float:
        base, max_w, jitter = self.STRATEGIES.get(
            error_type,
            (self.base_wait, self.max_wait, self.jitter)
        )
        exponential = min(base * (2 ** attempt), max_w)
        return exponential + random.uniform(0, jitter)

    def retry(self, max_retries: Optional[int] = None, operation_name: str = "") -> Callable:
        retries = max_retries if max_retries is not None else self.max_retries

        def decorator(func: Callable) -> Callable:
            name = operation_name or func.__name__

            @functools.wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                success, result = self.execute_with_retry(
                    func, *args, operation_name=name, **kwargs
                )
                if not success:
                    raise result  # type: ignore[misc]
                return result

            return wrapper
        return decorator


DEFAULT_RETRY_HANDLER = RetryHandler(max_retries=3)