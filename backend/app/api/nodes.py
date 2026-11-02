"""Nodes management — CRUD + SSH auto-setup"""

import base64
import json
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field, JsonValue, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Node, Protocol
from app.api.auth import require_admin, User
from app.core.ssh import SSHClient
from app.api.protocols import Port, ProtocolName, validate_options

router = APIRouter()


class NodeCreate(BaseModel):
    name: str
    host: str
    ssh_port: int = 22
    ssh_user: str = "root"
    ssh_key: Optional[str] = None
    group: Optional[str] = None


class NodeOut(BaseModel):
    id: int
    name: str
    host: str
    ssh_port: int
    ssh_user: str
    group: Optional[str]
    status: str
    latency_ms: Optional[float]
    traffic_in: int
    traffic_out: int
    is_active: bool
    last_check: Optional[datetime]
    created_at: datetime
    protocols: list[dict] = []

    model_config = {"from_attributes": True}


class AutoSetupRequest(BaseModel):
    model_config = {"extra": "forbid"}
    protocol: ProtocolName
    port: Port = 443
    extra: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("extra")
    @classmethod
    def validate_extra(cls, value):
        return validate_options(value)


# IMPORTANT: /check-all must be registered BEFORE /{node_id} so it isn't
# swallowed as a path parameter — same reasoning applies to any other
# static sub-route added later under this router.

def _node_out(n: Node, protocols: list[dict]) -> NodeOut:
    """
    Build NodeOut from an explicit field dict — NEVER call
    NodeOut.model_validate(node) directly. from_attributes=True makes
    pydantic read every declared field off the ORM object, INCLUDING the
    `protocols` relationship (same name as our plain list[dict] field).
    That triggers a lazy SQL load, but by the time response serialization
    runs the request's async session/greenlet context has already exited
    -> "MissingGreenlet: greenlet_spawn has not been called" -> 500 on
    every /api/nodes call.
    """
    return NodeOut(
        id=n.id, name=n.name, host=n.host, ssh_port=n.ssh_port,
        ssh_user=n.ssh_user, group=n.group, status=n.status,
        latency_ms=n.latency_ms, traffic_in=n.traffic_in,
        traffic_out=n.traffic_out, is_active=n.is_active,
        last_check=n.last_check, created_at=n.created_at,
        protocols=protocols,
    )


