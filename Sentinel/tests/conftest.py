"""
conftest.py — Configuración global de pytest para SentinelAI.

Define fixtures compartidas y ajusta el PYTHONPATH para que los imports
funcionen independientemente de desde dónde se lance pytest.
"""

import sys
import os
import pytest

# Añadir la raíz del proyecto al path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ------------------------------------------------------------------ #
# Fixtures compartidos                                                 #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session")
def project_root():
    """Ruta raíz del proyecto."""
    return ROOT


@pytest.fixture
def temp_workspace(tmp_path):
    """Directorio temporal con estructura básica para tests de archivos."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def sample_task():
    """Tarea de ejemplo para tests que necesitan un objeto task."""
    return {
        "task_id":   "test-task-001",
        "objective": "listar archivos del directorio actual",
        "constraints": [],
        "priority":  "low",
        "context": {
            "history":        [],
            "errors":         [],
            "attempt":        1,
            "memory_summary": "No hay episodios previos."
        }
    }


@pytest.fixture
def sample_plan():
    """Plan de ejemplo con dos tareas paralelas."""
    return {
        "tasks": [
            {
                "id":          1,
                "description": "Verificar directorio actual",
                "depends_on":  [],
                "mode":        "parallel"
            },
            {
                "id":          2,
                "description": "Listar archivos",
                "depends_on":  [1],
                "mode":        "sequential"
            }
        ]
    }