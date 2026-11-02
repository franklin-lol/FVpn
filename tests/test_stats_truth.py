"""Traffic history reports missing measurements without invented samples."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import require_admin
from app.api.stats import router
from app.database import Base, get_db
from app.models import Node


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_traffic_history_is_explicitly_unavailable_and_missing_node_is_404(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'truth.sqlite'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as db:
        node = Node(name="fixture", host="fixture.invalid")
        db.add(node)
        await db.commit()
    app = FastAPI()
    app.include_router(router)

    async def database():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_admin] = lambda: None
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            result = await client.get(f"/nodes/{node.id}/history")
            assert result.status_code == 200
            assert result.json()["points"] == []
            assert result.json()["available"] is False
            assert "not collected" in result.json()["reason"].lower()
            assert (await client.get("/nodes/9999/history")).status_code == 404
    finally:
        await engine.dispose()
