"""Protocol CRUD + config preview + server config sync"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Protocol, Node
from app.api.auth import require_admin, User
from app.lib.config_generator import ConfigGenerator, Balancer, ProtocolConfig
from app.config import settings

router = APIRouter()


class ProtocolCreate(BaseModel):
    node_id: int
    name: str
    port: int
    config: dict = {}


class ProtocolOut(BaseModel):
    id: int
    node_id: int
    name: str
    port: int
    is_active: bool
    config: dict
    model_config = {"from_attributes": True}


class ConfigPreviewRequest(BaseModel):
    format: str = "singbox"
    protocol: str
    host: str
    port: int
    config: dict = {}


async def _sync_node(node_id: int):
    """Background task: rebuild Xray/Sing-box server configs after protocol change."""
    try:
        from app.core.config_writer import sync_node_config
        result = await sync_node_config(node_id)
        import logging
        logging.getLogger("fvpn.protocols").info(
            f"Node {node_id} config sync: xray={result['xray']} singbox={result['singbox']}"
        )
    except Exception as e:
        import logging
        logging.getLogger("fvpn.protocols").error(f"Config sync failed for node {node_id}: {e}")


@router.get("/", response_model=list[ProtocolOut])
async def list_protocols(
    node_id: Optional[int] = None,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    q = select(Protocol)
    if node_id:
        q = q.where(Protocol.node_id == node_id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=ProtocolOut, status_code=201)
async def create_protocol(
    data: ProtocolCreate,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    node_res = await db.execute(select(Node).where(Node.id == data.node_id))
    if not node_res.scalar_one_or_none():
        raise HTTPException(404, "Node not found")

    merged = ProtocolConfig.defaults(data.name, data.port, data.config)
    proto = Protocol(node_id=data.node_id, name=data.name, port=data.port, config=merged)
    db.add(proto)
    await db.commit()
    await db.refresh(proto)

    # Rebuild server-side Xray/Sing-box configs in background
    bg.add_task(_sync_node, data.node_id)
    return proto


@router.patch("/{proto_id}", response_model=ProtocolOut)
async def update_protocol(
    proto_id: int,
    data: dict,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Protocol).where(Protocol.id == proto_id))
    proto = result.scalar_one_or_none()
    if not proto:
        raise HTTPException(404)
    for k, v in data.items():
        if hasattr(proto, k):
            setattr(proto, k, v)
    await db.commit()
    await db.refresh(proto)
    bg.add_task(_sync_node, proto.node_id)
    return proto


@router.delete("/{proto_id}", status_code=204)
async def delete_protocol(
    proto_id: int,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Protocol).where(Protocol.id == proto_id))
    proto = result.scalar_one_or_none()
    if not proto:
        raise HTTPException(404)
    node_id = proto.node_id
    await db.delete(proto)
    await db.commit()
    bg.add_task(_sync_node, node_id)


@router.post("/preview")
async def preview_config(
    req: ConfigPreviewRequest,
    _: User = Depends(require_admin),
):
    """Live config preview — no DB write, no server reload."""
    gen = ConfigGenerator(domain=settings.DOMAIN)
    cfg = ProtocolConfig.defaults(req.protocol, req.port, req.config)
    gen.add_protocol(req.protocol, req.host, req.port, tag=f"{req.protocol}-preview", **cfg)
    try:
        result = gen.generate(req.format, balancer=Balancer())
        return {"config": result, "errors": gen.validate(), "format": req.format}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sync/{node_id}")
async def force_sync(
    node_id: int,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger server config rebuild for a node."""
    node_res = await db.execute(select(Node).where(Node.id == node_id))
    if not node_res.scalar_one_or_none():
        raise HTTPException(404, "Node not found")
    bg.add_task(_sync_node, node_id)
    return {"message": f"Config sync triggered for node {node_id}"}


@router.get("/supported")
async def supported_protocols(_: User = Depends(require_admin)):
    return {
        "protocols": [
            {"name": "hysteria2",    "core": "sing-box", "description": "QUIC/HTTP3, port-hopping"},
            {"name": "shadowsocks",  "core": "both",     "description": "SS-2022 + aes-256-gcm"},
            {"name": "shadowtls",    "core": "sing-box", "description": "TLS SNI camouflage v3"},
            {"name": "vless",        "core": "xray",     "description": "XTLS-Vision + Reality"},
            {"name": "trojan",       "core": "xray",     "description": "HTTPS traffic mimicry"},
            {"name": "tuic",         "core": "sing-box", "description": "QUIC, BBR, 0-RTT"},
            {"name": "wireguard",    "core": "sing-box", "description": "ChaCha20-Poly1305 VPN"},
            {"name": "ssh",          "core": "xray",     "description": "Legacy SSH tunnel"},
        ],
        "formats": ["singbox", "clash", "hiddify", "shadowrocket", "v2rayng", "base64"],
    }