@router.get("", response_model=list[NodeOut])
async def list_nodes(
    group: Optional[str] = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(Node)
    if group:
        q = q.where(Node.group == group)
    result = await db.execute(q)
    nodes = result.scalars().all()
    out = []
    for n in nodes:
        pr = await db.execute(select(Protocol).where(Protocol.node_id == n.id))
        protocols = [
            {"id": p.id, "name": p.name, "port": p.port, "is_active": p.is_active}
            for p in pr.scalars().all()
        ]
        out.append(_node_out(n, protocols))
    return out


@router.post("", response_model=NodeOut, status_code=201)
async def create_node(
    data: NodeCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    node = Node(**data.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return _node_out(node, [])


@router.post("/check-all")
async def check_all_nodes(
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Trigger async health-check on all active nodes."""
    result = await db.execute(select(Node).where(Node.is_active.is_(True)))
    nodes = result.scalars().all()
    bg.add_task(_check_nodes_bg, [n.id for n in nodes])
    return {"message": f"Health check started for {len(nodes)} nodes"}


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(
    node_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    pr = await db.execute(select(Protocol).where(Protocol.node_id == node.id))
    protocols = [{"id": p.id, "name": p.name, "port": p.port, "is_active": p.is_active}
                 for p in pr.scalars().all()]
    return _node_out(node, protocols)


@router.delete("/{node_id}", status_code=204)
async def delete_node(
    node_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    from app.core.config_writer import is_local_node
    if is_local_node(node):
        raise HTTPException(
            status_code=409,
            detail="The local node cannot be deleted. Disable or delete its protocols, then apply the empty configuration to stop listeners.",
        )
    try:
        await db.execute(delete(Protocol).where(Protocol.node_id == node_id))
        await db.delete(node)
        await db.commit()
    except Exception:
        await db.rollback()
        raise


@router.post("/{node_id}/check")
async def check_node(
    node_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(f"http://{node.host}:80")
        latency = (time.monotonic() - t0) * 1000
        status = "online"
    except Exception:
        latency = None
        status = "offline"

    node.status = status
    node.latency_ms = latency
    node.last_check = datetime.utcnow()
    await db.commit()
    return {"node_id": node_id, "status": status, "latency_ms": latency}


@router.post("/{node_id}/auto-setup")
async def auto_setup(
    node_id: int,
    req: AutoSetupRequest,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    from app.core.config_writer import is_local_node
    if is_local_node(node):
        raise HTTPException(409, {"status": "manual_required", "message": "Use local protocol sync"})
    if req.protocol != "shadowsocks":
        raise HTTPException(409, {"status": "manual_required", "message": "Remote automatic setup is supported only for Shadowsocks"})
    if not node.ssh_key:
        raise HTTPException(status_code=400, detail="SSH key required for auto-setup")

    bg.add_task(_auto_setup_bg, node_id, req.protocol, req.port, req.extra)
    return {"message": f"Auto-setup '{req.protocol}' started on {node.host}", "node_id": node_id}


# ── Background helpers ────────────────────────────────────────────────────────

async def _check_nodes_bg(node_ids: list[int]):
    from app.database import SessionLocal
    async with SessionLocal() as db:
        for nid in node_ids:
            result = await db.execute(select(Node).where(Node.id == nid))
            node = result.scalar_one_or_none()
            if node:
                t0 = time.monotonic()
                try:
                    async with httpx.AsyncClient(timeout=5) as c:
                        await c.get(f"http://{node.host}:80")
                    node.latency_ms = (time.monotonic() - t0) * 1000
                    node.status = "online"
                except Exception:
                    node.status = "offline"
                    node.latency_ms = None
                node.last_check = datetime.utcnow()
        await db.commit()


async def _auto_setup_bg(node_id: int, protocol: str, port: int, extra: dict):
    from app.database import SessionLocal
    async with SessionLocal() as db:
        result = await db.execute(select(Node).where(Node.id == node_id))
        node = result.scalar_one_or_none()
        if not node:
            return
        ssh = None
        try:
            from app.lib.config_generator import ProtocolConfig
            # Generate once before connecting, then deliver and persist this
            # exact configuration. Unsupported setup fails before SSH begins.
            config = ProtocolConfig.defaults(protocol, port, extra)
            commands = _setup_script(protocol, port, config, node.host)
            ssh = SSHClient(node.host, node.ssh_port, node.ssh_user, node.ssh_key)
            await ssh.connect()
            for cmd in commands:
                _, _, code = await ssh.exec(cmd)
                if code != 0:
                    raise RuntimeError("remote_setup_command_failed")

            proto = Protocol(node_id=node_id, name=protocol, port=port, config=config)
            db.add(proto)
            node.status = "online"
            node.meta = {**(node.meta or {}), "last_error": None, "setup_status": "applied"}
            await db.commit()
        except Exception:
            node.status = "error"
            node.meta = {**(node.meta or {}), "last_error": "Remote setup failed; verify SSH access and install the protocol manually", "setup_status": "failed"}
            await db.commit()
        finally:
            if ssh is not None:
                try:
                    await ssh.disconnect()
                except Exception:
                    pass


def _setup_script(protocol: str, port: int, extra: dict, host: str) -> list[str]:
    if protocol != "shadowsocks":
        raise ValueError("Remote protocol setup requires manual configuration")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    password = extra.get("password")
    method = extra.get("method", "aes-256-gcm")
    if not isinstance(password, str) or not password:
        raise ValueError("A generated password is required")
    if method not in ("aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305"):
        raise ValueError("Method is unsupported by shadowsocks-libev")
    config = {"server": "0.0.0.0", "server_port": port, "method": method,
              "password": password, "timeout": 300, "mode": "tcp_and_udp"}
    encoded = base64.b64encode(json.dumps(config).encode()).decode("ascii")
    return [
        "apt-get install -y -qq shadowsocks-libev",
        f"umask 077; printf '%s' '{encoded}' | base64 -d > /etc/shadowsocks-libev/config.json",
        "systemctl enable shadowsocks-libev && systemctl restart shadowsocks-libev && systemctl is-active --quiet shadowsocks-libev",
    ]
