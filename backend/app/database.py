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
    """Create all tables on startup"""
    # Import all models to register them
    from app.models import user, node, protocol, subscription  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default admin
    from app.models.user import User
    from app.core.security import hash_password
    async with SessionLocal() as session:
        from sqlalchemy import select
        result = await session.execute(select(User).where(User.username == "admin"))
        if not result.scalar_one_or_none():
            admin = User(
                username="admin",
                email="admin@uniproxy.local",
                hashed_password=hash_password(settings.MASTER_PASSWORD),
                is_admin=True,
                is_active=True,
            )
            session.add(admin)
            await session.commit()


async def get_db():
    """Dependency injection for FastAPI routes"""
    async with SessionLocal() as session:
        yield session
