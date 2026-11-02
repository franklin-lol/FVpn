"""Security boundaries run against real ASGI, bcrypt and temporary SQLite."""

import asyncio
import threading
import time

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import auth, stats, users
from app.config import Settings
from app.core import security
from app.database import Base, get_db
from app.models import User


@pytest.mark.parametrize("secret", ["", "short-secret", " " * 32, "changeme-generate-with-openssl-rand-hex-32"])
def test_unsafe_jwt_secret_rejected_without_disclosing_value(secret):
    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None, JWT_SECRET=secret)
    assert "input_value" not in str(caught.value)
    if secret:
        assert secret not in str(caught.value)


def test_valid_existing_secret_is_preserved():
    value = "unchanged-fixture-secret-at-least-32-bytes"
    assert Settings(_env_file=None, JWT_SECRET=value).JWT_SECRET == value


def test_secret_minimum_is_measured_in_utf8_bytes():
    assert Settings(_env_file=None, JWT_SECRET="é" * 16).JWT_SECRET == "é" * 16


@pytest.mark.parametrize("value", ["", "*", "https://one.test,https://two.test", '["https://one.test"]'])
def test_cors_defaults_to_panel_and_preserves_explicit_origins(value):
    config = Settings(_env_file=None, DOMAIN="vpn.test", PANEL_PORT=2095, CORS_ORIGINS=value)
    expected = ["https://vpn.test:2095"]
    if value == "https://one.test,https://two.test":
        expected = ["https://one.test", "https://two.test"]
    elif value.startswith("["):
        expected = ["https://one.test"]
    assert config.cors_list == expected


@pytest.mark.parametrize("value", ['["*"]', "https://ok.test,*", "https://user:pass@host.test", "https://host.test/path", "javascript:alert(1)", '[1]', '["https://ok.test",', 'https://host.test?query=1'])
def test_invalid_cors_fails_at_startup(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, CORS_ORIGINS=value)


@pytest.mark.parametrize("value", ["proxy.local", "172.20.0.0/16", "172.20.0.10,bad"])
def test_invalid_proxy_peer_settings_fail_at_startup(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, TRUSTED_PROXY_IPS=value)


def request(peer, headers):
    return Request({"type": "http", "client": (peer, 1234), "headers": [(k.encode(), v.encode()) for k, v in headers]})


@pytest.mark.parametrize("peer,headers,expected", [
    ("198.51.100.1", [("x-forwarded-for", "192.0.2.1"), ("x-real-ip", "192.0.2.2")], "198.51.100.1"),
    ("172.20.0.10", [("x-real-ip", "192.0.2.2")], "192.0.2.2"),
    ("172.20.0.10", [("x-forwarded-for", "192.0.2.1")], "172.20.0.10"),
    ("172.20.0.10", [("x-real-ip", "192.0.2.1,192.0.2.2")], "172.20.0.10"),
    ("172.20.0.10", [("x-real-ip", "192.0.2.1"), ("x-real-ip", "192.0.2.2")], "172.20.0.10"),
])
def test_only_single_real_ip_from_trusted_peer_is_accepted(peer, headers, expected):
    assert auth._client_ip(request(peer, headers)) == expected


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def app(tmp_path, monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "auth.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        db.add(User(username="admin", hashed_password=security.hash_password("correct"), is_admin=True))
        db.add(User(username="member", hashed_password=security.hash_password("correct")))
        await db.commit()
    application = FastAPI()
    application.include_router(auth.router, prefix="/auth")
    application.include_router(users.router, prefix="/users")
    application.include_router(stats.router, prefix="/stats")

    async def database():
        async with sessions() as db:
            yield db

    application.dependency_overrides[get_db] = database
    # Keep lockout state isolated between real endpoint tests.
    if hasattr(auth, "_limiter"):
        monkeypatch.setattr(auth, "_limiter", auth.LoginLimiter())
    else:
        auth._FAILS.clear()
    yield application
    await engine.dispose()


async def login(application, username="admin", password="wrong", ip="198.51.100.1"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, client=(ip, 1234)), base_url="http://test") as client:
        return await client.post("/auth/login", data={"username": username, "password": password})


@pytest.mark.anyio
async def test_account_limit_survives_ip_rotation(app):
    for i in range(5):
        assert (await login(app, ip=f"198.51.100.{i}")).status_code == 401
    result = await login(app, ip="203.0.113.1")
    assert result.status_code == 429
    assert int(result.headers["Retry-After"]) > 0


