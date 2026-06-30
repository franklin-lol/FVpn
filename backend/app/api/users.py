"""Users CRUD API"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.core.security import hash_password
from app.api.auth import get_current_user, require_admin

router = APIRouter()


class UserCreate(BaseModel):
    username: str
    email: Optional[str] = None
    password: str
    traffic_limit_gb: float = 0.0
    expire_at: Optional[datetime] = None
    is_admin: bool = False


class UserUpdate(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    traffic_limit_gb: Optional[float] = None
    expire_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    uuid: str
    username: str
    email: Optional[str]
    is_admin: bool
    is_active: bool
    traffic_limit_gb: float
    traffic_used_gb: float
    # Optional, not float: the ORM property returns None for unlimited users
    # (traffic_limit_gb == 0) instead of float('inf'), which plain JSON cannot
    # encode. Returning `null` here is what every client already expects from
    # an "unlimited" sentinel — frontend already treats limit===0 as unlimited.
    traffic_remaining_gb: Optional[float] = None
    expire_at: Optional[datetime]
    is_expired: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[UserOut])
async def list_users(
    skip: int = 0, limit: int = 100,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).offset(skip).limit(limit))
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    data: UserCreate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        traffic_limit_gb=data.traffic_limit_gb,
        expire_at=data.expire_at,
        is_admin=data.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/me", response_model=UserOut)
async def get_me(current: User = Depends(get_current_user)):
    return current


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in data.model_dump(exclude_none=True).items():
        if field == "password":
            setattr(user, "hashed_password", hash_password(value))
        else:
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()


@router.post("/{user_id}/reset-traffic", response_model=UserOut)
async def reset_traffic(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.traffic_used_gb = 0.0
    await db.commit()
    await db.refresh(user)
    return user
