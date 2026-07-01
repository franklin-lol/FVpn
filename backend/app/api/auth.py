"""Auth endpoints"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from backend.app import User
from app.core.security import verify_password, create_access_token, decode_token
from pydantic import BaseModel

router = APIRouter()
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    is_admin: bool


@router.post("/login", response_model=Token)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

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