@pytest.mark.anyio
async def test_ip_limit_survives_account_rotation_and_spoofed_headers(app):
    transport = httpx.ASGITransport(app=app, client=("198.51.100.1", 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(5):
            result = await client.post("/auth/login", data={"username": f"unknown-{i}", "password": "wrong"}, headers={"X-Forwarded-For": f"192.0.2.{i}"})
            assert result.status_code == 401
        assert (await client.post("/auth/login", data={"username": "admin", "password": "correct"})).status_code == 429


@pytest.mark.anyio
async def test_parallel_attempts_reserve_limit_before_password_work(app, monkeypatch):
    started = 0
    release = asyncio.Event()

    async def slow_verify(*args):
        nonlocal started
        started += 1
        await release.wait()
        return False

    # Slow boundary allows all concurrent requests to reach the reservation.
    monkeypatch.setattr(auth, "async_verify_password", slow_verify, raising=False)
    tasks = [asyncio.create_task(login(app)) for _ in range(12)]
    for _ in range(100):
        await asyncio.sleep(0.01)
        if started >= 5:
            break
    release.set()
    results = await asyncio.gather(*tasks)
    assert sorted(r.status_code for r in results) == [401] * 5 + [429] * 7
    assert started == 5


@pytest.mark.anyio
async def test_denied_requests_do_not_extend_lockout(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    for _ in range(5):
        assert (await login(app)).status_code == 401
    now[0] += 899
    assert (await login(app)).status_code == 429
    now[0] += 2
    assert (await login(app, password="correct")).status_code == 200


@pytest.mark.anyio
async def test_success_clears_own_failures_without_erasing_other_accounts(app):
    for _ in range(3):
        assert (await login(app, username="member")).status_code == 401
    assert (await login(app)).status_code == 401
    assert (await login(app, password="correct")).status_code == 200
    assert (await login(app, username="member")).status_code == 401
    assert (await login(app, username="member")).status_code == 401
    assert (await login(app, username="member")).status_code == 429


def test_limiter_memory_is_bounded_and_expired_capacity_is_reused(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    limiter = auth.LoginLimiter(capacity=8)
    for i in range(8):
        limiter.reserve(f"ip-{i}", f"account-{i}")
    with pytest.raises(auth.HTTPException) as caught:
        limiter.reserve("new-ip", "new-account")
    assert caught.value.status_code == 429
    now[0] += 901
    limiter.reserve("new-ip", "new-account")
    assert len(limiter.accounts) <= 8
    assert len(limiter.addresses) <= 8


def test_success_does_not_remove_another_pending_reservation():
    limiter = auth.LoginLimiter()
    limiter.reserve("192.0.2.1", "admin")
    successful = limiter.reserve("192.0.2.1", "admin")
    limiter.release(successful, success=True)
    for _ in range(4):
        limiter.reserve("192.0.2.1", "admin")
    with pytest.raises(auth.HTTPException) as caught:
        limiter.reserve("192.0.2.1", "admin")
    assert caught.value.status_code == 429


@pytest.mark.anyio
async def test_real_bcrypt_roundtrip_does_not_block_event_loop():
    ticks = 0
    done = False

    async def heartbeat():
        nonlocal ticks
        while not done:
            ticks += 1
            await asyncio.sleep(0.005)

    task = asyncio.create_task(heartbeat())
    try:
        hashed = await security.async_hash_password("correct")
        assert await security.async_verify_password("correct", hashed)
        assert not await security.async_verify_password("wrong", hashed)
    finally:
        done = True
        await task
    assert ticks > 10


@pytest.mark.anyio
async def test_password_thread_concurrency_is_bounded_even_after_cancellation(monkeypatch):
    active = 0
    maximum = 0
    lock = threading.Lock()

    def slow_hash(password):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "hash"

    monkeypatch.setattr(security, "hash_password", slow_hash)
    tasks = [asyncio.create_task(security.async_hash_password("x")) for _ in range(16)]
    await asyncio.sleep(0.01)
    for task in tasks[:4]:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    assert maximum <= 4
    assert active == 0


@pytest.mark.anyio
async def test_cpu_sample_keeps_event_loop_responsive(app, monkeypatch):
    def sample(*args, **kwargs):
        time.sleep(0.1)
        return 37.5

    monkeypatch.setattr(stats.psutil, "cpu_percent", sample)
    app.dependency_overrides[auth.require_admin] = lambda: None
    ticks = 0
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        pending = asyncio.create_task(client.get("/stats/dashboard"))
        while not pending.done():
            ticks += 1
            await asyncio.sleep(0.005)
        result = await pending
    assert result.json()["system"]["cpu_pct"] == 37.5
    assert ticks >= 10


@pytest.mark.anyio
async def test_admin_create_and_update_password_keep_loop_responsive(app, monkeypatch):
    original_hash = security.hash_password

    def slow_hash(password):
        time.sleep(0.1)
        return original_hash(password)

    monkeypatch.setattr(security, "hash_password", slow_hash)
    token = (await login(app, password="correct")).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        async def responsive(operation):
            pending = asyncio.create_task(operation)
            ticks = 0
            while not pending.done():
                ticks += 1
                await asyncio.sleep(0.005)
            result = await pending
            assert ticks > 10
            return result

        created = await responsive(client.post("/users", json={"username": "created", "password": "first"}, headers=headers))
        assert created.status_code == 201
        updated = await responsive(client.patch(f"/users/{created.json()['id']}", json={"password": "second"}, headers=headers))
        assert updated.status_code == 200
    assert (await login(app, username="created", password="first", ip="203.0.113.10")).status_code == 401
    assert (await login(app, username="created", password="second", ip="203.0.113.10")).status_code == 200


@pytest.mark.anyio
async def test_bootstrap_admin_hash_is_offloaded_and_existing_password_preserved(tmp_path, monkeypatch):
    from app import database
    from app.core import bootstrap

    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "startup.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)

    async def no_services():
        pass

    monkeypatch.setattr(bootstrap, "run_once", no_services)
    original_hash = security.hash_password

    def slow_hash(password):
        time.sleep(0.1)
        return original_hash(password)

    monkeypatch.setattr(security, "hash_password", slow_hash)
    pending = asyncio.create_task(database.init_db())
    ticks = 0
    while not pending.done():
        ticks += 1
        await asyncio.sleep(0.005)
    await pending
    assert ticks > 10
    async with sessions() as db:
        existing = await db.get(User, 1)
        hashed = existing.hashed_password
        assert await security.async_verify_password(database.settings.MASTER_PASSWORD, hashed)
    await database.init_db()
    async with sessions() as db:
        assert (await db.get(User, 1)).hashed_password == hashed
    await engine.dispose()
