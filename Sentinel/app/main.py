import json
from core.orchestrator import Orchestrator
from utils.logger import setup_logger, logger
from utils.input_validator import InputValidator
from utils.ollama_client import OllamaClient
from app.config import Config

logger = setup_logger()


def _startup_checks() -> bool:
    """
    Valida la configuración y la conectividad antes de arrancar.
    Devuelve True si el sistema está listo.
    """
    print("🔍 Verificando configuración...\n")

    # Validar Config
    warnings = Config.validate()
    for w in warnings:
        print(f"  ⚠️  {w}")

    # Verificar Ollama
    client = OllamaClient(Config.DEFAULT_MODEL)
    print(f"  🔗 Conectando con Ollama en {Config.OLLAMA_BASE_URL}...")

    if not client.is_available():
        print(
            f"\n  ❌ No se puede conectar con Ollama.\n"
            f"     Verifica que el servidor esté corriendo y que\n"
            f"     OLLAMA_HOST={Config.OLLAMA_HOST} sea correcto en .env\n"
        )
        return False

    models = client.list_models()
    current_model = Config.MODELS.get(Config.DEFAULT_MODEL, Config.DEFAULT_MODEL)
    model_ok = any(current_model.split(":")[0] in m for m in models)

    print(f"  ✅ Ollama conectado. Modelos disponibles: {len(models)}")

    if not model_ok:
        print(
            f"  ⚠️  Modelo '{current_model}' no encontrado en Ollama.\n"
            f"     Modelos disponibles: {models}\n"
            f"     Descárgalo con: ollama pull {current_model}\n"
        )
        return False

    print(f"  ✅ Modelo activo: {current_model} (modo: {Config.DEFAULT_MODEL})\n")
    return True


def run():
    print("🧠 SentinelAI iniciado.\n")

    if not _startup_checks():
        print("❌ El sistema no pudo arrancar correctamente. Revisa la configuración.")
        return

    orchestrator = Orchestrator()
    validator    = InputValidator()   # Alerta #4

    print("Escribe tu consulta o 'exit' para salir.\n")

    while True:
        try:
            user_input = input(">> ").strip()

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "salir"):
                print("👋 Cerrando SentinelAI...")
                break

            # Alerta #4: validar y sanitizar el input
            validation = validator.validate(user_input)

            if validation.blocked:
                print(f"\n🚫 {validation.block_reason}\n")
                continue

            for w in validation.warnings:
                print(f"  ⚠️  {w}")

            clean_input = validation.clean_input

            # Procesar con el orquestador
            result = orchestrator.handle_user_input(clean_input)

            print("\n📤 Resultado:\n")
            print(result)
            print("\n" + "─" * 50 + "\n")

        except KeyboardInterrupt:
            print("\n👋 Interrumpido por el usuario.")
            break

        except Exception as e:
            logger.error(f"Error en main loop: {e}", exc_info=True)
            print(f"❌ Error inesperado: {e}\n")


if __name__ == "__main__":
    run()