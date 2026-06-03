import time
from typing import Any, Dict, List, Optional


class WorkingMemory:
    """
    Memoria de trabajo: contexto de la tarea activa.
    Se resetea entre tareas. Contiene el estado vivo del ciclo ReAct actual.
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def clear(self) -> None:
        self._data.clear()

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._data)

    def update(self, data: Dict[str, Any]) -> None:
        self._data.update(data)


class EpisodicMemory:
    """
    Memoria episódica: historial de ejecuciones de la sesión.
    Persiste entre tareas dentro de la misma sesión. Permite al agente
    aprender de intentos previos y evitar repetir los mismos errores.
    """

    def __init__(self, max_episodes: int = 50):
        self._episodes: List[Dict[str, Any]] = []
        self.max_episodes = max_episodes

    def add(self, episode: Dict[str, Any]) -> None:
        episode.setdefault("timestamp", time.time())
        self._episodes.append(episode)
        if len(self._episodes) > self.max_episodes:
            self._episodes.pop(0)

    def get_recent(self, n: int = 5) -> List[Dict[str, Any]]:
        return self._episodes[-n:]

    def get_errors(self) -> List[Dict[str, Any]]:
        return [
            e for e in self._episodes
            if e.get("status") in ("error", "retry", "fatal")
        ]

    def get_successes(self) -> List[Dict[str, Any]]:
        return [
            e for e in self._episodes
            if e.get("status") == "success"
        ]

    def clear(self) -> None:
        self._episodes.clear()

    def to_context_string(self, n: int = 3) -> str:
        """Resumen compacto de los últimos N episodios para incluir en el prompt."""
        recent = self.get_recent(n)
        if not recent:
            return "No hay episodios previos en esta sesión."
        lines = []
        for ep in recent:
            status  = ep.get("status", "unknown")
            reason  = ep.get("reason", "")
            attempt = ep.get("attempt", "?")
            obj     = ep.get("objective", "")[:80]
            lines.append(f"  - Intento {attempt} [{status}]: {obj}. {reason}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._episodes)


class AgentMemory:
    """
    Sistema de memoria principal del agente.

    Siguiendo la arquitectura de IBM (AI Agent Memory):
    - working:  memoria de trabajo (tarea activa, se resetea)
    - episodic: historial de ejecuciones de la sesión
    """

    def __init__(self):
        self.working  = WorkingMemory()
        self.episodic = EpisodicMemory()

    def add_episode(self, data: Dict[str, Any]) -> None:
        """Registra un episodio completo de ejecución."""
        self.episodic.add(data)

    def reset_working(self) -> None:
        """Limpia la memoria de trabajo al comenzar una nueva tarea."""
        self.working.clear()

    def get_context_summary(self) -> str:
        """
        Devuelve un resumen del historial para incluir en el contexto
        de la siguiente iteración ReAct.
        """
        return self.episodic.to_context_string()

    def get_error_patterns(self) -> List[str]:
        """Extrae patrones de error de episodios anteriores."""
        errors = self.episodic.get_errors()
        return [e.get("reason", "") for e in errors if e.get("reason")]