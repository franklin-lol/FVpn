"""Async SQLAlchemy database layer"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """Create all tables; seed default admin; seed default local node+protocols once."""
    import backend.app  # noqa: F401 — registers ORM classes with Base.metadata

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from backend.app import User
    from app.core.security import hash_password
    from sqlalchemy import select

    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@fvpn.local",
                hashed_password=hash_password(settings.MASTER_PASSWORD),
                is_admin=True,
                is_active=True,
            )
            session.add(admin)
            await session.commit()

    # One-time: seed a "Local Server" node with 4 ready-to-use protocols so
    # the proxy stack works immediately after install, with zero manual
    # SSH/Auto-Setup steps. Safe to call on every boot — it's a no-op after
    # the first successful run (see app/core/bootstrap.py for details).
    from app.core.bootstrap import run_once
    await run_once()


async def get_db():
    """FastAPI dependency — yields AsyncSession, auto-closes on exit."""
    async with SessionLocal() as session:
        yield session
