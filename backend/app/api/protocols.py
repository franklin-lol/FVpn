"""Protocol CRUD + config preview + server config sync"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field, JsonValue, field_validator
from typing import Annotated, Literal, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Protocol, Node
from app.api.auth import require_admin, User
from app.lib.config_generator import ConfigGenerator, Balancer, ProtocolConfig
from app.config import settings

router = APIRouter()

ProtocolName = Literal["hysteria2", "shadowsocks", "shadowtls", "vless", "trojan", "tuic", "wireguard", "ssh", "vmess"]
Port = Annotated[int, Field(strict=True, ge=1, le=65535)]
TextOption = Annotated[str, Field(strict=True, max_length=4096)]


class ProtocolOptions(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    password: TextOption | None = None
    uuid: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")] | None = None
    private_key: TextOption | None = None
    public_key: TextOption | None = None
    client_public_key: TextOption | None = None
    preshared_key: TextOption | None = None
    short_id: Annotated[str, Field(pattern=r"^(?:[0-9a-fA-F]{2}){0,8}$")] | None = None
    sni: Annotated[str, Field(min_length=1, max_length=253, pattern=r"^[a-zA-Z0-9.-]+$")] | None = None
    method: Literal["aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305"] | None = None
    flow: Literal["", "xtls-rprx-vision"] | None = None
    obfs: Literal["", "salamander"] | None = None
    obfs_password: TextOption | None = None
    tls_insecure: bool | None = None
    congestion: Literal["bbr", "cubic", "new_reno"] | None = None
    version: Literal[3] | None = None
    ss_port: Port | None = None
    path: Annotated[str, Field(min_length=1, max_length=2048, pattern=r"^/")] | None = None
    cert_path: Literal["/etc/fvpn/ssl/cert.pem"] | None = None
    key_path: Literal["/etc/fvpn/ssl/key.pem"] | None = None
    username: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    dns: Annotated[str, Field(max_length=253)] | None = None
    mtu: Annotated[int, Field(ge=576, le=9000)] | None = None

    @field_validator("*")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Option cannot be null")
        return value


def validate_options(value: dict[str, JsonValue]) -> dict[str, JsonValue]:
    ProtocolOptions.model_validate(value)
    return value


class ProtocolInput(BaseModel):
    model_config = {"extra": "forbid"}

    @field_validator("config", check_fields=False)
    @classmethod
    def validate_config_options(cls, value):
        if value is not None:
            validate_options(value)
        return value


class ProtocolCreate(ProtocolInput):
    node_id: Annotated[int, Field(strict=True, ge=1)]
    name: ProtocolName
    port: Port
    config: dict[str, JsonValue] = Field(default_factory=dict)


class ProtocolUpdate(ProtocolInput):
    name: ProtocolName | None = None
    port: Port | None = None
    is_active: Annotated[bool, Field(strict=True)] | None = None
    config: dict[str, JsonValue] | None = None

    @field_validator("name", "port", "is_active", "config")
    @classmethod
    def reject_null(cls, value):
        if value is None:
            raise ValueError("Field cannot be null")
        return value


class ProtocolOut(BaseModel):
    id: int
    node_id: int
    name: str
    port: int
    is_active: bool
    config: dict
    model_config = {"from_attributes": True}


class ConfigPreviewRequest(ProtocolInput):
    format: Literal["singbox", "sing-box", "clash", "hiddify", "shadowrocket", "v2rayng", "base64"] = "singbox"
    protocol: ProtocolName
    host: Annotated[str, Field(min_length=1, max_length=253)]
    port: Port
    config: dict[str, JsonValue] = Field(default_factory=dict)


async def _sync_node(node_id: int):
    try:
        from app.core.config_writer import sync_node_config
        result = await sync_node_config(node_id)
        import logging
        log = logging.getLogger("fvpn.protocols")
        level = logging.INFO if result.get("status") == "applied" else logging.WARNING
        log.log(level, "Node %s sync: %s", node_id, result.get("status", "failed"))
    except Exception:
        import logging
        logging.getLogger("fvpn.protocols").error("Config sync failed for node %s", node_id)


@router.get("", response_model=list[ProtocolOut])
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


@router.post("", response_model=ProtocolOut, status_code=201)
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
    bg.add_task(_sync_node, data.node_id)
    return proto


@router.patch("/{proto_id}", response_model=ProtocolOut)
async def update_protocol(
    proto_id: int,
    data: ProtocolUpdate,
    bg: BackgroundTasks,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Protocol).where(Protocol.id == proto_id))
    proto = result.scalar_one_or_none()
    if not proto:
        raise HTTPException(404)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(proto, key, value)
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
    node_res = await db.execute(select(Node).where(Node.id == node_id))
    node = node_res.scalar_one_or_none()
    if not node:
        raise HTTPException(404, "Node not found")
    from app.core.config_writer import is_local_node
    if not is_local_node(node):
        raise HTTPException(409, {"status": "manual_required", "message": "Export and apply remote configuration manually"})
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
