"""
app/server.py

Adds sudo password collection to the SSE flow:
  - The event_stream() generator polls SudoManager.is_waiting_for_password()
    and emits a "needs_sudo" event when an executor thread is blocked waiting.
  - POST /sudo-auth  - receives the password from the browser modal and
    unblocks the waiting executor thread.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from agents.wazuh.agent import WazuhAgent
from app.config import Config
from core.orchestrator import Orchestrator
from utils.input_validator import InputValidator
from utils.llm_client import MultiProviderLLMClient
from utils.logger import logger
from utils.runtime_tracer import get_tracer

app = FastAPI(
    title="SentinelAI",
    description="Agente de ciberseguridad con arquitectura multiagente",
    version="2.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
GUI_DIR = PROJECT_ROOT / "sentinel_GUI"

app.mount("/css", StaticFiles(directory=GUI_DIR / "css"), name="sentinel-gui-css")
app.mount("/js", StaticFiles(directory=GUI_DIR / "js"), name="sentinel-gui-js")

_orchestrator: Orchestrator | None = None
_validator = InputValidator()
_wazuh_agent: WazuhAgent | None = None
_last_alert_ids: set[str] = set()
_tracer = get_tracer()
_alert_queue: asyncio.Queue = asyncio.Queue()


def _get_wazuh_agent() -> WazuhAgent:
    global _wazuh_agent
    if _wazuh_agent is None:
        _wazuh_agent = WazuhAgent()
    return _wazuh_agent


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        logger.info("[Server] Inicializando Orchestrator...")
        _orchestrator = Orchestrator()
    return _orchestrator


async def _wazuh_monitor_loop() -> None:
    global _last_alert_ids
    agent = _get_wazuh_agent()

    if not agent.is_available():
        logger.warning("[WazuhMonitor] Wazuh no disponible; monitor deshabilitado.")
        return

    logger.info(f"[WazuhMonitor] Iniciado. Intervalo: {Config.WAZUH_POLL_INTERVAL}s")

    while True:
        try:
            result = agent.proactive_check()
            if result["has_critical"]:
                new_alerts = [
                    alert for alert in result["alerts"]
                    if alert.get("id") and alert["id"] not in _last_alert_ids
                ]
                if new_alerts:
                    _last_alert_ids.update(alert["id"] for alert in new_alerts if alert.get("id"))
                    if len(_last_alert_ids) > 2000:
                        _last_alert_ids = set(list(_last_alert_ids)[-1000:])

                    await _alert_queue.put({
                        "type": "wazuh_alert",
                        "count": len(new_alerts),
                        "summary": result["summary"],
                        "alerts": new_alerts[:5],
                    })
                    logger.info(f"[WazuhMonitor] {len(new_alerts)} alertas nuevas encoladas.")
        except Exception as exc:
            logger.error(f"[WazuhMonitor] Error en ciclo: {exc}")

        await asyncio.sleep(Config.WAZUH_POLL_INTERVAL)


@app.on_event("startup")
async def _startup() -> None:
    warnings = Config.validate()
    for warning in warnings:
        logger.warning(f"[Config] {warning}")

    client = MultiProviderLLMClient()
    models = client.list_models()
    if models:
        logger.info(f"[Server] LLM providers ready: {models}")
    else:
        logger.warning(
            "[Server] No LLM providers configured. "
            "Set OPENAI_API_KEY and/or OPENROUTER_API_KEY and/or HF_API_TOKEN and/or GROQ_API_KEY in .env"
        )

    if Config.WAZUH_HOST and Config.WAZUH_PASSWORD:
        asyncio.create_task(_wazuh_monitor_loop())
        logger.info("[Server] Wazuh monitor background task iniciado.")


@app.get("/wazuh/alerts/stream")
async def wazuh_alert_stream() -> StreamingResponse:
    async def _stream():
        yield "data: {\"type\": \"connected\", \"message\": \"Wazuh monitor activo\"}\n\n"
        while True:
            try:
                payload = await asyncio.wait_for(_alert_queue.get(), timeout=30.0)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"type\": \"ping\"}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/wazuh/status")
async def wazuh_status() -> JSONResponse:
    agent = _get_wazuh_agent()
    available = agent.is_available()
    return JSONResponse({
        "available": available,
        "host": Config.WAZUH_HOST or "no configurado",
        "monitor": Config.WAZUH_POLL_INTERVAL,
    })


@app.get("/", response_class=HTMLResponse)
async def serve_chatbot() -> HTMLResponse:
    html_path = GUI_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>sentinel_GUI/index.html no encontrado</h1>", status_code=404)
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> JSONResponse:
    client = MultiProviderLLMClient()
    models = client.list_models()
    return JSONResponse({
        "status": "ok" if models else "degraded",
        "models": models,
        "providers": {
            "openai": bool(Config.OPENAI_API_KEY),
            "openrouter": bool(Config.OPENROUTER_API_KEY),
            "huggingface": bool(Config.HF_API_TOKEN),
            "groq": bool(Config.GROQ_API_KEY),
        },
        "warnings": Config.validate(),
    })


@app.post("/sudo-auth")
async def sudo_auth(request: Request) -> JSONResponse:
    try:
        body = await request.json()
        password = body.get("password", "").strip()
        if not password:
            return JSONResponse({"error": "Contraseña vacía"}, status_code=400)

        from utils.sudo_manager import SudoManager

        SudoManager.get_instance().set_password(password)
        logger.info("[Server] /sudo-auth: password received, executor unblocked")
        return JSONResponse({"status": "ok"})
    except Exception as exc:
        logger.error(f"[Server] /sudo-auth error: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/chat")
async def chat(request: Request) -> Response:
    try:
        try:
            body = await request.json()
        except UnicodeDecodeError:
            raw_body = await request.body()
            body = json.loads(raw_body.decode("cp1252"))
        question = body.get("question", "").strip()
        if not question:
            return JSONResponse({"response": "Escribe tu consulta."}, status_code=400)

        validation = _validator.validate(question)
        if validation.blocked:
            return JSONResponse({"response": f"🚫 {validation.block_reason}"}, status_code=400)

        logger.info(f"[Server] /chat -> {question[:80]}")
        _tracer.log("system", "http_chat_request", {"question": question[:80]})
    except Exception as exc:
        return JSONResponse({"response": f"❌ Bad request: {exc}"}, status_code=400)

    clean_input = validation.clean_input

    async def event_stream():
        loop = asyncio.get_running_loop()
        orch = _get_orchestrator()

        from utils.sudo_manager import SudoManager

        sudo_mgr = SudoManager.get_instance()
        future = loop.run_in_executor(None, orch.handle_user_input, clean_input)

        ping_messages = [
            "🔍 Analizando solicitud...",
            "📋 Consultando modelo de lenguaje...",
            "🌐 Escaneando red...",
            "💻 Ejecutando comandos...",
            "📊 Procesando resultados...",
            "⏳ Los scans completos pueden tardar varios minutos...",
        ]
        ping_idx = 0
        sudo_prompt_active = False

        while not future.done():
            if sudo_mgr.is_waiting_for_password():
                if not sudo_prompt_active:
                    payload = json.dumps({
                        "type": "needs_sudo",
                        "message": (
                            "🔐 Se requieren permisos sudo para ejecutar este comando. "
                            "Por favor, introduce la contraseña del sistema:"
                        ),
                    })
                    yield f"data: {payload}\n\n"
                    sudo_prompt_active = True

                payload = json.dumps({
                    "type": "ping",
                    "message": "⏳ Esperando contraseña sudo...",
                })
                yield f"data: {payload}\n\n"
            else:
                sudo_prompt_active = False
                msg = ping_messages[ping_idx % len(ping_messages)]
                payload = json.dumps({"type": "ping", "message": msg})
                yield f"data: {payload}\n\n"
                ping_idx += 1

            try:
                await asyncio.wait_for(asyncio.shield(future), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

        try:
            response = await future
            payload = json.dumps({"type": "done", "response": response})
            yield f"data: {payload}\n\n"
        except Exception as exc:
            logger.error(f"[Server] Orchestrator error: {exc}", exc_info=True)
            payload = json.dumps({"type": "error", "response": f"❌ Error interno: {exc}"})
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.post("/config-model")
async def config_model(request: Request) -> JSONResponse:
    global _orchestrator
    try:
        body = await request.json()
        mode = body.get("mode", "").strip()
        if mode not in Config.MODELS:
            return JSONResponse(
                {"error": f"Modo inválido. Opciones: {list(Config.MODELS.keys())}"},
                status_code=400,
            )
        Config.DEFAULT_MODEL = mode
        _orchestrator = None
        logger.info(f"[Server] Modo -> {mode}")
        return JSONResponse({"status": "ok", "mode": mode})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
