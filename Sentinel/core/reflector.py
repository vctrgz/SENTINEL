from typing import Optional
from agents.reflector.agent import ReflectorAgent


class Reflector:

    def __init__(self) -> None:
        self.agent = ReflectorAgent()

    def run(
        self,
        execution_results: list,
        task: Optional[dict] = None,
    ) -> dict:
        return self.agent.run(execution_results, task or {})

    def analyze(self, execution_results: list, task: dict) -> dict:
        """Alias de run() para compatibilidad con código legado."""
        return self.run(execution_results, task)