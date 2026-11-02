"""Subscription ownership and token-scoped metadata against real ASGI/SQLite."""

import base64
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import subscriptions
from app.api.auth import get_current_user
from app.database import Base, get_db
from app.models import Node, Protocol, Subscription, User


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'subscriptions.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        admin = User(username="admin", hashed_password="unused", is_admin=True)
        member = User(username="owner-SENTINEL", hashed_password="unused")
        node = Node(name="fixture", host="fixture.invalid", ssh_key="ssh-key-SENTINEL")
        db.add_all([admin, member, node])
        await db.flush()
        db.add(Protocol(node_id=node.id, name="shadowsocks", port=443,
                        config={"password": "proxy-password-SENTINEL"}))
        sub = Subscription(user_id=member.id, format="base64")
        db.add(sub)
        await db.commit()
    app = FastAPI(redirect_slashes=False)
    app.include_router(subscriptions.router, prefix="/subscriptions")

    async def database():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: member
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, app, sessions, admin, member, sub, node, engine
    await engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/subscriptions", "/subscriptions/"])
async def test_omitted_owner_is_current_and_other_owner_requires_admin(context, path):
    client, app, _, admin, member, _, _, _ = context
    own = await client.post(path, json={"format": "singbox"})
    assert own.status_code == 201
    assert own.json()["user_id"] == member.id
    assert own.json()["connect_url"].endswith("/s/" + own.json()["token"])
    assert (await client.post(path, json={"user_id": admin.id})).status_code == 403
    app.dependency_overrides[get_current_user] = lambda: admin
    other = await client.post(path, json={"user_id": member.id})
    assert other.status_code == 201
    assert other.json()["user_id"] == member.id
    assert (await client.post(path, json={"user_id": 99999})).status_code == 404
    admin_sub = await client.post(path, json={"format": "singbox"})
    assert admin_sub.status_code == 201
    assert admin_sub.json()["user_id"] == admin.id
    app.dependency_overrides[get_current_user] = lambda: member
    listed = await client.get(path)
    assert listed.status_code == 200
    assert all(row["user_id"] == member.id and row["connect_url"].endswith("/s/" + row["token"])
               for row in listed.json())


@pytest.mark.anyio
@pytest.mark.parametrize("path", ["/subscriptions", "/subscriptions/"])
@pytest.mark.parametrize("method", ["GET", "POST"])
async def test_collection_paths_require_authentication(context, path, method):
    client, app, *_ = context
    app.dependency_overrides.pop(get_current_user)
    response = await client.request(method, path, json={"format": "singbox"})
    assert response.status_code == 401
    assert "SENTINEL" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("user_id", [0, -1, "1", True])
async def test_target_owner_must_be_strict_positive_integer(context, user_id):
    client, *_ = context
    assert (await client.post("/subscriptions", json={"user_id": user_id})).status_code == 422


@pytest.mark.anyio
async def test_public_info_minimal_no_store_and_formats_match_exports(context):
    client, app, _, _, _, sub, _, _ = context
    app.dependency_overrides.pop(get_current_user)
    result = await client.get(f"/subscriptions/info/{sub.token}")
    assert result.status_code == 200
    assert result.headers["Cache-Control"] == "no-store"
    body = result.json()
    assert set(body) == {"format", "url", "connect_url", "expires_at", "available_formats"}
    assert body["format"] == "base64"
    assert body["url"].endswith(f"/fetch/{sub.token}?format=base64")
    assert body["connect_url"].endswith(f"/s/{sub.token}")
    assert body["available_formats"] == ["singbox", "hiddify", "clash", "shadowrocket", "v2rayng", "base64"]
    assert "SENTINEL" not in result.text
    for fmt in body["available_formats"]:
        exported = await client.get(f"/subscriptions/fetch/{sub.token}", params={"format": fmt})
        assert exported.status_code == 200
        assert exported.headers["Cache-Control"] == "no-store"
    qr = await client.get(f"/subscriptions/qr/{sub.token}")
    assert qr.status_code == 200
    assert qr.headers["Cache-Control"] == "no-store"


@pytest.mark.anyio
@pytest.mark.parametrize("stored_format", ["base64", "v2rayng", "shadowrocket"])
async def test_fetch_without_format_preserves_the_subscription_client_format(context, stored_format):
    client, app, sessions, _, _, sub, _, _ = context
    app.dependency_overrides.pop(get_current_user)
    async with sessions() as db:
        stored = await db.get(Subscription, sub.id)
        stored.format = stored_format
        await db.commit()
    response = await client.get(f"/subscriptions/fetch/{sub.token}")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/plain")
    assert response.headers["Cache-Control"] == "no-store"
    raw = response.text if stored_format == "shadowrocket" else base64.b64decode(response.content).decode()
    uris = [line for line in raw.splitlines() if line and not line.startswith("#")]
    assert len(uris) == 1
    parsed = urlsplit(uris[0])
    assert parsed.scheme == "ss"
    assert parsed.hostname == "fixture.invalid"
    assert parsed.port == 443
    assert base64.b64decode(parsed.username).decode() == "aes-256-gcm:proxy-password-SENTINEL"
    assert "ssh-key-SENTINEL" not in raw


