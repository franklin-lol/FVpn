"""Protocol CRUD + config preview"""

from fastapi import APIRouter, Depends, HTTPException
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
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Validate node exists
    node_res = await db.execute(select(Node).where(Node.id == data.node_id))
    if not node_res.scalar_one_or_none():
        raise HTTPException(404, "Node not found")

    # Fill in defaults for any missing keys
    merged_config = ProtocolConfig.defaults(data.name, data.port, data.config)
    proto = Protocol(
        node_id=data.node_id,
        name=data.name,
        port=data.port,
        config=merged_config,
    )
    db.add(proto)
    await db.commit()
    await db.refresh(proto)
    return proto


@router.patch("/{proto_id}", response_model=ProtocolOut)
async def update_protocol(
    proto_id: int,
    data: dict,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Protocol).where(Protocol.id == proto_id))
    proto = result.scalar_one_or_none()
    if not proto:
        raise HTTPException(404, "Protocol not found")
    for k, v in data.items():
        if hasattr(proto, k):
            setattr(proto, k, v)
    await db.commit()
    await db.refresh(proto)
    return proto


@router.delete("/{proto_id}", status_code=204)
async def delete_protocol(
    proto_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Protocol).where(Protocol.id == proto_id))
    proto = result.scalar_one_or_none()
    if not proto:
        raise HTTPException(404)
    await db.delete(proto)
    await db.commit()


@router.post("/preview")
async def preview_config(
    req: ConfigPreviewRequest,
    _: User = Depends(require_admin),
):
    """Generate single-protocol config preview without saving"""
    gen = ConfigGenerator(domain=settings.DOMAIN)
    cfg = ProtocolConfig.defaults(req.protocol, req.port, req.config)
    gen.add_protocol(req.protocol, req.host, req.port, tag=f"{req.protocol}-preview", **cfg)
    bl = Balancer()
    try:
        result = gen.generate(req.format, balancer=bl)
        errors = gen.validate()
        return {"config": result, "errors": errors, "format": req.format}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/supported")
async def supported_protocols(_: User = Depends(require_admin)):
    return {
        "protocols": [
            {"name": "hysteria2",    "description": "HTTP/3 based, high performance, port-hopping capable"},
            {"name": "shadowsocks",  "description": "Symmetric cipher obfuscation, SS-2022 supported"},
            {"name": "shadowtls",    "description": "TLS traffic camouflage via SNI fronting"},
            {"name": "vless",        "description": "VLESS + XTLS-Reality (zero TLS overhead)"},
            {"name": "trojan",       "description": "TLS-based mimicking HTTPS traffic"},
            {"name": "tuic",         "description": "QUIC-based, multiplexed, BBR congestion"},
            {"name": "wireguard",    "description": "Kernel-level VPN, state-of-the-art encryption"},
            {"name": "ssh",          "description": "SSH tunnel (legacy fallback)"},
        ],
        "formats": ["singbox", "clash", "hiddify", "shadowrocket", "v2rayng", "base64"],
    }
