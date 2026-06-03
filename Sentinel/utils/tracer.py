import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from utils.logger import logger


class Tracer:
    """
    Sistema de trazabilidad para SentinelAI:
    - Formato JSONL (un objeto JSON por línea) → más eficiente para leer/parsear
    - Rotación automática cuando el archivo supera MAX_FILE_SIZE_MB
    - Retención configurable de archivos rotados (por defecto: 5 archivos)
    - Un archivo por sesión (nombre incluye timestamp)
    """

    MAX_FILE_SIZE_MB  = 10     # rotar cuando supera este tamaño
    MAX_ROTATED_FILES = 5      # mantener este número de archivos históricos

    def __init__(
        self,
        log_dir:          str  = "logs",
        max_file_size_mb: int  = MAX_FILE_SIZE_MB,
        max_rotated:      int  = MAX_ROTATED_FILES
    ):
        self.trace_id        = str(uuid.uuid4())
        self.steps:  List[Dict[str, Any]] = []
        self.log_dir         = Path(log_dir)
        self.max_bytes       = max_file_size_mb * 1024 * 1024
        self.max_rotated     = max_rotated

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._trace_file = self.log_dir / "traces.jsonl"

    # ------------------------------------------------------------------ #
    # Registro de pasos                                                    #
    # ------------------------------------------------------------------ #

    def log(self, agent: str, action: str, data: Any = None) -> None:
        """Añade un paso al trace de la sesión actual."""
        step = {
            "timestamp": time.time(),
            "agent":     agent,
            "action":    action,
        }
        if data is not None:
            step["data"] = data

        self.steps.append(step)

    def log_react_step(
        self,
        iteration: int,
        phase:     str,   # "reason" | "act" | "observe"
        details:   Any = None
    ) -> None:
        """Shortcut para registrar pasos del bucle ReAct."""
        self.log(
            agent  = "orchestrator",
            action = f"react:{phase}:iter{iteration}",
            data   = details
        )

    # ------------------------------------------------------------------ #
    # Persistencia                                                         #
    # ------------------------------------------------------------------ #

    def save(self) -> Dict:
        """
        Guarda el trace actual en formato JSONL con rotación automática.
        Devuelve el objeto trace serializado.
        """
        trace = {
            "trace_id":  self.trace_id,
            "timestamp": time.time(),
            "steps":     self.steps
        }

        # Rotar si el archivo supera el límite
        self._rotate_if_needed()

        try:
            with open(self._trace_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            logger.error(f"[Tracer] Error al guardar trace: {e}")

        return trace

    def clear(self) -> None:
        """Resetea el trace actual (útil entre tareas)."""
        self.steps = []
        self.trace_id = str(uuid.uuid4())

    # ------------------------------------------------------------------ #
    # Lectura                                                              #
    # ------------------------------------------------------------------ #

    def load_recent(self, n: int = 10) -> List[Dict]:
        """Lee los últimos N traces del archivo JSONL."""
        if not self._trace_file.exists():
            return []

        lines = []
        try:
            with open(self._trace_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)
        except Exception as e:
            logger.error(f"[Tracer] Error al leer traces: {e}")
            return []

        # Devolver los últimos N
        recent_lines = lines[-n:]
        result = []
        for line in recent_lines:
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return result

    def get_stats(self) -> Dict:
        """Estadísticas del archivo de traces actual."""
        if not self._trace_file.exists():
            return {"file": str(self._trace_file), "size_mb": 0, "traces": 0}

        size_bytes = self._trace_file.stat().st_size
        traces     = self.load_recent(n=10_000)  # contar todos

        return {
            "file":     str(self._trace_file),
            "size_mb":  round(size_bytes / (1024 * 1024), 2),
            "traces":   len(traces),
        }

    # ------------------------------------------------------------------ #
    # Rotación                                                             #
    # ------------------------------------------------------------------ #

    def _rotate_if_needed(self) -> None:
        """
        Rota el archivo si supera MAX_FILE_SIZE_MB.
        Mantiene solo MAX_ROTATED_FILES archivos históricos.
        """
        if not self._trace_file.exists():
            return

        if self._trace_file.stat().st_size < self.max_bytes:
            return

        # Renombrar archivo actual con timestamp
        timestamp   = int(time.time())
        rotated     = self.log_dir / f"traces_{timestamp}.jsonl"
        self._trace_file.rename(rotated)

        logger.info(f"[Tracer] Archivo rotado → {rotated.name}")

        # Limpiar archivos históricos si hay demasiados
        self._cleanup_old_files()

    def _cleanup_old_files(self) -> None:
        """Elimina archivos rotados más antiguos si superan el límite."""
        pattern  = sorted(self.log_dir.glob("traces_*.jsonl"))
        to_delete = pattern[:-self.max_rotated] if len(pattern) > self.max_rotated else []

        for old_file in to_delete:
            try:
                old_file.unlink()
                logger.debug(f"[Tracer] Eliminado archivo histórico: {old_file.name}")
            except Exception as e:
                logger.warning(f"[Tracer] No se pudo eliminar {old_file.name}: {e}")