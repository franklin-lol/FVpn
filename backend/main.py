"""FVpn Backend — FastAPI Application"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import init_db
from app.api import auth, users, nodes, protocols, subscriptions, stats, system
from app.core.monitor import MonitorService
from app.core.self_heal import SelfHealService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("uniproxy")


class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.remove(ws)


ws_manager = WSManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"FVpn v{settings.VERSION} starting...")
    await init_db()

    monitor   = MonitorService(ws_manager)
    selfheal  = SelfHealService()

    mon_task  = asyncio.create_task(monitor.run())
    heal_task = asyncio.create_task(selfheal.run())

    yield

    mon_task.cancel()
    heal_task.cancel()
    await asyncio.gather(mon_task, heal_task, return_exceptions=True)
    logger.info("FVpn shutdown complete")


app = FastAPI(
    title="FVpn API",
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
    # CRITICAL: prevents 307 redirects (trailing-slash redirects break CSP
    # when uvicorn is behind nginx proxy — generates wrong scheme/port in Location)
    redirect_slashes=False,
)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,          prefix="/api/auth",          tags=["Auth"])
app.include_router(users.router,         prefix="/api/users",         tags=["Users"])
app.include_router(nodes.router,         prefix="/api/nodes",         tags=["Nodes"])
app.include_router(protocols.router,     prefix="/api/protocols",     tags=["Protocols"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Subscriptions"])
app.include_router(stats.router,         prefix="/api/stats",         tags=["Stats"])
app.include_router(system.router,        prefix="/api/system",        tags=["System"])


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}


@app.websocket("/ws/stats")
async def ws_stats(websocket: WebSocket, token: str | None = None):
    from app.core.security import verify_token
    if not token or not verify_token(token):
        await websocket.close(code=4001)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
