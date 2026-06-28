"""Nodes management — CRUD + SSH auto-setup"""

import asyncio
import json
import time
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Node, Protocol
from app.api.auth import require_admin, User
from app.core.ssh import SSHClient
from app.config import settings

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
    protocol: str          # hysteria2 | shadowsocks | vless | trojan | tuic | wireguard
    port: int = 443
    extra: dict = {}       # protocol-specific overrides


@router.get("/", response_model=list[NodeOut])
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
        protocols = [{"id": p.id, "name": p.name, "port": p.port, "is_active": p.is_active}
                     for p in pr.scalars().all()]
        d = NodeOut.model_validate(n)
        d.protocols = protocols
        out.append(d)
    return out


@router.post("/", response_model=NodeOut, status_code=201)
async def create_node(
    data: NodeCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    node = Node(**data.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(node_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.delete("/{node_id}", status_code=204)
async def delete_node(node_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    await db.delete(node)
    await db.commit()


@router.post("/{node_id}/check")
async def check_node(node_id: int, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Ping node and measure latency"""
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"http://{node.host}:80")
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


@router.post("/check-all")
async def check_all_nodes(
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Async check all nodes in background"""
    result = await db.execute(select(Node).where(Node.is_active == True))
    nodes = result.scalars().all()
    bg.add_task(_check_nodes_bg, [n.id for n in nodes])
    return {"message": f"Health check started for {len(nodes)} nodes"}


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


@router.post("/{node_id}/auto-setup")
async def auto_setup(
    node_id: int,
    req: AutoSetupRequest,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """SSH into node and auto-install + configure protocol"""
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if not node.ssh_key:
        raise HTTPException(status_code=400, detail="SSH key required for auto-setup")

    bg.add_task(_auto_setup_bg, node_id, req.protocol, req.port, req.extra)
    return {"message": f"Auto-setup '{req.protocol}' started on {node.host}", "node_id": node_id}


async def _auto_setup_bg(node_id: int, protocol: str, port: int, extra: dict):
    from app.database import SessionLocal
    async with SessionLocal() as db:
        result = await db.execute(select(Node).where(Node.id == node_id))
        node = result.scalar_one_or_none()
        if not node:
            return

        try:
            ssh = SSHClient(node.host, node.ssh_port, node.ssh_user, node.ssh_key)
            await ssh.connect()

            scripts = _get_setup_script(protocol, port, extra, node.host)
            for cmd in scripts:
                stdout, stderr, code = await ssh.exec(cmd)
                if code != 0:
                    raise RuntimeError(f"SSH cmd failed [{code}]: {stderr}")

            await ssh.disconnect()

            # Save protocol to DB
            from app.lib.config_generator import ProtocolConfig
            config = ProtocolConfig.defaults(protocol, port, extra)
            proto = Protocol(node_id=node_id, name=protocol, port=port, config=config)
            db.add(proto)
            node.status = "online"
            await db.commit()
        except Exception as e:
            node.status = "error"
            node.meta = {**(node.meta or {}), "last_error": str(e)}
            await db.commit()


def _get_setup_script(protocol: str, port: int, extra: dict, host: str) -> list[str]:
    scripts = {
        "hysteria2": [
            "apt-get install -y -qq curl",
            "bash <(curl -fsSL https://get.hy2.sh/)",
            f"hy2 setup --port {port} --password {extra.get('password', 'UniProxyH2')} --acme {host}",
            "systemctl enable hysteria-server --now",
        ],
        "shadowsocks": [
            "apt-get install -y -qq shadowsocks-libev",
            f"bash -c \"cat > /etc/shadowsocks-libev/config.json << 'EOF'\n"
            f'{{\"server\":\"0.0.0.0\",\"server_port\":{port},\"method\":\"{extra.get("method","aes-256-gcm")}\",\"password\":\"{extra.get("password","UniProxy2024")}\",\"timeout\":300}}\n'
            "EOF\"",
            "systemctl enable shadowsocks-libev --now",
        ],
        "vless": [
            "bash <(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)",
            "systemctl enable xray --now",
        ],
        "wireguard": [
            "apt-get install -y -qq wireguard",
            "wg genkey | tee /etc/wireguard/private.key | wg pubkey > /etc/wireguard/public.key",
            "chmod 600 /etc/wireguard/private.key",
            f"bash -c 'echo \"[Interface]\\nAddress=10.0.0.1/24\\nListenPort={port}\\nPrivateKey=$(cat /etc/wireguard/private.key)\" > /etc/wireguard/wg0.conf'",
            "systemctl enable wg-quick@wg0 --now",
        ],
    }
    return scripts.get(protocol, [f"echo 'Protocol {protocol} setup not implemented'"])
