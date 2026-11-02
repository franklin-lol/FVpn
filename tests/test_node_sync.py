"""Node locality and protocol input regressions against an isolated SQLite DB."""

import asyncio
import base64
import json

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_remote_force_sync_never_queues_local_apply(tmp_path, monkeypatch):
    from app.api import protocols
    from app.database import Base
    from app.models import Node

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            node = Node(name="remote", host="127.0.0.1", meta={})
            db.add(node)
            await db.commit()
            bg = BackgroundTasks()
            with pytest.raises(HTTPException) as error:
                await protocols.force_sync(node.id, bg, None, db)
            assert error.value.status_code == 409
            assert "manual_required" in str(error.value.detail)
            assert not bg.tasks
        await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [
    {"node_id": 1, "name": "unknown", "port": 443},
    {"node_id": 1, "name": "trojan", "port": 0},
    {"node_id": 1, "name": "trojan", "port": 65536},
    {"node_id": 1, "name": "trojan", "port": "443"},
    {"node_id": 1, "name": "trojan", "port": 443, "config": {"password": {"bad": "type"}}},
    {"node_id": 1, "name": "shadowtls", "port": 443, "config": {"ss_port": 70000}},
    {"node_id": 1, "name": "trojan", "port": 443, "config": {"unknown": True}},
])
def test_protocol_create_rejects_invalid_input(payload):
    from app.api.protocols import ProtocolCreate

    with pytest.raises(ValidationError):
        ProtocolCreate.model_validate(payload)


@pytest.mark.parametrize("payload", [{"id": 3}, {"node_id": 3}, {"created_at": "now"}])
def test_protocol_patch_rejects_identity_reassignment(payload):
    from app.api.protocols import ProtocolUpdate

    with pytest.raises(ValidationError):
        ProtocolUpdate.model_validate(payload)


def test_remote_sync_function_returns_manual_required_without_apply(tmp_path, monkeypatch):
    import app.database as database
    from app.core import config_writer
    from app.database import Base
    from app.models import Node

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'boundary.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        async with sessions() as db:
            node = Node(name="remote", host="localhost", meta={"local": "true"})
            db.add(node)
            await db.commit()
            node_id = node.id

        async def apply(specs):
            pytest.fail("remote node must never reach the local core boundary")

        monkeypatch.setattr(config_writer, "apply_configs_locked", apply)
        assert await config_writer.sync_node_config(node_id) == {
            "xray": False, "singbox": False, "status": "manual_required",
        }
        await engine.dispose()

    asyncio.run(scenario())


def test_local_protocol_without_server_builder_is_not_silently_applied(tmp_path, monkeypatch):
    import app.database as database
    from app.core import config_writer
    from app.database import Base
    from app.models import Node, Protocol

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'unsupported.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        async with sessions() as db:
            node = Node(name="local", host="fixture.invalid", meta={"local": True})
            db.add(node)
            await db.flush()
            node_id = node.id
            db.add(Protocol(node_id=node_id, name="ssh", port=22, config={}))
            await db.commit()

        async def apply(specs):
            pytest.fail("unsupported listener must not replace a working configuration")

        monkeypatch.setattr(config_writer, "apply_configs_locked", apply)
        assert (await config_writer.sync_node_config(node_id))["status"] == "unsupported_protocol"
        await engine.dispose()

    asyncio.run(scenario())


def test_unsupported_remote_setup_fails_before_ssh():
    from app.api.nodes import _setup_script

    with pytest.raises(ValueError):
        _setup_script("vless", 443, {}, "synthetic.example")


def test_empty_local_sync_removes_proxy_inbounds(tmp_path, monkeypatch):
    from app.core import config_writer, xray
    import app.database as database
    from app.database import Base
    from app.models import Node

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'empty.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        monkeypatch.setattr(xray, "XRAY_BIN", "/host-only/xray")
        async with sessions() as db:
            node = Node(name="local", host="example.invalid", meta={"local": True})
            db.add(node)
            await db.commit()
            node_id = node.id
        captured = []

        async def apply(specs):
            captured.extend(specs)
            return {"xray": True, "singbox": True, "status": "applied"}

        monkeypatch.setattr(config_writer, "apply_configs_locked", apply, raising=False)
        result = await config_writer.sync_node_config(node_id)
        assert result["xray"] and result["singbox"]
        assert len(captured) == 2
        assert captured[0].binary == "/usr/bin/xray"
        assert captured[0].config["inbounds"] == [{
            "tag": "api-in", "listen": "127.0.0.1", "port": 62789,
            "protocol": "dokodemo-door", "settings": {"address": "127.0.0.1"},
        }]
        assert captured[1].config["inbounds"] == []
        await engine.dispose()

    asyncio.run(scenario())


def test_remote_setup_persists_exactly_the_generated_credentials(tmp_path, monkeypatch):
    import app.database as database
    from app.api import nodes
    from app.database import Base
    from app.lib.config_generator import ProtocolConfig
    from app.models import Node, Protocol
    from sqlalchemy import select

    generated = []
    delivered = []

    def defaults(name, port, extra):
        config = {"password": f"generated-{len(generated)}", "method": "aes-256-gcm"}
        generated.append(config)
        return config

    class SSH:
        def __init__(self, *args):
            pass

        async def connect(self):
            assert len(generated) == 1

        async def exec(self, command):
            delivered.append(command)
            return "", "", 0

        async def disconnect(self):
            pass

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'remote.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        monkeypatch.setattr(nodes, "SSHClient", SSH)
        monkeypatch.setattr(ProtocolConfig, "defaults", defaults)
        async with sessions() as db:
            node = Node(name="remote", host="synthetic.invalid", ssh_key="fixture")
            db.add(node)
            await db.commit()
            node_id = node.id
        await nodes._auto_setup_bg(node_id, "shadowsocks", 8443, {})
        async with sessions() as db:
            proto = (await db.execute(select(Protocol))).scalar_one()
            assert proto.config == generated[0]
        assert len(generated) == 1
        config_command = next(command for command in delivered if "base64 -d" in command)
        encoded = config_command.split("'")[3]
        assert json.loads(base64.b64decode(encoded))["password"] == "generated-0"
        await engine.dispose()

    asyncio.run(scenario())


def test_bootstrap_retries_failed_apply_without_reseeding_credentials(tmp_path, monkeypatch):
    import app.database as database
    from app.core import bootstrap, config_writer
    from app.database import Base
    from app.models import Node, Protocol
    from sqlalchemy import select

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        monkeypatch.setattr(bootstrap, "FLAG_FILE", tmp_path / "bootstrap_done")
        attempts = []

        async def sync(node_id):
            attempts.append(node_id)
            ok = len(attempts) > 1
            return {"xray": ok, "singbox": ok, "status": "applied" if ok else "validation_failed"}

        monkeypatch.setattr(config_writer, "sync_node_config", sync)
        await bootstrap.run_once()
        assert not bootstrap.FLAG_FILE.exists()
        async with sessions() as db:
            before = [(row.name, row.config) for row in (await db.execute(select(Protocol))).scalars()]
        assert {name for name, _ in before} == {"vless", "shadowsocks"}
        await bootstrap.run_once()
        assert bootstrap.FLAG_FILE.exists()
        async with sessions() as db:
            assert len((await db.execute(select(Node))).scalars().all()) == 1
            after = [(row.name, row.config) for row in (await db.execute(select(Protocol))).scalars()]
        assert before == after
        assert attempts == [1, 1]
        await engine.dispose()

    asyncio.run(scenario())
