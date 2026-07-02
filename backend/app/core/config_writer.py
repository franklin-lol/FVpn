"""
Config sync orchestrator — bridges DB `Protocol` rows to the xray/sing-box
config writers (app/core/xray.py, app/core/singbox.py) and triggers the
sibling container restarts.

Referenced by app/core/bootstrap.py (initial seed) and app/api/protocols.py
(create/update/delete/force-sync) as:

    from app.core.config_writer import sync_node_config
    result = await sync_node_config(node_id)   # {"xray": bool, "singbox": bool}

Both write_and_reload() implementations already filter inbounds by their own
protocol map and silently skip anything they don't own (see the "no builder
for X — skipped" log lines in xray.py / singbox.py), so the *same* protocol
list is safely passed to both — each writer only picks up what it recognizes.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core import xray, singbox

logger = logging.getLogger("fvpn.config_writer")


async def sync_node_config(node_id: int) -> dict:
    """
    Load all active protocols for `node_id`, write both xray and sing-box
    server configs, and restart the sibling proxy containers.

    Returns {"xray": bool, "singbox": bool} — True per core if its
    write_and_reload succeeded (or had nothing to do).
    """
    from app.database import SessionLocal
    from app.models import Protocol

    async with SessionLocal() as db:
        result = await db.execute(
            select(Protocol).where(
                Protocol.node_id == node_id,
                Protocol.is_active == True,  # noqa: E712
            )
        )
        rows = result.scalars().all()

    protocols = [
        {"name": p.name, "port": p.port, "config": p.config or {}}
        for p in rows
    ]

    if not protocols:
        logger.info(f"Node {node_id}: no active protocols — nothing to sync")
        return {"xray": True, "singbox": True}

    xray_ok, singbox_ok = await asyncio.gather(
        xray.write_and_reload(protocols),
        singbox.write_and_reload(protocols),
    )

    return {"xray": xray_ok, "singbox": singbox_ok}
