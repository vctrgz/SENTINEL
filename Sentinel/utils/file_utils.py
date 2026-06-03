import os


def load_file(path: str) -> str:
    """
    Carga el contenido de un archivo de texto.
    Módulo independiente para evitar imports circulares entre
    prompt_loader y skill_loader.
    """
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()