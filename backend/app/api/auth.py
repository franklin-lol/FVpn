"""Auth endpoints"""

import time
import hashlib
import math
from dataclasses import dataclass
from ipaddress import ip_address

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import settings
from app.models import SetupState, User
from app.core.security import async_hash_password, async_verify_password, create_access_token, decode_token
from pydantic import BaseModel, SecretStr

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


_MAX_ATTEMPTS = 5
_LOCKOUT_SEC = 900


@dataclass
class LoginAttempt:
    sequence: int
    created: float
    address: str
    account: str
    failed: bool = False


class LoginLimiter:
    """Bounded, process-local reservations for the single event-loop worker.

    Reserve synchronously before the first await. Pending requests count toward
    both limits; denied requests never refresh TTL. Capacity exhaustion rejects
    new keys rather than evicting active limits under attacker key churn.
    """

    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self.accounts: dict[str, list[LoginAttempt]] = {}
        self.addresses: dict[str, list[LoginAttempt]] = {}
        self._sequence = 0
        self._next_cleanup = 0.0

    @staticmethod
    def _denied(retry: float) -> None:
        seconds = max(1, math.ceil(retry))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(seconds)},
        )

    def _cleanup(self, now: float) -> None:
        for store in (self.accounts, self.addresses):
            for key, attempts in list(store.items()):
                live = [attempt for attempt in attempts if now - attempt.created < _LOCKOUT_SEC]
                if live:
                    store[key] = live
                else:
                    del store[key]
        self._next_cleanup = now + 30

    def reserve(self, address: str, username: str) -> LoginAttempt:
        now = time.monotonic()
        # Bound key size even for hostile form values; exact usernames remain
        # case-sensitive, matching the database's authentication semantics.
        account = hashlib.sha256(username.encode("utf-8")).hexdigest()
        if now >= self._next_cleanup or any(
            len(store) >= self.capacity for store in (self.accounts, self.addresses)
        ):
            self._cleanup(now)
        for store, key in ((self.accounts, account), (self.addresses, address)):
            attempts = [a for a in store.get(key, []) if now - a.created < _LOCKOUT_SEC]
            if len(attempts) >= _MAX_ATTEMPTS:
                self._denied(_LOCKOUT_SEC - (now - attempts[0].created))
            if key not in store and len(store) >= self.capacity:
                self._denied(_LOCKOUT_SEC)
        self._sequence += 1
        attempt = LoginAttempt(self._sequence, now, address, account)
        for store, key in ((self.accounts, account), (self.addresses, address)):
            store[key] = [a for a in store.get(key, []) if now - a.created < _LOCKOUT_SEC]
            store[key].append(attempt)
        return attempt

    def release(self, attempt: LoginAttempt, *, success: bool = False) -> None:
        for store, key in ((self.accounts, attempt.account), (self.addresses, attempt.address)):
            remaining = [
                a for a in store.get(key, [])
                if not (
                    a.sequence == attempt.sequence
                    or (success and a.failed and a.address == attempt.address and a.account == attempt.account
                        and a.sequence < attempt.sequence)
                )
            ]
            if remaining:
                store[key] = remaining
            else:
                store.pop(key, None)


_limiter = LoginLimiter()


def _client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    try:
        peer = str(ip_address(peer))
    except ValueError:
        return peer
    real = request.headers.getlist("x-real-ip")
    if peer in settings.trusted_proxy_ips and len(real) == 1:
        try:
            return str(ip_address(real[0]))
        except ValueError:
            pass
    return peer


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    attempt = _limiter.reserve(_client_ip(request), form.username)
    try:
        result = await db.execute(select(User).where(User.username == form.username))
        user = result.scalar_one_or_none()
        valid = bool(user and await async_verify_password(form.password, user.hashed_password))
    except BaseException:
        # Infrastructure errors/cancellation are not credential failures.
        _limiter.release(attempt)
        raise
    if not valid:
        attempt.failed = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        attempt.failed = True
        raise HTTPException(status_code=403, detail="Account disabled")

    _limiter.release(attempt, success=True)
    token = create_access_token({"sub": user.username, "admin": user.is_admin})
    return Token(access_token=token, username=user.username, is_admin=user.is_admin)


async def get_current_user(token: str = Depends(oauth2), db: AsyncSession = Depends(get_db)) -> User:
    username = decode_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin required")
    return user


class PasswordChange(BaseModel):
    model_config = {"extra": "forbid"}
    current_password: SecretStr
    new_password: SecretStr


@router.post("/password")
async def change_password(
    data: PasswordChange,
    request: Request,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    password = data.new_password.get_secret_value()
    if len(password) < 12 or len(password.encode("utf-8")) > 72:
        raise HTTPException(422, "New password must have at least 12 characters and at most 72 UTF-8 bytes")
    if password == data.current_password.get_secret_value():
        raise HTTPException(422, "Choose a new password different from the current password")
    attempt = _limiter.reserve(_client_ip(request), current.username)
    try:
        valid = await async_verify_password(data.current_password.get_secret_value(), current.hashed_password)
        if valid:
            hashed = await async_hash_password(password)
    except BaseException:
        _limiter.release(attempt)
        raise
    if not valid:
        attempt.failed = True
        raise HTTPException(401, "Current password is incorrect")
    # Compare the verified hash in SQL so overlapping changes cannot silently
    # replace a password which changed while bcrypt ran in a worker thread.
    changed = await db.execute(update(User).where(
        User.id == current.id, User.is_active.is_(True),
        User.hashed_password == current.hashed_password,
    ).values(hashed_password=hashed).execution_options(synchronize_session=False))
    if changed.rowcount != 1:
        await db.rollback()
        _limiter.release(attempt)
        raise HTTPException(409, "Password changed during this request; sign in again and retry")
    state = await db.get(SetupState, 1)
    if state is not None and state.required and current.is_admin and state.admin_user_id == current.id:
        state.password_changed = True
    await db.commit()
    _limiter.release(attempt, success=True)
    return {"status": "password_changed"}
