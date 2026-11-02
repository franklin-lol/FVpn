"""Bot bearer tokens survive changing the seeded administrator password."""

import asyncio
import importlib.util
import time
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import auth
from app.config import settings
from app.core import security
from app.database import Base, get_db
from app.models import User


@pytest.fixture
def module(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ADMIN_IDS", "7")
    monkeypatch.setenv("JWT_SECRET", settings.JWT_SECRET)
    monkeypatch.setenv("BOT_API_USER", "admin")
    path = Path(__file__).resolve().parents[1] / "bot" / "bot.py"
    spec = importlib.util.spec_from_file_location("bot_token_fixture", path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_bot_token_is_standard_hs256_with_ten_minute_lifetime_and_no_password_login(module, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("shared JWT authentication must not log in with stale seeded password")

    monkeypatch.setattr(module.httpx, "AsyncClient", forbidden)
    token = asyncio.run(module.get_token())
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "admin"
    assert claims["exp"] - claims["iat"] == 600
    assert abs(claims["iat"] - time.time()) < 2


def test_password_fallback_when_shared_secret_absent(module, monkeypatch):
    monkeypatch.setattr(module, "JWT_SECRET", "", raising=False)
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"access_token": "legacy-token"})

    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    assert asyncio.run(module.get_token()) == "legacy-token"
    assert requests[0].url.path == "/api/auth/login"


def test_bot_token_uses_real_account_authorization_after_password_change(module, tmp_path):
    async def scenario():
        engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "bot.db"))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add(User(username="admin", is_admin=True, hashed_password=security.hash_password("changed-password")))
            await db.commit()
        application = FastAPI()

        async def database():
            async with sessions() as db:
                yield db

        application.dependency_overrides[get_db] = database

        @application.get("/admin")
        async def admin(current=Depends(auth.require_admin)):
            return {"id": current.id}

        token = await module.get_token()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            assert (await client.get("/admin", headers={"Authorization": "Bearer " + token})).status_code == 200
            async with sessions() as db:
                user = await db.get(User, 1)
                user.is_active = False
                await db.commit()
            assert (await client.get("/admin", headers={"Authorization": "Bearer " + token})).status_code == 401
        await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("command", ["cmd_logs", "cmd_cert"])
def test_direct_api_commands_refresh_short_lived_token(module, monkeypatch, command):
    expired = jwt.encode({"sub": "admin", "exp": 1}, settings.JWT_SECRET, algorithm="HS256")
    monkeypatch.setattr(module, "_jwt_token", expired)

    def handle(request):
        token = request.headers["Authorization"].removeprefix("Bearer ")
        jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return httpx.Response(200, json={"valid": True})

    original = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    message = AsyncMock()
    message.message = message
    asyncio.run(getattr(module, command)(message))
    assert not message.answer.call_args.args[0].startswith("❌")
