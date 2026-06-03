import platform
import shutil
import subprocess

from utils.logger import logger
from utils.os_context import build_install_command, detect_os_context, detect_package_manager


class ToolManager:
    """
    Instala herramientas con el gestor de paquetes adecuado para el SO actual.
    """

    def __init__(self):
        self.os_context = detect_os_context()
        self.package_manager = detect_package_manager(self.os_context["family"])
        self.os_info = self.os_context["system"]

        if self.package_manager:
            logger.info(
                f"[ToolManager] OS: {self.os_info} | "
                f"Gestor: {self.package_manager} | "
                f"shell: {self.os_context.get('shell_kind')}"
            )
        else:
            logger.warning(
                "[ToolManager] No se detecto ningun gestor de paquetes. "
                "La instalacion automatica no estara disponible."
            )

    def is_installed(self, tool: str) -> bool:
        return shutil.which(tool) is not None

    def ensure_tool(self, tool: str) -> dict:
        if self.is_installed(tool):
            logger.debug(f"[ToolManager] '{tool}' ya esta instalado.")
            return {"tool": tool, "status": "already_installed"}
        return self.install_tool(tool)

    def install_tool(self, tool_name: str) -> dict:
        if not self.package_manager:
            return {
                "tool": tool_name,
                "installed": False,
                "error": (
                    f"No se encontro gestor de paquetes en {self.os_info}. "
                    "Instala la herramienta manualmente."
                ),
            }

        cmd = build_install_command(tool_name, self.os_context)
        if not cmd:
            return {
                "tool": tool_name,
                "installed": False,
                "error": f"No se pudo construir el comando de instalacion para {self.os_info}.",
            }

        logger.info(f"[ToolManager] Instalando '{tool_name}' con: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            success = result.returncode == 0

            if success:
                logger.info(f"[ToolManager] '{tool_name}' instalado correctamente.")
            else:
                logger.warning(
                    f"[ToolManager] Instalacion de '{tool_name}' fallo "
                    f"(codigo {result.returncode}): {result.stderr[:200]}"
                )

            return {
                "tool": tool_name,
                "installed": success,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "command": " ".join(cmd),
            }
        except subprocess.TimeoutExpired:
            return {
                "tool": tool_name,
                "installed": False,
                "error": "Timeout durante la instalacion (>120s)",
            }
        except FileNotFoundError:
            return {
                "tool": tool_name,
                "installed": False,
                "error": f"Gestor '{self.package_manager}' no encontrado en PATH",
            }
        except Exception as exc:
            logger.error(f"[ToolManager] Error inesperado: {exc}")
            return {
                "tool": tool_name,
                "installed": False,
                "error": str(exc),
            }

    def get_system_info(self) -> dict:
        return {
            "os": self.os_info,
            "platform": self.os_context["platform"],
            "package_manager": self.package_manager or "none",
            "shell": self.os_context.get("shell"),
            "shell_kind": self.os_context.get("shell_kind"),
            "python": platform.python_version(),
        }
