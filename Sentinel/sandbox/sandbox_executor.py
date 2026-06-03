import os
import subprocess
import shutil
from typing import Optional

from agents.executors.base_executor import BaseExecutor
from app.config import Config
from utils.logger import logger
from utils.os_context import build_shell_command, detect_os_context, needs_native_shell, split_command


class SandboxExecutor(BaseExecutor):
    DEFAULT_IMAGE = "python:3.11-slim"

    def __init__(self, image: Optional[str] = None, workspace: Optional[str] = None):
        self.image = image or self.DEFAULT_IMAGE
        self.workspace = workspace or Config.SANDBOX_PATH
        self._docker_ok = self._check_docker()

        if self._docker_ok:
            logger.info(f"[SandboxExecutor] Modo Docker activo (imagen: {self.image})")
        else:
            logger.warning(
                "[SandboxExecutor] Docker no disponible, usando fallback restringido. "
                "Para aislamiento real instala Docker y asegurate de que el daemon este corriendo."
            )

    def execute(self, cmd: str) -> dict:
        if Config.SANDBOX_MODE and self._docker_ok:
            return self._execute_docker(cmd)
        return self._execute_restricted(cmd)

    def _execute_docker(self, cmd: str) -> dict:
        docker_cmd = [
            "docker", "run",
            "--rm",
            "--network=none",
            "--memory=512m",
            "--memory-swap=512m",
            "--cpus=1.0",
            "--read-only",
            "--tmpfs=/tmp:size=100m",
            f"--volume={self.workspace}:/workspace:rw",
            "--workdir=/workspace",
            "--user=nobody",
            self.image,
            "sh", "-lc", cmd,
        ]

        try:
            result = subprocess.run(
                docker_cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
            )
            return {
                "command": cmd,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "sandbox": "docker",
            }
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "kill", "--signal=SIGKILL"], capture_output=True)
            return {
                "command": cmd,
                "stdout": "",
                "stderr": f"Docker timeout tras {Config.TIMEOUT}s",
                "returncode": -1,
                "sandbox": "docker",
            }
        except Exception as exc:
            logger.error(f"[SandboxExecutor][Docker] Error: {exc}")
            return self._execute_restricted(cmd)

    def _execute_restricted(self, cmd: str) -> dict:
        os_context = detect_os_context()
        safe_path = os.environ.get("PATH", "") if os_context["is_windows"] else "/usr/bin:/bin:/usr/local/bin:/usr/sbin:/sbin"
        sandbox_env = dict(os.environ)
        sandbox_env["PATH"] = safe_path

        try:
            args = build_shell_command(cmd, os_context) if needs_native_shell(cmd, os_context) else split_command(cmd, os_context)
        except ValueError as exc:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": str(exc),
                "returncode": -1,
                "sandbox": "restricted",
            }

        try:
            result = subprocess.run(
                args,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
                env=sandbox_env,
            )
            return {
                "command": cmd,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
                "sandbox": "restricted",
            }
        except subprocess.TimeoutExpired:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": f"Timeout tras {Config.TIMEOUT}s",
                "returncode": -1,
                "sandbox": "restricted",
            }
        except FileNotFoundError:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": f"Comando no encontrado: '{args[0] if args else cmd}'",
                "returncode": 127,
                "sandbox": "restricted",
            }
        except Exception as exc:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": str(exc),
                "returncode": -1,
                "sandbox": "restricted",
            }

    @staticmethod
    def _check_docker() -> bool:
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
