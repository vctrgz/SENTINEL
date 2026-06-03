"""
Cross-platform shell executor.
"""

from __future__ import annotations

import subprocess
import time

from agents.executors.base_executor import BaseExecutor
from app.config import Config
from utils.logger import logger
from utils.os_context import build_shell_command, detect_os_context, needs_native_shell, split_command
from utils.runtime_tracer import get_tracer


def _is_sudo_cmd(cmd: str) -> bool:
    return cmd.lstrip().startswith("sudo ")


class ShellExecutor(BaseExecutor):
    def __init__(self) -> None:
        self._tracer = get_tracer()

    def execute(self, cmd: str) -> dict:
        if not cmd or not cmd.strip():
            return {"command": cmd, "stdout": "", "stderr": "Comando vacio", "returncode": -1}

        if _is_sudo_cmd(cmd):
            return self._execute_sudo(cmd)

        return self._execute_plain(cmd)

    def _execute_sudo(self, cmd: str) -> dict:
        if detect_os_context()["is_windows"]:
            return {
                "command": cmd,
                "stdout": "",
                "stderr": "sudo no esta soportado en Windows. Genera un comando nativo para este SO.",
                "returncode": -1,
            }

        from utils.sudo_manager import SudoManager

        sudo_mgr = SudoManager.get_instance()

        if not sudo_mgr.sudo_needs_password():
            return self._run(cmd)

        if not sudo_mgr.has_password():
            logger.info(f"[ShellExecutor] Sudo password needed for: {cmd[:60]!r}")
            got = sudo_mgr.request_password(timeout=180.0)
            if not got:
                return {
                    "command": cmd,
                    "stdout": "",
                    "stderr": (
                        "No se recibio la contrasena sudo (timeout 180 s). "
                        "Intenta de nuevo e introduce la contrasena cuando se solicite."
                    ),
                    "returncode": -1,
                }

        return self._run_with_password(cmd, sudo_mgr)

    def _run_with_password(self, cmd: str, sudo_mgr) -> dict:
        from utils.sudo_manager import SudoManager

        sudo_s_cmd = SudoManager.inject_sudo_s(cmd)
        stdin_data = sudo_mgr.stdin_payload()

        self._tracer.log("shell", f"run(sudo-S): {sudo_s_cmd[:90]}")
        t0 = time.monotonic()

        try:
            result = subprocess.run(
                sudo_s_cmd,
                shell=True,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
            )
            duration = time.monotonic() - t0
            cleaned_stderr = SudoManager.clean_sudo_stderr(result.stderr)

            if SudoManager.is_wrong_password_error(result.stderr):
                logger.warning("[ShellExecutor] Wrong sudo password, clearing cache")
                sudo_mgr.clear_password()
                return {
                    "command": cmd,
                    "stdout": "",
                    "stderr": "Contrasena sudo incorrecta. Intentalo de nuevo.",
                    "returncode": -1,
                    "_sudo_wrong_password": True,
                }

            if SudoManager.is_unsupported_stdin_flag_error(result.stderr):
                logger.warning("[ShellExecutor] sudo does not support -S; retrying original command")
                return self._run(cmd)

            self._tracer.log_command(
                cmd,
                "shell-sudo",
                result.returncode,
                len(result.stdout),
                cleaned_stderr[:200],
                duration,
            )
            return {
                "command": cmd,
                "stdout": result.stdout.strip(),
                "stderr": cleaned_stderr.strip(),
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            msg = f"Timeout: comando supero {Config.TIMEOUT}s"
            logger.warning(f"[ShellExecutor] {msg}: {cmd}")
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": -1}
        except Exception as exc:
            logger.error(f"[ShellExecutor] sudo error: {exc}")
            return {"command": cmd, "stdout": "", "stderr": str(exc), "returncode": -1}

    def _execute_plain(self, cmd: str) -> dict:
        os_context = detect_os_context()
        use_shell = needs_native_shell(cmd, os_context)
        self._tracer.log(
            "shell",
            f"run: {cmd[:90]}",
            {"shell_mode": use_shell, "shell_kind": os_context.get("shell_kind")},
        )
        t0 = time.monotonic()

        try:
            if use_shell:
                run_cmd = build_shell_command(cmd, os_context)
            else:
                try:
                    run_cmd = split_command(cmd, os_context)
                except ValueError as exc:
                    return {
                        "command": cmd,
                        "stdout": "",
                        "stderr": f"Sintaxis invalida: {exc}",
                        "returncode": -1,
                    }

            if not run_cmd:
                return {"command": cmd, "stdout": "", "stderr": "Comando vacio", "returncode": -1}

            result = subprocess.run(
                run_cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=Config.TIMEOUT,
            )

            duration = time.monotonic() - t0
            self._tracer.log_command(
                cmd,
                "shell",
                result.returncode,
                len(result.stdout),
                result.stderr.strip()[:200],
                duration,
            )
            return {
                "command": cmd,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            msg = f"Timeout: comando supero {Config.TIMEOUT}s"
            logger.warning(f"[ShellExecutor] {msg}: {cmd}")
            self._tracer.log_command(cmd, "shell", -1, 0, msg, time.monotonic() - t0)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": -1}
        except FileNotFoundError:
            base = (cmd.split() or [cmd])[0]
            msg = f"Comando no encontrado: '{base}'"
            self._tracer.log_command(cmd, "shell", 127, 0, msg)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": 127}
        except PermissionError:
            base = (cmd.split() or [cmd])[0]
            msg = f"Permiso denegado: '{base}'"
            self._tracer.log_command(cmd, "shell", 126, 0, msg)
            return {"command": cmd, "stdout": "", "stderr": msg, "returncode": 126}
        except Exception as exc:
            logger.error(f"[ShellExecutor] Error inesperado: {exc}")
            self._tracer.log_command(cmd, "shell", -1, 0, str(exc))
            return {"command": cmd, "stdout": "", "stderr": str(exc), "returncode": -1}

    def _run(self, cmd: str) -> dict:
        return self._execute_plain(cmd)
