"""Parent deletion is atomic and removes child records without FK pragmas."""

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import nodes, users
from app.api.auth import require_admin
from app.database import Base, get_db
from app.models import Node, Protocol, SetupState, Subscription, User


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def deletion_app(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "delete.db"))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as db:
        admin = User(username="admin", hashed_password="fixture", is_admin=True, is_active=True)
        member = User(username="member", hashed_password="fixture", is_admin=False, is_active=True)
        another = User(username="another", hashed_password="fixture", is_admin=False, is_active=True)
        node = Node(name="remove", host="192.0.2.1")
        other_node = Node(name="keep", host="192.0.2.2")
        db.add_all([admin, member, another, node, other_node])
        await db.flush()
        db.add_all([
            Subscription(user_id=member.id, token="fixture-delete-sub", format="singbox"),
            Subscription(user_id=another.id, token="fixture-keep-sub", format="singbox"),
            Protocol(node_id=node.id, name="shadowsocks", port=8443, config={"password": "fixture"}),
            Protocol(node_id=other_node.id, name="shadowsocks", port=8444, config={"password": "fixture"}),
        ])
        await db.commit()
        ids = {"admin": admin.id, "member": member.id, "another": another.id, "node": node.id, "other_node": other_node.id}

    application = FastAPI()
    application.include_router(users.router, prefix="/users")
    application.include_router(nodes.router, prefix="/nodes")

    async def database():
        async with sessions() as db:
            yield db

    async def current_admin():
        async with sessions() as db:
            return await db.get(User, ids["admin"])

    application.dependency_overrides[get_db] = database
    application.dependency_overrides[require_admin] = current_admin
    try:
        yield application, sessions, engine, ids
    finally:
        await engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["users", "nodes"])
async def test_deleting_parent_removes_only_its_children(deletion_app, kind):
    application, sessions, _, ids = deletion_app
    parent, child, target, keeper, fk = (
        (User, Subscription, ids["member"], ids["another"], "user_id") if kind == "users"
        else (Node, Protocol, ids["node"], ids["other_node"], "node_id")
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.delete(f"/{kind}/{target}")
    assert response.status_code == 204, response.text
    async with sessions() as db:
        assert await db.get(parent, target) is None
        assert await db.get(parent, keeper) is not None
        children = (await db.execute(select(child))).scalars().all()
        assert [getattr(row, fk) for row in children] == [keeper]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["users", "nodes"])
async def test_failure_deleting_parent_rolls_back_child_deletion(deletion_app, kind):
    application, sessions, engine, ids = deletion_app
    parent, child, target, fk, table = (
        (User, Subscription, ids["member"], "user_id", "users") if kind == "users"
        else (Node, Protocol, ids["node"], "node_id", "nodes")
    )

    def fail_parent_delete(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("DELETE FROM " + table.upper()):
            raise RuntimeError("fixture injected parent deletion failure")

    event.listen(engine.sync_engine, "before_cursor_execute", fail_parent_delete)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application, raise_app_exceptions=False), base_url="http://test") as client:
            response = await client.delete(f"/{kind}/{target}")
        assert response.status_code == 500
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_parent_delete)
    async with sessions() as db:
        assert await db.get(parent, target) is not None
        assert (await db.execute(select(child).where(getattr(child, fk) == target))).scalar_one_or_none() is not None


@pytest.mark.anyio
async def test_current_administrator_cannot_delete_own_account(deletion_app):
    application, sessions, _, ids = deletion_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.delete(f"/users/{ids['admin']}")
    assert response.status_code == 403
    async with sessions() as db:
        admin = await db.get(User, ids["admin"])
        assert admin is not None and admin.is_active and admin.is_admin


@pytest.mark.anyio
@pytest.mark.parametrize("required", [True, False])
async def test_initial_setup_owner_cannot_be_orphaned(deletion_app, required):
    application, sessions, _, ids = deletion_app
    async with sessions() as db:
        owner = await db.get(User, ids["member"])
        owner.is_admin = True
        db.add(SetupState(id=1, admin_user_id=owner.id, required=required, password_changed=True))
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.delete(f"/users/{ids['member']}")
    assert response.status_code == (403 if required else 204)
    async with sessions() as db:
        assert (await db.get(SetupState, 1) is not None) is required
        assert (await db.get(User, ids["member"]) is not None) is required
        assert ((await db.execute(select(Subscription).where(Subscription.user_id == ids["member"]))).scalar_one_or_none() is not None) is required


@pytest.mark.anyio
async def test_local_node_cannot_be_deleted_with_live_protocols(deletion_app):
    application, sessions, _, ids = deletion_app
    async with sessions() as db:
        node = await db.get(Node, ids["node"])
        node.meta = {"local": True}
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.delete(f"/nodes/{ids['node']}")
    assert response.status_code == 409
    assert "empty configuration" in response.json()["detail"]
    async with sessions() as db:
        assert await db.get(Node, ids["node"]) is not None
        assert (await db.execute(select(Protocol).where(Protocol.node_id == ids["node"]))).scalar_one_or_none() is not None


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["users", "nodes"])
async def test_missing_parent_is_404_without_modifying_children(deletion_app, kind):
    application, sessions, _, _ = deletion_app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
        response = await client.delete(f"/{kind}/999999")
    assert response.status_code == 404
    async with sessions() as db:
        assert len((await db.execute(select(Subscription))).scalars().all()) == 2
        assert len((await db.execute(select(Protocol))).scalars().all()) == 2
