"""UniProxy Backend — FastAPI Application"""

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

# WebSocket connection manager
class WSManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
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
monitor_service: MonitorService | None = None
self_heal_service: SelfHealService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor_service, self_heal_service

    logger.info(f"UniProxy v{settings.VERSION} starting...")
    await init_db()

    monitor_service = MonitorService(ws_manager)
    self_heal_service = SelfHealService()

    monitor_task  = asyncio.create_task(monitor_service.run())
    selfheal_task = asyncio.create_task(self_heal_service.run())

    yield

    monitor_task.cancel()
    selfheal_task.cancel()
    await asyncio.gather(monitor_task, selfheal_task, return_exceptions=True)
    logger.info("UniProxy shutdown complete")


app = FastAPI(
    title="UniProxy API",
    version=settings.VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Middleware
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
    """Real-time stats stream — authenticates via ?token=<jwt>"""
    from app.core.security import verify_token
    if not token or not verify_token(token):
        await websocket.close(code=4001)
        return
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()  # keep-alive ping
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
