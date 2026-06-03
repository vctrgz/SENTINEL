from agents.planner.agent import PlannerAgent


class Planner:

    def __init__(self):
        self.agent = PlannerAgent()

    def run(self, task: dict) -> dict:
        return self.agent.run(task)