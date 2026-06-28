"""Async SQLAlchemy database layer"""

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    # check_same_thread only valid for SQLite sync driver; aiosqlite doesn't need it
    # but harmless to pass — aiosqlite ignores unknown connect_args
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
    """Create all tables; seed default admin on first run."""
    # Import models to register with Base.metadata (all defined in app.models)
    import app.models  # noqa: F401 — side-effect: registers ORM classes

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed admin only if table is empty
    from app.models import User
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


async def get_db():
    """FastAPI dependency — yields AsyncSession, auto-closes on exit."""
    async with SessionLocal() as session:
        yield session
