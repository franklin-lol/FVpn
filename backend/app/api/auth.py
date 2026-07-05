"""Auth endpoints"""

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User
from app.core.security import verify_password, create_access_token, decode_token
from pydantic import BaseModel

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


# --- brute-force lockout -----------------------------------------------
# In-process sliding window keyed by (client_ip, username). Correct as a
# single-process store now that the backend runs one uvicorn worker
# (--workers 1); would need Redis instead if that ever changes.
_FAILS: dict[tuple[str, str], list[float]] = defaultdict(list)
_MAX_ATTEMPTS  = 5
_WINDOW_SEC    = 300   # 5 min
_LOCKOUT_SEC   = 900   # 15 min once tripped


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def _check_lockout(key: tuple[str, str]) -> None:
    now = time.time()
    attempts = [t for t in _FAILS[key] if now - t < _LOCKOUT_SEC]
    _FAILS[key] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        retry_after = int(_LOCKOUT_SEC - (now - attempts[0]))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {retry_after}s.",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _record_fail(key: tuple[str, str]) -> None:
    _FAILS[key].append(time.time())


def _clear(key: tuple[str, str]) -> None:
    _FAILS.pop(key, None)


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    key = (_client_ip(request), form.username)
    _check_lockout(key)

    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        _record_fail(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    _clear(key)
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
