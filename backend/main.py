"""FVpn Backend — FastAPI Application"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import unquote_plus

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal, init_db
from app.api import auth, users, nodes, protocols, subscriptions, stats, system
from app.core.monitor import MonitorService
from app.core.self_heal import SelfHealService
from app.core.security import decode_token
from app.models import User

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("uniproxy")


class SecretURLFilter(logging.Filter):
    """Redact bearer URLs before Uvicorn or application handlers format them."""

    _query = re.compile(r"""([?&]([^=&\s"'<>]+)=)[^&#\s"'<>]*""")
    _path = re.compile(r"""(/(?:api/subscriptions/(?:fetch|qr|info)|s)/)[^/?#\s"'<>]+""")

    @classmethod
    def redact(cls, value: str) -> str:
        value = cls._query.sub(
            lambda match: match[1] + "[REDACTED]"
            if unquote_plus(match[2]).lower() in {"token", "access_token"}
            else match[0],
            value,
        )
        return cls._path.sub(r"\1[REDACTED]", value)

    def filter(self, record: logging.LogRecord) -> bool:
        # Uvicorn's AccessFormatter unpacks these five arguments, so keep their
        # sanitized shape. Other messages are rendered once and drop raw args.
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            record.msg = self.redact(str(record.msg))
            record.args = tuple(self.redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        else:
            record.msg = self.redact(record.getMessage())
            record.args = ()
        if record.exc_info:
            record.exc_text = self.redact(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self.redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self.redact(record.stack_info)
        return True


_secret_url_filter = SecretURLFilter()
for _logger_name in ("uvicorn.error", "uvicorn.access", "uniproxy"):
    logging.getLogger(_logger_name).addFilter(_secret_url_filter)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_secret_url_filter)


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
    username = decode_token(token) if token else None
    if not isinstance(username, str) or not username:
        await websocket.close(code=4001)
        return
    async with SessionLocal() as db:
        authorized = (
            await db.execute(
                select(User.id).where(
                    User.username == username,
                    User.is_active.is_(True),
                    User.is_admin.is_(True),
                )
            )
        ).scalar_one_or_none()
    if authorized is None:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_manager.disconnect(websocket)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
