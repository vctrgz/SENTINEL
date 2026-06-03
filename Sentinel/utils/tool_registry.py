import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from utils.logger import logger
from utils.os_context import build_shell_command, detect_os_context, needs_native_shell, split_command


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class Tool:
    name: str
    description: str
    parameters: List[ToolParameter]
    handler: Callable
    category: str = "general"

    def to_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": {
                "type": "object",
                "properties": {
                    p.name: {
                        "type": p.type,
                        "description": p.description,
                        **({"default": p.default} if p.default is not None else {}),
                    }
                    for p in self.parameters
                },
                "required": [p.name for p in self.parameters if p.required],
            },
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool
        logger.debug(f"[ToolRegistry] Registrada: {tool.name}")

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def list_schemas(self) -> List[dict]:
        return [t.to_schema() for t in self._tools.values()]

    def schemas_as_prompt(self) -> str:
        lines = ["## Available Tools\n"]
        for tool in self._tools.values():
            lines.append(f"### {tool.name}")
            lines.append(f"**Descripcion**: {tool.description}")
            lines.append(f"**Categoria**: {tool.category}")
            lines.append("**Parametros**:")
            for p in tool.parameters:
                req = "requerido" if p.required else f"opcional (default: {p.default})"
                lines.append(f"  - `{p.name}` ({p.type}, {req}): {p.description}")
            lines.append("")
        return "\n".join(lines)

    def execute(self, name: str, params: dict) -> dict:
        tool = self.get(name)
        if not tool:
            return {
                "tool": name,
                "success": False,
                "error": f"Herramienta '{name}' no registrada. Disponibles: {self.list_tools()}",
            }

        missing = [p.name for p in tool.parameters if p.required and p.name not in params]
        if missing:
            return {
                "tool": name,
                "success": False,
                "error": f"Parametros requeridos faltantes: {missing}",
            }

        try:
            result = tool.handler(**params)
            return {"tool": name, "success": True, "result": result}
        except Exception as exc:
            logger.error(f"[ToolRegistry] Error en {name}: {exc}")
            return {"tool": name, "success": False, "error": str(exc)}


def _bash_handler(command: str, timeout: int = 30) -> dict:
    try:
        os_context = detect_os_context()
        args = build_shell_command(command, os_context) if needs_native_shell(command, os_context) else split_command(command, os_context)
        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=timeout)
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Timeout ({timeout}s)", "returncode": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": f"Comando no encontrado: {command.split()[0]}", "returncode": 127}


def _read_file_handler(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _write_file_handler(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Archivo escrito: {path} ({len(content)} chars)"


def _str_replace_handler(path: str, old_str: str, new_str: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Archivo no encontrado: {path}")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old_str not in content:
        raise ValueError(f"El texto a reemplazar no se encontro en {path}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.replace(old_str, new_str, 1))
    return f"Reemplazo aplicado en {path}"


def _search_code_handler(pattern: str, path: str = ".", case_sensitive: bool = True) -> str:
    try:
        os_context = detect_os_context()
        if shutil.which("rg"):
            args = ["rg", "-n"]
            if not case_sensitive:
                args.append("-i")
            args.extend([pattern, path])
        elif os_context["is_windows"]:
            escaped_pattern = pattern.replace("'", "''")
            escaped_path = path.replace("'", "''")
            args = build_shell_command(
                f"Get-ChildItem -Path '{escaped_path}' -Recurse -File | Select-String -Pattern '{escaped_pattern}'",
                os_context,
            )
        else:
            args = ["grep", "-rn"]
            if not case_sensitive:
                args.append("-i")
            args.extend([pattern, path])

        result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() or "(Sin resultados)"
    except Exception as exc:
        return f"Error en busqueda: {exc}"


def _list_directory_handler(path: str = ".", show_hidden: bool = False) -> str:
    try:
        entries = os.listdir(path)
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        entries.sort()
        result = []
        for entry in entries:
            full = os.path.join(path, entry)
            prefix = "[D]" if os.path.isdir(full) else "[F]"
            result.append(f"{prefix} {entry}")
        return "\n".join(result) if result else "(Directorio vacio)"
    except PermissionError as exc:
        raise PermissionError(f"Sin permisos para leer: {path}") from exc


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()

    registry.register(Tool(
        name="bash",
        description="Ejecuta un comando del shell nativo del sistema",
        category="shell",
        parameters=[
            ToolParameter("command", "string", "Comando shell a ejecutar"),
            ToolParameter("timeout", "integer", "Timeout en segundos", required=False, default=30),
        ],
        handler=_bash_handler,
    ))

    registry.register(Tool(
        name="read_file",
        description="Lee el contenido completo de un archivo",
        category="filesystem",
        parameters=[ToolParameter("path", "string", "Ruta al archivo a leer")],
        handler=_read_file_handler,
    ))

    registry.register(Tool(
        name="write_file",
        description="Escribe o sobreescribe un archivo con el contenido dado",
        category="filesystem",
        parameters=[
            ToolParameter("path", "string", "Ruta del archivo a escribir"),
            ToolParameter("content", "string", "Contenido a escribir"),
        ],
        handler=_write_file_handler,
    ))

    registry.register(Tool(
        name="str_replace",
        description="Reemplaza una cadena exacta en un archivo (compatible con SWE-bench)",
        category="edit",
        parameters=[
            ToolParameter("path", "string", "Ruta del archivo"),
            ToolParameter("old_str", "string", "Texto exacto a reemplazar"),
            ToolParameter("new_str", "string", "Nuevo texto"),
        ],
        handler=_str_replace_handler,
    ))

    registry.register(Tool(
        name="search_code",
        description="Busca un patron de texto en archivos de codigo",
        category="search",
        parameters=[
            ToolParameter("pattern", "string", "Patron a buscar"),
            ToolParameter("path", "string", "Directorio de busqueda", required=False, default="."),
            ToolParameter("case_sensitive", "boolean", "Busqueda sensible a mayusculas", required=False, default=True),
        ],
        handler=_search_code_handler,
    ))

    registry.register(Tool(
        name="list_directory",
        description="Lista el contenido de un directorio",
        category="filesystem",
        parameters=[
            ToolParameter("path", "string", "Ruta del directorio", required=False, default="."),
            ToolParameter("show_hidden", "boolean", "Mostrar archivos ocultos", required=False, default=False),
        ],
        handler=_list_directory_handler,
    ))

    return registry


DEFAULT_REGISTRY = build_default_registry()
