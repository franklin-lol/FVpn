"""Additive onboarding state and retry-safe local preset application."""

import asyncio
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import require_admin
from app.core import config_writer
from app.database import get_db
from app.lib.config_generator import ConfigGenerator, ProtocolConfig
from app.models import Node, Protocol, SetupState, User

router = APIRouter()
# One backend worker; serialize preset creation, apply and completion together.
_SETUP_LOCK = asyncio.Lock()


class SetupNode(BaseModel):
    id: int
    name: str
    host: str
    local: bool


class SetupStatus(BaseModel):
    required: bool
    password_changed: bool
    local_node_id: int | None
    recommended_ready: bool
    nodes: list[SetupNode]


class SetupComplete(BaseModel):
    model_config = {"extra": "forbid"}
    node_id: Annotated[int, Field(strict=True, gt=0)]
    preset: Literal["recommended", "existing"]


def _client_supported(node: Node, protocols: list[Protocol]) -> bool:
    generator = ConfigGenerator()
    try:
        for protocol in protocols:
            name = protocol.name.lower().replace("-", "")
            required = {
                "vless": ("uuid", "public_key", "sni"),
                "vlessreality": ("uuid", "public_key", "sni"),
                "shadowsocks": ("password",), "shadowtls": ("password",),
                "hysteria2": ("password",), "trojan": ("password",),
                "tuic": ("uuid", "password"), "ssh": ("username", "private_key"),
            }.get(name)
            if name in {"vless", "vlessreality"} and config_writer.is_local_node(node):
                required = (*required, "private_key")
            config = protocol.config or {}
            if required is not None and all(isinstance(config.get(key), str) and config[key].strip() for key in required):
                generator.add_protocol(protocol.name, node.host, protocol.port, **config)
        generator.generate("singbox")
    except (ValueError, TypeError):
        return False
    return True


@router.get("", response_model=SetupStatus)
async def get_setup(
    _: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    state = await db.get(SetupState, 1)
    nodes = (await db.execute(select(Node).where(Node.is_active.is_(True)).order_by(Node.id))).scalars().all()
    local = next((node for node in nodes if config_writer.is_local_node(node)), None)
    ready = False
    if local is not None:
        rows = (await db.execute(select(Protocol).where(
            Protocol.node_id == local.id, Protocol.is_active.is_(True),
            Protocol.name.in_(["vless", "vless-reality", "vlessreality"]),
        ))).scalars().all()
        ready = _client_supported(local, rows)
    return SetupStatus(
        required=state.required if state else False,
        password_changed=state.password_changed if state else True,
        local_node_id=local.id if local else None,
        recommended_ready=ready,
        nodes=[SetupNode(id=node.id, name=node.name, host=node.host,
                         local=config_writer.is_local_node(node)) for node in nodes],
    )


@router.post("/complete")
async def complete_setup(
    data: SetupComplete, _: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    async with _SETUP_LOCK:
        state = await db.get(SetupState, 1, populate_existing=True)
        if state is None or not state.required:
            return {"status": "configured"}
        if not state.password_changed:
            raise HTTPException(409, "Change the initial administrator password before completing setup")
        node = await db.get(Node, data.node_id)
        if node is None:
            raise HTTPException(404, "Node not found")
        if not node.is_active:
            raise HTTPException(409, "Enable the selected node before completing setup")
        local = config_writer.is_local_node(node)
        protocols = (await db.execute(select(Protocol).where(Protocol.node_id == node.id))).scalars().all()
        if data.preset == "recommended":
            if not local:
                raise HTTPException(409, "Recommended setup requires a local node; configure remote nodes manually")
            reality = next((p for p in protocols if p.name.lower().replace("-", "") in {"vless", "vlessreality"}), None)
            if reality is None:
                if any(p.is_active and p.port == 443 for p in protocols):
                    raise HTTPException(409, "Port 443 is already configured; select existing settings or change its protocol")
                reality = Protocol(node_id=node.id, name="vless", port=443,
                                   config=ProtocolConfig.defaults("vless", 443, {}), is_active=True)
                db.add(reality)
            else:
                if not _client_supported(node, [reality]):
                    raise HTTPException(409, "Existing VLESS credentials are incomplete; repair its configuration before retrying setup")
                reality.is_active = True
            # Persist once so failed application retries reuse these credentials.
            await db.commit()
        elif not _client_supported(node, [p for p in protocols if p.is_active]):
            raise HTTPException(409, "Enable a supported client protocol on the selected node first")
        if local:
            result = await config_writer.sync_node_config(node.id)
            if result.get("status") != "applied":
                raise HTTPException(409, "Configuration could not be applied; review protocols and retry setup")
        state.required = False
        await db.commit()
        return {"status": "configured"}
