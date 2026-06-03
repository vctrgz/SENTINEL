"""
setup_env.py - Crea el entorno virtual e instala dependencias.
Se ejecuta automaticamente al pulsar F5 en VSCode (preLaunchTask).

Mantiene el workflow actual, pero valida mejor venvs rotos o generados con
stubs no ejecutables (por ejemplo algunos paths de Windows Store), y los
reconstruye sin tocar nada si el entorno sigue sano.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from utils.os_context import candidate_host_python_commands


ROOT = Path(__file__).parent.resolve()
VENV = ROOT / "venv"
IS_WIN = os.name == "nt"

PYTHON_VENV = VENV / ("Scripts" if IS_WIN else "bin") / ("python.exe" if IS_WIN else "python")
REQS = Path(__file__).parent / "requirements.txt"


def run(cmd: list[str], desc: str = ""):
    display = " ".join(str(c) for c in cmd).replace(str(ROOT), "<root>")
    print(f"  $ {display}")
    result = subprocess.run([str(c) for c in cmd], capture_output=False)
    if result.returncode != 0:
        print(f"\nFallo: {desc or display}")
        sys.exit(result.returncode)


def _try_command(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(
            cmd + ["-c", "import sys; print(sys.executable)"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.returncode == 0
    except Exception:
        return False


def resolve_host_python() -> list[str]:
    candidates = candidate_host_python_commands()

    if os.name == "nt":
        preferred: list[list[str]] = []
        fallback: list[list[str]] = []
        for candidate in candidates:
            if candidate[:2] == ["py", "-3"] or candidate == ["py"]:
                preferred.append(candidate)
            else:
                fallback.append(candidate)
        candidates = preferred + fallback

    for candidate in candidates:
        if _try_command(candidate):
            return candidate
    return [sys.executable]


def recreate_venv(reason: str):
    print(f"  Entorno virtual invalido: {reason}")
    if VENV.exists():
        print(f"  Eliminando {VENV} ...")
        shutil.rmtree(VENV)
    print("  Recreando entorno virtual...")
    creator = resolve_host_python()
    run(creator + ["-m", "venv", str(VENV)], "recrear venv")
    print("  Entorno recreado\n")


def venv_is_healthy() -> tuple[bool, str]:
    if not PYTHON_VENV.exists():
        return False, f"no se encontro el interprete en {PYTHON_VENV}"

    cfg = VENV / "pyvenv.cfg"
    if cfg.exists():
        try:
            contents = cfg.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            return False, f"no se pudo leer {cfg.name}: {exc}"

        for line in contents.splitlines():
            if line.startswith("home = "):
                home = Path(line.split("=", 1)[1].strip())
                if not home.exists():
                    return False, f"pyvenv.cfg apunta a un Python inexistente: {home}"
                break

    try:
        result = subprocess.run(
            [str(PYTHON_VENV), "-c", "import sys,platform; print(sys.executable); print(platform.system())"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError as exc:
        return False, f"fallo al ejecutar el interprete del venv: {exc}"

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        return False, f"el interprete del venv no arranca correctamente: {stderr or result.returncode}"

    try:
        pip_check = subprocess.run(
            [str(PYTHON_VENV), "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except OSError as exc:
        return False, f"fallo al invocar pip del venv: {exc}"

    if pip_check.returncode != 0:
        return False, f"pip del venv no funciona: {(pip_check.stderr or '').strip()}"

    return True, ""


def main():
    print("\nSentinelAI - Setup del entorno\n")
    print(f"  Raiz del proyecto : {ROOT}")
    print(f"  Entorno virtual   : {VENV}")
    print(f"  Python del sistema: {sys.executable}\n")

    if not VENV.exists():
        print("Creando entorno virtual...")
        creator = resolve_host_python()
        run(creator + ["-m", "venv", str(VENV)], "crear venv")
        print("  Entorno creado\n")
    else:
        print("  Entorno ya existe\n")

    healthy, reason = venv_is_healthy()
    if not healthy:
        recreate_venv(reason)
        healthy, reason = venv_is_healthy()
        if not healthy:
            print(f"No se pudo validar el entorno virtual: {reason}")
            sys.exit(1)

    print("Actualizando pip...")
    run(
        [str(PYTHON_VENV), "-m", "pip", "install", "--upgrade", "pip", "-q"],
        "actualizar pip",
    )

    if REQS.exists():
        print(f"Instalando dependencias ({REQS.name})...")
        run(
            [str(PYTHON_VENV), "-m", "pip", "install", "-r", str(REQS), "-q"],
            "instalar requirements",
        )
        print("  Dependencias instaladas\n")
    else:
        print(f"  No se encontro {REQS} - saltando instalacion\n")

    print("Entorno listo. Arrancando servidor...\n")


if __name__ == "__main__":
    main()
