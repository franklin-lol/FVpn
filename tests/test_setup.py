"""Onboarding preserves deployed users and credentials across retries."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import database
from app.api import auth, setup
from app.core import bootstrap, config_writer, security
from app.models import Node, Protocol, User


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def context(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "setup.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)

    async def skip_bootstrap():
        pass

    monkeypatch.setattr(bootstrap, "run_once", skip_bootstrap)
    await database.init_db()
    async with sessions() as db:
        db.add_all([
            Node(name="Local", host="vpn.test", meta={"local": True}),
            Node(name="Remote", host="remote.test"),
            User(username="member", hashed_password=security.hash_password("old-password")),
        ])
        await db.commit()

    application = FastAPI()
    application.include_router(auth.router, prefix="/api/auth")
    application.include_router(setup.router, prefix="/api/setup")

    async def get_db():
        async with sessions() as db:
            yield db

    application.dependency_overrides[database.get_db] = get_db
    monkeypatch.setattr(auth, "_limiter", auth.LoginLimiter())
    transport = httpx.ASGITransport(app=application)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, sessions
    await engine.dispose()


def headers(username="admin"):
    return {"Authorization": "Bearer " + security.create_access_token({"sub": username})}


async def change(client, current=None, new="new-password-123"):
    return await client.post("/api/auth/password", headers=headers(), json={
        "current_password": current or database.settings.MASTER_PASSWORD,
        "new_password": new,
    })


@pytest.mark.anyio
async def test_fresh_setup_requires_password_change_and_admin(context):
    client, _ = context
    assert (await client.get("/api/setup")).status_code == 401
    assert (await client.get("/api/setup", headers=headers("member"))).status_code == 403
    status = await client.get("/api/setup", headers=headers())
    assert status.json() == {
        "required": True, "password_changed": False, "local_node_id": 1,
        "recommended_ready": False,
        "nodes": [{"id": 1, "name": "Local", "host": "vpn.test", "local": True},
                  {"id": 2, "name": "Remote", "host": "remote.test", "local": False}],
    }
    response = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 1, "preset": "recommended"})
    assert response.status_code == 409


@pytest.mark.anyio
@pytest.mark.parametrize("password", ["short", "a" * 73, "é" * 37])
async def test_password_rules_reject_before_mutating(context, password):
    client, sessions = context
    response = await change(client, new=password)
    assert response.status_code == 422
    async with sessions() as db:
        admin = (await db.execute(select(User).where(User.username == "admin"))).scalar_one()
        assert security.verify_password(database.settings.MASTER_PASSWORD, admin.hashed_password)


@pytest.mark.anyio
async def test_current_password_required_and_new_hash_survives_restart(context):
    from app.models import SetupState

    client, sessions = context
    assert (await change(client, current="wrong")).status_code == 401
    async with sessions() as db:
        before = (await db.get(User, 1)).hashed_password
    assert (await change(client)).json() == {"status": "password_changed"}
    await database.init_db()
    async with sessions() as db:
        assert (await db.get(SetupState, 1)).password_changed is True
        admin = await db.get(User, 1)
        assert admin.hashed_password != before
        assert security.verify_password("new-password-123", admin.hashed_password)


@pytest.mark.anyio
async def test_member_password_does_not_unlock_admin_setup(context):
    from app.models import SetupState

    client, sessions = context
    response = await client.post("/api/auth/password", headers=headers("member"), json={
        "current_password": "old-password", "new_password": "member-new-password",
    })
    assert response.status_code == 200
    async with sessions() as db:
        assert (await db.get(SetupState, 1)).password_changed is False


@pytest.mark.anyio
async def test_recommended_failure_retry_and_parallel_completion_reuse_credentials(context, monkeypatch):
    from app.models import SetupState

    client, sessions = context
    await change(client)
    calls = []

    async def apply(node_id):
        calls.append(node_id)
        async with sessions() as db:
            protocols = (await db.execute(select(Protocol))).scalars().all()
            assert len(protocols) == 1
            assert protocols[0].config["private_key"]
        return {"status": "validation_failed" if len(calls) == 1 else "applied"}

    monkeypatch.setattr(config_writer, "sync_node_config", apply)
    payload = {"node_id": 1, "preset": "recommended"}
    assert (await client.post("/api/setup/complete", headers=headers(), json=payload)).status_code == 409
    async with sessions() as db:
        original = (await db.execute(select(Protocol))).scalar_one().config
        assert (await db.get(SetupState, 1)).required
    results = await asyncio.gather(*(client.post("/api/setup/complete", headers=headers(), json=payload) for _ in range(3)))
    assert all(r.json() == {"status": "configured"} for r in results)
    assert calls == [1, 1]
    async with sessions() as db:
        assert (await db.execute(select(Protocol))).scalar_one().config == original
        assert not (await db.get(SetupState, 1)).required


@pytest.mark.anyio
async def test_existing_bootstrap_vless_is_reused(context, monkeypatch):
    client, sessions = context
    from app.lib.config_generator import ProtocolConfig

    original = ProtocolConfig.defaults("vless", 443, {})
    async with sessions() as db:
        db.add(Protocol(node_id=1, name="vless", port=443, config=original))
        await db.commit()
    await change(client)

    async def apply(node_id):
        return {"status": "applied"}

    monkeypatch.setattr(config_writer, "sync_node_config", apply)
    response = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 1, "preset": "recommended"})
    assert response.status_code == 200
    async with sessions() as db:
        assert (await db.execute(select(Protocol))).scalar_one().config == original


@pytest.mark.anyio
async def test_remote_requires_existing_supported_protocol_and_never_applies_local(context, monkeypatch):
    client, sessions = context
    await change(client)

    async def forbidden(*args):
        pytest.fail("remote existing selection must not touch local proxy cores")

    monkeypatch.setattr(config_writer, "sync_node_config", forbidden)
    for preset in ["existing", "recommended"]:
        response = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 2, "preset": preset})
        assert response.status_code == 409
    async with sessions() as db:
        db.add(Protocol(node_id=2, name="wireguard", port=51820, config={"private_key": "server-only"}))
        await db.commit()
    assert (await client.post("/api/setup/complete", headers=headers(), json={"node_id": 2, "preset": "existing"})).status_code == 409
    async with sessions() as db:
        db.add(Protocol(node_id=2, name="shadowsocks", port=8443, config={"password": "preserved"}))
        await db.commit()
    assert (await client.post("/api/setup/complete", headers=headers(), json={"node_id": 2, "preset": "existing"})).json() == {"status": "configured"}


@pytest.mark.anyio
async def test_legacy_admin_without_state_is_configured_and_hash_preserved(context):
    from app.models import SetupState

    client, sessions = context
    async with sessions() as db:
        original = (await db.get(User, 1)).hashed_password
        await db.delete(await db.get(SetupState, 1))
        await db.commit()
    await database.init_db()
    assert (await client.get("/api/setup", headers=headers())).json()["required"] is False
    async with sessions() as db:
        assert (await db.get(User, 1)).hashed_password == original
        assert await db.get(SetupState, 1) is None


@pytest.mark.anyio
async def test_concurrent_password_changes_cannot_overwrite_an_already_changed_hash(context, monkeypatch):
    client, _ = context
    original = auth.async_verify_password
    arrived = 0
    both = asyncio.Event()

    async def synchronized_verify(*args):
        nonlocal arrived
        valid = await original(*args)
        arrived += 1
        if arrived == 2:
            both.set()
        await both.wait()
        return valid

    monkeypatch.setattr(auth, "async_verify_password", synchronized_verify)
    responses = await asyncio.gather(change(client, new="one-new-password"), change(client, new="two-new-password"))
    assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.anyio
async def test_remote_protocol_without_credentials_cannot_complete(context):
    client, sessions = context
    await change(client)
    async with sessions() as db:
        db.add(Protocol(node_id=2, name="vless", port=443, config={}))
        await db.commit()
    result = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 2, "preset": "existing"})
    assert result.status_code == 409


@pytest.mark.anyio
async def test_unchanged_password_cannot_mark_setup_changed(context):
    from app.models import SetupState

    client, sessions = context
    result = await change(client, new=database.settings.MASTER_PASSWORD)
    assert result.status_code == 422
    async with sessions() as db:
        assert not (await db.get(SetupState, 1)).password_changed


@pytest.mark.anyio
@pytest.mark.parametrize("missing", ["uuid", "public_key", "private_key", "sni"])
@pytest.mark.parametrize("preset", ["recommended", "existing"])
async def test_incomplete_local_vless_is_preserved_and_rejected_before_apply(context, monkeypatch, missing, preset):
    from app.lib.config_generator import ProtocolConfig
    from app.models import SetupState

    client, sessions = context
    config = ProtocolConfig.defaults("vless", 443, {})
    del config[missing]
    async with sessions() as db:
        db.add(Protocol(node_id=1, name="vless", port=443, config=config, is_active=True))
        await db.commit()
    await change(client)

    async def forbidden(*args):
        pytest.fail("incomplete reused credentials must fail before config apply")

    monkeypatch.setattr(config_writer, "sync_node_config", forbidden)
    result = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 1, "preset": preset})
    assert result.status_code == 409
    assert (await client.get("/api/setup", headers=headers())).json()["recommended_ready"] is False
    async with sessions() as db:
        assert (await db.execute(select(Protocol))).scalar_one().config == config
        assert (await db.get(SetupState, 1)).required


@pytest.mark.anyio
async def test_existing_remote_vless_needs_no_server_private_key(context, monkeypatch):
    from app.lib.config_generator import ProtocolConfig

    client, sessions = context
    config = ProtocolConfig.defaults("vless", 443, {})
    del config["private_key"]
    async with sessions() as db:
        db.add(Protocol(node_id=2, name="vless", port=443, config=config))
        await db.commit()
    await change(client)

    async def forbidden(*args):
        pytest.fail("remote existing selection must not apply local cores")

    monkeypatch.setattr(config_writer, "sync_node_config", forbidden)
    result = await client.post("/api/setup/complete", headers=headers(), json={"node_id": 2, "preset": "existing"})
    assert result.status_code == 200
