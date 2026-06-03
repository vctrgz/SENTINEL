from utils.logger import logger
import json


def debug_dump(title: str, data) -> None:
    """Vuelca datos estructurados en el log de debug."""
    try:
        serialized = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialized = str(data)
 
    logger.debug(f"[DEBUG] {title}\n{serialized}")
 
 
def debug_step(agent: str, step: str, data=None) -> None:
    """Registra un paso de ejecución de un agente para trazabilidad."""
    msg = f"[{agent}] {step}"
    if data is not None:
        try:
            msg += f"\n{json.dumps(data, indent=2, ensure_ascii=False, default=str)}"
        except (TypeError, ValueError):
            msg += f"\n{data}"
    logger.debug(msg)
 