"""WebSocket authorization uses current SQLite user records, never JWT role claims."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.websockets import WebSocketDisconnect

import main
from app.config import settings
from app.core.security import create_access_token
from app.database import Base
from app.models import User


@pytest.fixture
def websocket_app(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "websocket.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def prepare():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all([
                User(username="admin", hashed_password="unused-fixture", is_admin=True, is_active=True),
                User(username="member", hashed_password="unused-fixture", is_admin=False, is_active=True),
                User(username="inactive", hashed_password="unused-fixture", is_admin=True, is_active=False),
            ])
            await session.commit()

    asyncio.run(prepare())
    monkeypatch.setattr(main, "SessionLocal", sessions, raising=False)
    manager = main.WSManager()
    manager.connect = AsyncMock(wraps=manager.connect)
    monkeypatch.setattr(main, "ws_manager", manager)
    # Omitting TestClient's lifespan context prevents bootstrap and service startup.
    client = TestClient(main.app)
    try:
        yield client, manager
    finally:
        client.close()
        asyncio.run(engine.dispose())


def connect_url(token):
    return "/ws/stats" if token is None else "/ws/stats?token=" + token


@pytest.mark.parametrize("subject", [None, "invalid", "member", "inactive", "deleted", "missing-sub", "expired"])
def test_socket_rejects_invalid_or_unauthorized_users_before_accept(websocket_app, subject):
    client, manager = websocket_app
    if subject in (None, "invalid"):
        token = subject
    elif subject == "missing-sub":
        token = create_access_token({"admin": True})
    elif subject == "expired":
        token = jwt.encode(
            {"sub": "admin", "admin": True, "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            settings.JWT_SECRET,
            algorithm=settings.JWT_ALGORITHM,
        )
    else:
        token = create_access_token({"sub": subject, "admin": True})

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(connect_url(token)):
            pytest.fail("unauthorized WebSocket must not be accepted")
    assert caught.value.code == 4001
    manager.connect.assert_not_awaited()
    assert manager.connections == []


def test_socket_accepts_current_admin_and_cleans_up_on_disconnect(websocket_app):
    client, manager = websocket_app
    # Current DB role is authoritative, even if a valid old JWT has admin=False.
    token = create_access_token({"sub": "admin", "admin": False})
    with client.websocket_connect(connect_url(token)) as websocket:
        assert len(manager.connections) == 1
        manager.connect.assert_awaited_once()
        websocket.send_text("keep-alive")
    assert manager.connections == []


def test_disconnecting_one_admin_keeps_other_socket_registered(websocket_app):
    client, manager = websocket_app
    token = create_access_token({"sub": "admin"})
    with client.websocket_connect(connect_url(token)):
        with client.websocket_connect(connect_url(token)):
            assert len(manager.connections) == 2
        assert len(manager.connections) == 1
    assert manager.connections == []
