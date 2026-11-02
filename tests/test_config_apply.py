"""Configuration transactions use temporary files and mocked core boundaries."""

import asyncio
import json

import pytest


def test_both_candidates_checked_before_any_live_file_changes(tmp_path, monkeypatch):
    from app.core import config_apply

    paths = [tmp_path / "xray.json", tmp_path / "singbox.json"]
    for path in paths:
        path.write_text('{"old":true}')
    checked = []

    async def validate(spec, candidate):
        assert all(path.read_text() == '{"old":true}' for path in paths)
        checked.append(spec.name)
        return spec.name != "singbox", ""

    async def restart(spec):
        pytest.fail("invalid candidates must not restart cores")

    monkeypatch.setattr(config_apply, "validate_candidate", validate)
    monkeypatch.setattr(config_apply, "restart_core", restart)
    specs = [config_apply.CoreConfig(name, path, name, name, {"new": True})
             for name, path in zip(("xray", "singbox"), paths)]
    result = asyncio.run(config_apply.apply_configs(specs))
    assert checked == ["xray", "singbox"]
    assert result["status"] == "validation_failed"
    assert all(path.read_text() == '{"old":true}' for path in paths)


def test_restart_failure_restores_both_files_and_touched_cores(tmp_path, monkeypatch):
    from app.core import config_apply

    paths = [tmp_path / "xray.json", tmp_path / "singbox.json"]
    for path in paths:
        path.write_text('{"old":true}')
    calls = []

    async def validate(spec, candidate):
        assert json.loads(candidate.read_text()) == {"new": True}
        return True, ""

    async def restart(spec):
        calls.append((spec.name, json.loads(spec.path.read_text())))
        return len(calls) != 2

    monkeypatch.setattr(config_apply, "validate_candidate", validate)
    monkeypatch.setattr(config_apply, "restart_core", restart)
    specs = [config_apply.CoreConfig(name, path, name, name, {"new": True})
             for name, path in zip(("xray", "singbox"), paths)]
    result = asyncio.run(config_apply.apply_configs(specs))
    assert result["status"] == "rolled_back"
    assert result["xray"] is False and result["singbox"] is False
    assert calls == [("xray", {"new": True}), ("singbox", {"new": True}),
                     ("xray", {"old": True}), ("singbox", {"old": True})]
    assert all(path.read_text() == '{"old":true}' for path in paths)
    assert len(list(tmp_path.glob("*.bak"))) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_validator_uses_same_image_without_requiring_running_container(tmp_path, monkeypatch):
    from app.core import config_apply

    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"synthetic":true}')
    commands = []

    async def command(*args, input_data=None):
        commands.append((args, input_data))
        return (0, b"sha256:fixture\n") if args[1] == "inspect" else (0, b"")

    monkeypatch.setattr(config_apply, "run_command", command)
    spec = config_apply.CoreConfig("xray", candidate, "stopped-xray", "/usr/bin/xray", {})
    assert asyncio.run(config_apply.validate_candidate(spec, candidate))[0]
    args, stdin = commands[-1]
    assert args[:3] == ("docker", "run", "--rm")
    assert args[args.index("--network") + 1] == "none"
    assert "stopped-xray:ro" in args and "sha256:fixture" in args
    assert "exec" not in args
    assert "run" in args and "-test" in args
    assert args[-6:] == ("run", "-test", "-format", "json", "-config", "/dev/stdin")
    assert stdin == candidate.read_bytes()


@pytest.mark.parametrize("enabled", [True, False])
def test_singbox_validator_preserves_only_explicit_sibling_compatibility_env(tmp_path, monkeypatch, enabled):
    from app.core import config_apply

    candidate = tmp_path / "synthetic.json"
    candidate.write_text('{"synthetic":true}')
    commands = []
    variable = "ENABLE_DEPRECATED_LEGACY_DOMAIN_STRATEGY_OPTIONS=true"

    async def command(*args, input_data=None):
        commands.append(args)
        if args[1] == "inspect":
            if args[3] == "{{.Image}}":
                return 0, b"sha256:fixture\n"
            return 0, (variable.encode() + b"\n") if enabled else b""
        return 0, b""

    monkeypatch.setattr(config_apply, "run_command", command)
    monkeypatch.setenv("ENABLE_DEPRECATED_LEGACY_DOMAIN_STRATEGY_OPTIONS", "false" if enabled else "true")
    spec = config_apply.CoreConfig("singbox", candidate, "fixture-singbox", "/usr/bin/sing-box", {})
    assert asyncio.run(config_apply.validate_candidate(spec, candidate))[0]
    argv = commands[-1]
    assert (variable in argv) is enabled
    if enabled:
        assert argv[argv.index(variable) - 1] == "--env"
    assert argv[argv.index("--entrypoint") + 1] == "/usr/bin/sing-box"
    assert argv[-3:] == ("check", "-c", "/dev/stdin")


def test_restart_rejects_crashing_core_even_after_successful_restart(tmp_path, monkeypatch):
    from app.core import config_apply

    async def command(*args, input_data=None):
        return (0, b'{"Running":false,"Restarting":true}') if args[1] == "inspect" else (0, b"")

    async def sleep(delay):
        pass

    monkeypatch.setattr(config_apply, "run_command", command)
    monkeypatch.setattr(config_apply.asyncio, "sleep", sleep)
    spec = config_apply.CoreConfig("xray", tmp_path / "synthetic.json", "fixture", "xray", {})
    assert asyncio.run(config_apply.restart_core(spec)) is False


def test_local_sync_serializes_database_read_and_apply(tmp_path, monkeypatch):
    import app.database as database
    from app.core import config_writer
    from app.database import Base
    from app.models import Node, Protocol
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'serial.sqlite'}")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "SessionLocal", sessions)
        lock = asyncio.Lock()
        monkeypatch.setattr(config_writer, "APPLY_LOCK", lock)
        async with sessions() as db:
            node = Node(name="local", host="fixture.invalid", meta={"local": True})
            db.add(node)
            await db.flush()
            node_id = node.id
            db.add(Protocol(node_id=node.id, name="shadowsocks", port=8443,
                            config={"password": "fixture"}))
            await db.commit()
        reached = asyncio.Event()
        release = asyncio.Event()
        configs = []

        async def apply(specs):
            configs.append(specs[1].config["inbounds"])
            if len(configs) == 1:
                reached.set()
                await release.wait()
            return {"xray": True, "singbox": True, "status": "applied"}

        monkeypatch.setattr(config_writer, "apply_configs_locked", apply)
        first = asyncio.create_task(config_writer.sync_node_config(node_id))
        await reached.wait()
        second = asyncio.create_task(config_writer.sync_node_config(node_id))
        await asyncio.sleep(0)
        async with sessions() as db:
            proto = (await db.execute(select(Protocol))).scalar_one()
            proto.is_active = False
            await db.commit()
        release.set()
        await asyncio.gather(first, second)
        assert len(configs[0]) == 1
        assert configs[1] == []
        await engine.dispose()

    asyncio.run(scenario())
