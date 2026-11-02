"""Subscriptions and token-scoped connection metadata."""

import base64
from datetime import datetime, timezone
from typing import Annotated, Optional

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, Subscription, Node, Protocol
from app.api.auth import get_current_user
from app.lib.config_generator import ConfigGenerator, Balancer
from app.config import settings

router = APIRouter()

SUPPORTED_FORMATS = ("singbox", "hiddify", "clash", "shadowrocket", "v2rayng", "base64")
NO_STORE = {"Cache-Control": "no-store"}


class SubCreate(BaseModel):
    format: str = "singbox"
    user_id: Annotated[int, Field(strict=True, gt=0)] | None = None


class SubOut(BaseModel):
    id: int
    user_id: int
    token: str
    format: str
    url: str
    connect_url: str
    last_fetch: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SubInfo(BaseModel):
    format: str
    url: str
    connect_url: str
    expires_at: datetime | None
    available_formats: list[str]


def _sub_url(token: str, fmt: str) -> str:
    return f"https://{settings.DOMAIN}:{settings.PANEL_PORT}/api/subscriptions/fetch/{token}?format={fmt}"


def _connect_url(token: str) -> str:
    return f"https://{settings.DOMAIN}:{settings.PANEL_PORT}/s/{token}"


def _sub_out(sub: Subscription) -> SubOut:
    return SubOut(
        id=sub.id, user_id=sub.user_id, token=sub.token, format=sub.format,
        url=_sub_url(sub.token, sub.format), connect_url=_connect_url(sub.token),
        last_fetch=sub.last_fetch, created_at=sub.created_at,
    )


async def _public_subscription(token: str, db: AsyncSession) -> tuple[Subscription, User]:
    row = (await db.execute(
        select(Subscription, User).outerjoin(User, User.id == Subscription.user_id)
        .where(Subscription.token == token)
    )).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Subscription not found", headers=NO_STORE)
    sub, user = row
    if user is None or not user.is_active or user.is_expired:
        raise HTTPException(status_code=403, detail="Subscription expired or disabled", headers=NO_STORE)
    return sub, user


async def _client_generator(db: AsyncSession) -> ConfigGenerator:
    rows = (await db.execute(
        select(Protocol, Node).join(Node, Protocol.node_id == Node.id)
        .where(Node.is_active.is_(True), Protocol.is_active.is_(True))
        .order_by(Node.id, Protocol.id)
    )).all()
    generator = ConfigGenerator(domain=settings.DOMAIN)
    for protocol, node in rows:
        generator.add_protocol(
            name=protocol.name, host=node.host, port=protocol.port,
            tag=f"{node.name}-{protocol.name}-{protocol.id}", **protocol.config,
        )
    return generator


@router.get("", response_model=list[SubOut])
@router.get("/", response_model=list[SubOut], include_in_schema=False)
async def list_subs(
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Subscription)
    if not current.is_admin:
        q = q.where(Subscription.user_id == current.id)
    result = await db.execute(q)
    subs = result.scalars().all()
    return [_sub_out(sub) for sub in subs]


@router.post("", response_model=SubOut, status_code=201)
@router.post("/", response_model=SubOut, status_code=201, include_in_schema=False)
async def create_sub(
    data: SubCreate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if data.format not in SUPPORTED_FORMATS:
        raise HTTPException(400, f"Unsupported format. Use: {', '.join(SUPPORTED_FORMATS)}")

    owner_id = current.id if data.user_id is None else data.user_id
    if owner_id != current.id:
        if not current.is_admin:
            raise HTTPException(status_code=403, detail="Only administrators may select another subscription owner")
        if await db.get(User, owner_id) is None:
            raise HTTPException(status_code=404, detail="Subscription owner not found")
    sub = Subscription(user_id=owner_id, format=data.format)
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return _sub_out(sub)


@router.get("/info/{token}", response_model=SubInfo)
async def subscription_info(token: str, response: Response, db: AsyncSession = Depends(get_db)):
    sub, user = await _public_subscription(token, db)
    generator = await _client_generator(db)
    available = []
    for fmt in SUPPORTED_FORMATS:
        try:
            generator.generate(fmt)
        except ValueError:
            continue
        available.append(fmt)
    response.headers.update(NO_STORE)
    expires_at = user.expire_at.replace(tzinfo=timezone.utc) if user.expire_at else None
    return SubInfo(
        format=sub.format, url=_sub_url(sub.token, sub.format), connect_url=_connect_url(sub.token),
        expires_at=expires_at, available_formats=available,
    )


@router.get("/fetch/{token}")
async def fetch_subscription(
    token: str,
    format: str = "singbox",
    db: AsyncSession = Depends(get_db),
):
    sub, user = await _public_subscription(token, db)
    gen = await _client_generator(db)
    balancer = Balancer(strategy="latency", url="http://www.gstatic.com/generate_204", interval="1m")

    fmt = format or sub.format
    try:
        config_data = gen.generate(fmt, balancer=balancer)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error), headers=NO_STORE) from None

    sub.last_fetch = datetime.utcnow()
    await db.commit()

    content_types = {
        "clash": "application/yaml", "singbox": "application/json",
        "hiddify": "application/json", "shadowrocket": "text/plain",
        "v2rayng": "text/plain", "base64": "text/plain",
    }

    # Standard sing-box / Hiddify / Clash-Meta subscription headers.
    # Without Profile-Title, the client has no display name to show and
    # falls back to rendering the raw subscription URL/token as the name
    # in the app's server list — exactly the "name == link" symptom.
    profile_title = base64.b64encode(f"FVpn-{user.username}".encode()).decode()
    limit_bytes = int(user.traffic_limit_gb * 1e9) if user.traffic_limit_gb else 0
    used_bytes = int(user.traffic_used_gb * 1e9)
    expire_ts = int(user.expire_at.timestamp()) if user.expire_at else 0

    headers = {
        **NO_STORE,
        "Profile-Title": f"base64:{profile_title}",
        "Profile-Update-Interval": "12",
        "Subscription-Userinfo": (
            f"upload=0; download={used_bytes}; total={limit_bytes}; expire={expire_ts}"
        ),
    }

    return Response(content=config_data, media_type=content_types.get(fmt, "text/plain"), headers=headers)


@router.get("/qr/{token}")
async def qr_code(token: str, db: AsyncSession = Depends(get_db)):
    sub, _ = await _public_subscription(token, db)

    url = _sub_url(sub.token, sub.format)
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgImage)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml", headers=NO_STORE)


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
