from agents.translator.agent import TranslatorAgent


class Translator:

    def __init__(self):
        self.agent = TranslatorAgent()

    def run(self, plan: dict, context: dict) -> dict:
        return self.agent.run(plan, context)