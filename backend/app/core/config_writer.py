"""Bridge database protocols to a single local, validated apply transaction."""

from pathlib import Path

from sqlalchemy import select

from app.core import xray, singbox
from app.core.config_apply import APPLY_LOCK, CoreConfig, apply_configs_locked


def is_local_node(node) -> bool:
    return isinstance(node.meta, dict) and node.meta.get("local") is True


async def sync_node_config(node_id: int) -> dict[str, bool | str]:
    from app.database import SessionLocal
    from app.models import Node, Protocol

    # Protect the read as well as the write, so queued syncs cannot apply stale snapshots.
    async with APPLY_LOCK:
        async with SessionLocal() as db:
            node = (await db.execute(select(Node).where(Node.id == node_id))).scalar_one_or_none()
            if node is None:
                return {"xray": False, "singbox": False, "status": "node_not_found"}
            if not is_local_node(node):
                return {"xray": False, "singbox": False, "status": "manual_required"}
            rows = (await db.execute(select(Protocol).where(
                Protocol.node_id == node_id, Protocol.is_active.is_(True),
            ))).scalars().all()
            protocols = [{"name": p.name, "port": p.port, "config": p.config or {}} for p in rows]
        supported = set(xray._INBOUND_MAP) | set(singbox._INBOUND_MAP)
        if any(p["name"].lower().replace("-", "") not in supported for p in protocols):
            return {"xray": False, "singbox": False, "status": "unsupported_protocol"}
        # An empty active set removes stale public listeners in both cores.
        return await apply_configs_locked([
            CoreConfig("xray", Path(xray.XRAY_CONFIG), xray.XRAY_CONTAINER,
                       xray.XRAY_CONTAINER_BIN, xray.build_xray_server_config(protocols)),
            CoreConfig("singbox", Path(singbox.SINGBOX_CONFIG), singbox.SINGBOX_CONTAINER,
                       singbox.SINGBOX_CONTAINER_BIN, singbox.build_singbox_server_config(protocols)),
        ])