@pytest.mark.anyio
async def test_fetch_explicit_format_overrides_the_subscription_client_format(context):
    client, app, _, _, _, sub, _, _ = context
    app.dependency_overrides.pop(get_current_user)
    response = await client.get(f"/subscriptions/fetch/{sub.token}", params={"format": "singbox"})
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.headers["Cache-Control"] == "no-store"
    outbound = next(item for item in response.json()["outbounds"] if item["type"] == "shadowsocks")
    assert outbound["server"] == "fixture.invalid"
    assert outbound["server_port"] == 443
    assert outbound["password"] == "proxy-password-SENTINEL"
    assert "ssh-key-SENTINEL" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("state", ["disabled", "expired", "missing"])
async def test_public_info_fetch_and_qr_enforce_same_owner_state(context, state):
    client, _, sessions, _, member, sub, _, _ = context
    if state != "missing":
        async with sessions() as db:
            user = await db.get(User, member.id)
            if state == "disabled":
                user.is_active = False
            else:
                user.expire_at = datetime.utcnow() - timedelta(days=1)
            await db.commit()
    token = "absent" if state == "missing" else sub.token
    for route in ("info", "fetch", "qr"):
        result = await client.get(f"/subscriptions/{route}/{token}")
        assert result.status_code == (404 if state == "missing" else 403)
        assert result.headers["Cache-Control"] == "no-store"


@pytest.mark.anyio
async def test_only_wireguard_has_no_available_formats(context):
    client, _, sessions, _, _, sub, node, _ = context
    async with sessions() as db:
        protocol = await db.get(Protocol, 1)
        protocol.name = "wireguard"
        protocol.config = {"private_key": "server-private-SENTINEL"}
        db.add(Protocol(node_id=node.id, name="trojan", port=8443, is_active=False, config={}))
        await db.commit()
    info = await client.get(f"/subscriptions/info/{sub.token}")
    assert info.status_code == 200
    assert info.json()["available_formats"] == []
    fetched = await client.get(f"/subscriptions/fetch/{sub.token}")
    assert fetched.status_code == 409
    assert "compatible" in fetched.json()["detail"].lower()


@pytest.mark.anyio
async def test_shadowtls_only_offers_singbox_formats(context):
    client, _, sessions, _, _, sub, _, _ = context
    async with sessions() as db:
        protocol = await db.get(Protocol, 1)
        protocol.name = "shadowtls"
        await db.commit()
    assert (await client.get(f"/subscriptions/info/{sub.token}")).json()["available_formats"] == ["singbox", "hiddify"]


@pytest.mark.anyio
async def test_inactive_nodes_do_not_offer_protocol_formats(context):
    client, _, sessions, _, _, sub, node, _ = context
    async with sessions() as db:
        stored_node = await db.get(Node, node.id)
        stored_node.is_active = False
        await db.commit()
    assert (await client.get(f"/subscriptions/info/{sub.token}")).json()["available_formats"] == []


@pytest.mark.anyio
async def test_metadata_query_count_does_not_grow_with_nodes(context):
    client, _, sessions, _, _, sub, _, engine = context
    async with sessions() as db:
        for index in range(5):
            node = Node(name=f"fixture-{index}", host=f"fixture-{index}.invalid")
            db.add(node)
            await db.flush()
            db.add(Protocol(node_id=node.id, name="shadowsocks", port=443, config={"password": "synthetic"}))
        await db.commit()
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        result = await client.get(f"/subscriptions/info/{sub.token}")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert result.status_code == 200
    assert len(statements) == 2


@pytest.mark.anyio
async def test_catalogue_offers_only_implemented_server_families():
    from app.api.protocols import supported_protocols

    catalogue = await supported_protocols(None)
    assert {protocol["name"] for protocol in catalogue["protocols"]} == {
        "vless", "vmess", "trojan", "shadowsocks", "shadowtls", "hysteria2", "tuic",
    }


@pytest.mark.anyio
@pytest.mark.parametrize("success", [True, False])
async def test_sync_reports_actual_apply_result(context, monkeypatch, success):
    from app.api import protocols
    from app.core import config_writer
    client, app, sessions, _, _, _, node, _ = context
    app.include_router(protocols.router, prefix="/protocols")
    from app.api.auth import require_admin
    app.dependency_overrides[require_admin] = lambda: None
    calls = []

    async def sync(node_id):
        calls.append(node_id)
        return {"status": "applied" if success else "validation_failed", "xray": success, "singbox": success}

    monkeypatch.setattr(config_writer, "sync_node_config", sync)
    async with sessions() as db:
        stored = await db.get(Node, node.id)
        stored.meta = {"local": True}
        await db.commit()
        if success:
            result = await client.post(f"/protocols/sync/{node.id}")
            assert result.status_code == 200
            assert result.json()["status"] == "applied"
        else:
            result = await client.post(f"/protocols/sync/{node.id}")
            assert result.status_code == 409
            assert result.json()["detail"]["status"] == "validation_failed"
    assert calls == [node.id]
