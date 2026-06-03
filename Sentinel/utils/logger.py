import logging
import os


def setup_logger(name: str = "SentinelAI") -> logging.Logger:
    """Configura y devuelve el logger principal."""
    _logger = logging.getLogger(name)

    if _logger.handlers:
        return _logger  # evitar duplicados en reinicios

    _logger.setLevel(logging.DEBUG)

    os.makedirs("logs", exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    _logger.addHandler(console_handler)
    _logger.addHandler(file_handler)

    return _logger


# Instancia global — fix de debug.py que hacía 'from utils.logger import logger'
# antes fallaba porque solo existía setup_logger() pero no el símbolo 'logger'
logger = setup_logger()