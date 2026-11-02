"""Security: JWT auth + password hashing"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Optional, TypeVar

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
_PASSWORD_CONCURRENCY = asyncio.Semaphore(4)
_T = TypeVar("_T")


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


async def _password_work(function: Callable[..., _T], *args: str) -> _T:
    # A cancelled request must retain its permit until bcrypt's thread exits.
    async with _PASSWORD_CONCURRENCY:
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
            # Retrieve any thread exception before propagating cancellation.
            task.exception()
            raise


async def async_hash_password(password: str) -> str:
    return await _password_work(hash_password, password)


async def async_verify_password(plain: str, hashed: str) -> bool:
    return await _password_work(verify_password, plain, hashed)


def create_access_token(data: dict, expire_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expire_minutes or settings.JWT_EXPIRE_MINUTES
    )
    payload = {**data, "exp": expire, "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def decode_token(token: str) -> Optional[str]:
    """Returns username from valid token or None"""
    payload = verify_token(token)
    if payload:
        return payload.get("sub")
    return None
