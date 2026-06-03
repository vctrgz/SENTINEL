from agents.supervisor.agent import SupervisorAgent


class Supervisor:

    def __init__(self):
        self.agent = SupervisorAgent()

    def run(
        self,
        commands: dict,
        objective: str = "",
        language_context: dict | None = None,
    ) -> dict:
        return self.agent.run(commands, objective, language_context=language_context)
