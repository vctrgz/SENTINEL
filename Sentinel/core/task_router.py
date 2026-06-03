from agents.executors.shell_executor import ShellExecutor
from utils.tool_registry import build_default_registry


class TaskRouter:
    def __init__(self):
        self.shell_executor = ShellExecutor()
        self.tool_registry = build_default_registry()

    def execute(self, commands: list) -> list:
        results = []

        for item in commands:
            if isinstance(item, dict) and item.get("kind") == "tool":
                tool_name = item.get("tool", "")
                params = item.get("params", {}) if isinstance(item.get("params"), dict) else {}
                result = self.tool_registry.execute(tool_name, params)
                result["kind"] = "tool"
                result["tool_name"] = tool_name
                result["params"] = params
                results.append(result)
                continue

            cmd = item.get("cmd", "") if isinstance(item, dict) else str(item)
            if not cmd or not str(cmd).strip():
                results.append(
                    {
                        "command": "",
                        "stdout": "",
                        "stderr": "Comando vacio o invalido",
                        "returncode": -1,
                    }
                )
                continue

            results.append(self.shell_executor.execute(str(cmd)))

        return results
