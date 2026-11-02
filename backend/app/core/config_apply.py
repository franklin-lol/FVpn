"""Serialized, validated proxy configuration transactions for one backend worker."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("fvpn.config_apply")
# Deployment deliberately uses one backend worker; this is not a distributed lock.
APPLY_LOCK = asyncio.Lock()
COMMAND_TIMEOUT = 30


@dataclass(frozen=True)
class CoreConfig:
    name: str
    path: Path
    container: str
    binary: str
    config: dict[str, Any]


async def run_command(*args: str, input_data: bytes | None = None) -> tuple[int, bytes]:
    """Bound subprocess lifetime; never log core output containing credentials."""
    proc = await asyncio.create_subprocess_exec(
        *args, stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(input_data), COMMAND_TIMEOUT)
        return proc.returncode or 0, out
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.communicate()
        raise


async def validate_candidate(spec: CoreConfig, candidate: Path) -> tuple[bool, str]:
    """Use the sibling's exact image and read-only volumes, even when stopped."""
    code, out = await run_command("docker", "inspect", "--format", "{{.Image}}", spec.container)
    image = out.decode().strip()
    if code or not image.startswith("sha256:"):
        return False, "image_unavailable"
    environment: list[str] = []
    if spec.name == "singbox":
        # Match the sibling's compatibility switch without reading or forwarding
        # unrelated container environment values, which may contain secrets.
        variable = "ENABLE_DEPRECATED_LEGACY_DOMAIN_STRATEGY_OPTIONS=true"
        template = '{{range .Config.Env}}{{if eq . "' + variable + '"}}{{println .}}{{end}}{{end}}'
        code, out = await run_command("docker", "inspect", "--format", template, spec.container)
        if code:
            return False, "environment_unavailable"
        if out.decode().strip() == variable:
            environment = ["--env", variable]
    check = ("run", "-test", "-format", "json", "-config", "/dev/stdin") if spec.name == "xray" else (
        "check", "-c", "/dev/stdin",
    )
    code, _ = await run_command(
        "docker", "run", "--rm", "--pull", "never", "--network", "none",
        "--volumes-from", f"{spec.container}:ro", *environment, "--entrypoint", spec.binary,
        "-i", image, *check, input_data=candidate.read_bytes(),
    )
    return code == 0, "" if code == 0 else "invalid_config"


async def restart_core(spec: CoreConfig) -> bool:
    code, _ = await run_command("docker", "restart", "--time", "10", spec.container)
    if code:
        return False
    for _ in range(3):
        await asyncio.sleep(1)
        code, state = await run_command(
            "docker", "inspect", "--format", "{{json .State}}", spec.container,
        )
        if code:
            return False
        info = json.loads(state)
        if not info.get("Running") or info.get("Restarting"):
            return False
        health = info.get("Health", {}).get("Status")
        if health and health != "healthy":
            return False
    return True


def _stage(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    candidate = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        candidate.unlink(missing_ok=True)
        raise
    return candidate


async def apply_configs(specs: list[CoreConfig]) -> dict[str, bool | str]:
    async with APPLY_LOCK:
        return await apply_configs_locked(specs)


async def apply_configs_locked(specs: list[CoreConfig]) -> dict[str, bool | str]:
    """Caller holds APPLY_LOCK through DB read, build, validation and rollback."""
    result: dict[str, bool | str] = {spec.name: False for spec in specs}
    staged: dict[str, Path] = {}
    originals: dict[str, bytes | None] = {}
    replaced: list[CoreConfig] = []
    touched: list[CoreConfig] = []
    try:
        for spec in specs:
            originals[spec.name] = spec.path.read_bytes() if spec.path.exists() else None
            staged[spec.name] = _stage(spec.path, json.dumps(spec.config, indent=2).encode())
        valid = True
        for spec in specs:
            ok, _ = await validate_candidate(spec, staged[spec.name])
            valid = ok and valid
        if not valid:
            return {**result, "status": "validation_failed"}
        for spec in specs:
            original = originals[spec.name]
            if original is not None:
                backup = spec.path.with_suffix(spec.path.suffix + ".bak")
                _stage(backup, original).replace(backup)
            staged[spec.name].replace(spec.path)
            replaced.append(spec)
        for spec in specs:
            touched.append(spec)
            if not await restart_core(spec):
                raise RuntimeError("core_not_ready")
        return {**{spec.name: True for spec in specs}, "status": "applied"}
    except BaseException as error:
        restored = True
        for spec in replaced:
            try:
                original = originals[spec.name]
                if original is None:
                    spec.path.unlink(missing_ok=True)
                else:
                    _stage(spec.path, original).replace(spec.path)
            except OSError:
                restored = False
        for spec in touched:
            try:
                restored = await restart_core(spec) and restored
            except (OSError, RuntimeError, asyncio.TimeoutError, ValueError):
                restored = False
        status = "rolled_back" if replaced and restored else (
            "rollback_failed" if replaced else "apply_failed"
        )
        logger.error("Core configuration apply failed: %s (%s)", status, type(error).__name__)
        if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            raise
        return {**result, "status": status}
    finally:
        for candidate in staged.values():
            candidate.unlink(missing_ok=True)
