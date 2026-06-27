"""Subscriptions — per-user config links in 5 formats"""

import base64
import uuid
from datetime import datetime
from typing import Optional

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Subscription, Node, Protocol
from app.api.auth import get_current_user, require_admin
from app.lib.config_generator import ConfigGenerator, Balancer
from app.config import settings

router = APIRouter()

SUPPORTED_FORMATS = {"clash", "singbox", "hiddify", "shadowrocket", "v2rayng", "base64"}


class SubCreate(BaseModel):
    format: str = "singbox"


class SubOut(BaseModel):
    id: int
    user_id: int
    token: str
    format: str
    url: str
    last_fetch: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


def _sub_url(token: str, fmt: str) -> str:
    domain = settings.DOMAIN
    port   = settings.PANEL_PORT
    return f"https://{domain}:{port}/api/subscriptions/fetch/{token}?format={fmt}"


@router.get("/", response_model=list[SubOut])
async def list_subs(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Subscription)
    if not current.is_admin:
        q = q.where(Subscription.user_id == current.id)
    result = await db.execute(q)
    subs = result.scalars().all()
    return [
        SubOut(
            **{k: v for k, v in sub.__dict__.items() if k != "_sa_instance_state"},
            url=_sub_url(sub.token, sub.format),
        )
        for sub in subs
    ]


@router.post("/", response_model=SubOut, status_code=201)
async def create_sub(
    data: SubCreate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.format not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format. Use: {', '.join(SUPPORTED_FORMATS)}")

    sub = Subscription(user_id=current.id, format=data.format)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return SubOut(
        **{k: v for k, v in sub.__dict__.items() if k != "_sa_instance_state"},
        url=_sub_url(sub.token, sub.format),
    )


@router.get("/fetch/{token}")
async def fetch_subscription(
    token: str,
    format: str = "singbox",
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint — clients poll this URL to get updated configs"""
    result = await db.execute(select(Subscription).where(Subscription.token == token))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Check user validity
    user_res = await db.execute(select(User).where(User.id == sub.user_id))
    user = user_res.scalar_one_or_none()
    if not user or not user.is_active or user.is_expired:
        raise HTTPException(status_code=403, detail="Subscription expired or disabled")

    # Get all active nodes with their protocols
    nodes_res = await db.execute(select(Node).where(Node.is_active == True))
    nodes = nodes_res.scalars().all()

    gen = ConfigGenerator(domain=settings.DOMAIN)
    balancer = Balancer(strategy="latency", url="http://www.gstatic.com/generate_204", interval="1m")

    for node in nodes:
        proto_res = await db.execute(
            select(Protocol).where(Protocol.node_id == node.id, Protocol.is_active == True)
        )
        for proto in proto_res.scalars().all():
            gen.add_protocol(
                name=proto.name,
                host=node.host,
                port=proto.port,
                tag=f"{node.name}-{proto.name}",
                **proto.config,
            )

    fmt = format or sub.format
    config_data = gen.generate(fmt, balancer=balancer)

    # Update last_fetch
    sub.last_fetch = datetime.utcnow()
    await db.commit()

    content_types = {
        "clash":        "application/yaml",
        "singbox":      "application/json",
        "hiddify":      "application/json",
        "shadowrocket": "text/plain",
        "v2rayng":      "text/plain",
        "base64":       "text/plain",
    }
    ct = content_types.get(fmt, "text/plain")
    return Response(content=config_data, media_type=ct)


@router.get("/qr/{token}")
async def qr_code(token: str, db: AsyncSession = Depends(get_db)):
    """Return QR-code SVG for subscription URL"""
    result = await db.execute(select(Subscription).where(Subscription.token == token))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404)

    url = _sub_url(sub.token, sub.format)
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")


@router.delete("/{sub_id}", status_code=204)
async def delete_sub(
    sub_id: int,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Subscription).where(Subscription.id == sub_id))
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404)
    if not current.is_admin and sub.user_id != current.id:
        raise HTTPException(status_code=403)
    await db.delete(sub)
    await db.commit()
