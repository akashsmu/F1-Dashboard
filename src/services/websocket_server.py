"""
FastAPI WebSocket server that runs alongside the Arcade replay window.

- WS  /ws           — 25 fps frame broadcast to browser clients
- GET /session-info — static session metadata (circuit geometry, pitstops, team radio)
- GET /ui/*         — serves the frontend/ HTML dashboard (when directory exists)

The server runs on its own asyncio event loop in a daemon thread.
Arcade calls broadcast() from its sync on_update; we schedule the send onto the
server loop via asyncio.run_coroutine_threadsafe.
"""

import asyncio
import json
import os
import threading

try:
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False

# ── module-level state (all websocket list operations happen on the asyncio loop) ──
_clients: "list[WebSocket]" = []
_session_info: dict = {}
_loop: "asyncio.AbstractEventLoop | None" = None
_server_ready = threading.Event()


def _make_app() -> "FastAPI":
    from contextlib import asynccontextmanager
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import JSONResponse
    from fastapi.staticfiles import StaticFiles

    @asynccontextmanager
    async def lifespan(app):
        _server_ready.set()
        yield

    app = FastAPI(lifespan=lifespan)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        _clients.append(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            if websocket in _clients:
                _clients.remove(websocket)

    @app.get("/session-info")
    async def get_session_info():
        return JSONResponse(_session_info)

    # Serve the HTML dashboard if the frontend/ directory exists
    frontend_dir = os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
    )
    if os.path.isdir(frontend_dir):
        app.mount("/ui", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


async def _send_all(message: str) -> None:
    dead: list = []
    for ws in list(_clients):
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _clients:
            _clients.remove(ws)


class F1WebSocketServer:
    """Drop-in companion to TelemetryStreamServer for browser WebSocket clients."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self._thread: "threading.Thread | None" = None

    def start(self) -> None:
        if not _FASTAPI_AVAILABLE:
            print("FastAPI/uvicorn not installed — WebSocket server disabled. "
                  "Run: pip install fastapi 'uvicorn[standard]'")
            return

        app = _make_app()

        def _run() -> None:
            global _loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _loop = loop
            config = uvicorn.Config(
                app,
                host=self.host,
                port=self.port,
                log_level="warning",
                loop="none",
            )
            server = uvicorn.Server(config)
            loop.run_until_complete(server.serve())

        self._thread = threading.Thread(target=_run, daemon=True, name="f1-ws-server")
        self._thread.start()
        # Wait until the FastAPI lifespan has fired (server is accepting connections)
        if not _server_ready.wait(timeout=8.0):
            print("Warning: WebSocket server did not start within 8 s")
        else:
            print(f"F1 WebSocket server ready at ws://{self.host}:{self.port}/ws")
            print(f"  Dashboard: http://localhost:{self.port}/ui")
            print(f"  Session info: http://localhost:{self.port}/session-info")

    def set_session_info(self, info: dict) -> None:
        """Store static session metadata served by GET /session-info."""
        global _session_info
        _session_info = info

    def broadcast(self, data: dict) -> None:
        """Broadcast a frame dict to all connected WebSocket clients (thread-safe)."""
        if _loop is None or not _loop.is_running():
            return
        try:
            message = json.dumps(data)
        except (TypeError, ValueError):
            return
        asyncio.run_coroutine_threadsafe(_send_all(message), _loop)

    def stop(self) -> None:
        # Daemon thread exits with the process; nothing explicit needed.
        pass
