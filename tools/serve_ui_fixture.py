"""Disposable browser fixture: real API/SQLite, synthetic data, no core control."""

import asyncio
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

scratch = tempfile.TemporaryDirectory(prefix="fvpn-ui-")
os.chdir(scratch.name)
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{scratch.name}/fixture.db",
    "JWT_SECRET": "fixture-only-secret-at-least-thirty-two-bytes",
    "MASTER_PASSWORD": "fixture-admin-password",
    "DOMAIN": "127.0.0.1", "PANEL_PORT": "4181",
})

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from app.core.security import async_hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.lib.config_generator import ProtocolConfig  # noqa: E402
from app.models import Node, Protocol, SetupState, Subscription, User  # noqa: E402


async def seed():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        admin = User(username="admin", hashed_password=await async_hash_password("fixture-admin-password"), is_admin=True)
        user = User(username="demo", hashed_password=await async_hash_password("fixture-user-password"))
        node = Node(name="Local server", host="fixture.invalid", meta={"local": True}, status="online", latency_ms=18)
        session.add_all([admin, user, node])
        await session.flush()
        session.add_all([
            Protocol(node_id=node.id, name="vless", port=443, config=ProtocolConfig.defaults("vless", 443, {})),
            Subscription(user_id=user.id, token="fixture-public-token", format="hiddify"),
            SetupState(id=1, required=os.getenv("FIXTURE_SETUP") == "1", password_changed=False, admin_user_id=admin.id),
        ])
        await session.commit()


asyncio.run(seed())


@asynccontextmanager
async def fixture_lifespan(_):
    yield


main.app.router.lifespan_context = fixture_lifespan


async def synthetic_apply(_node_id):
    return {"status": "applied", "fixture": True}


from app.core import config_writer  # noqa: E402
config_writer.sync_node_config = synthetic_apply


@main.app.middleware("http")
async def no_service_control(request, call_next):
    if request.url.path.startswith("/api/system/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Service control is disabled in the browser fixture"}, status_code=409)
    return await call_next(request)


main.app.mount("/assets", StaticFiles(directory="/ui/assets"), name="fixture-assets")


@main.app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str):
    if path.startswith(("api/", "ws/")):
        raise HTTPException(404)
    return FileResponse(Path("/ui/index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="0.0.0.0", port=4181, access_log=False, proxy_headers=False)
