"""
Arranque rapido de SentinelAI.

Servidor web:  python run.py
CLI:           python run.py --cli
"""

import asyncio
import os
import sys

from app.main import run
from app.server import app


class DebugServer:
    @staticmethod
    async def serve(host: str, port: int) -> None:
        import uvicorn

        class _ServerWithoutSignals(uvicorn.Server):
            def install_signal_handlers(self) -> None:
                return

        config = uvicorn.Config(app, host=host, port=port, reload=False)
        server = _ServerWithoutSignals(config)
        await server.serve()


if __name__ == "__main__":
    if "--cli" in sys.argv:
        run()
    else:
        import uvicorn

        debug_mode = sys.gettrace() is not None
        reload_enabled = os.getenv("UVICORN_RELOAD", "false").lower() == "true"
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))

        if debug_mode:
            # debugpy on Windows can emit SIGBREAK to child processes; if uvicorn
            # captures it, the server exits immediately after startup.
            asyncio.run(DebugServer.serve(host, port))
        else:
            uvicorn.run(
                "app.server:app",
                host=host,
                port=port,
                reload=reload_enabled,
            )
