"""Seed a fresh installation once; retry failed config apply without changing credentials.

One backend worker is required. Existing installations with a completion marker
are left alone, including intentionally deleted nodes.
"""

import asyncio
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("fvpn.bootstrap")

FLAG_FILE = Path("/data/.bootstrap_done")
_BOOTSTRAP_LOCK = asyncio.Lock()


async def run_once() -> None:
    async with _BOOTSTRAP_LOCK:
        if FLAG_FILE.exists():
            return
        try:
            FLAG_FILE.parent.mkdir(parents=True, exist_ok=True)
            await _seed()
            FLAG_FILE.touch(mode=0o600)
            logger.info("Bootstrap complete")
        except Exception:
            logger.error("Bootstrap incomplete; retry on restart or sync the local node manually")


async def _seed() -> None:
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Node, Protocol
    from app.lib.config_generator import ProtocolConfig

    async with SessionLocal() as db:
        nodes = (await db.execute(select(Node))).scalars().all()
        seeded = next((n for n in nodes if (n.meta or {}).get("local") is True
                       and (n.meta or {}).get("managed_by") == "bootstrap"), None)
        if seeded is not None:
            node_id = seeded.id
        elif nodes:
            # An existing installation must never gain a new seed node or keys.
            return
        else:
            node = Node(name="Local Server", host=settings.DOMAIN, ssh_port=22,
                        ssh_user="root", ssh_key=None, group="Local", status="online",
                        is_active=True, meta={"local": True, "managed_by": "bootstrap"})
            db.add(node)
            await db.flush()
            node_id = node.id
            # These protocols do not depend on a trusted local TLS certificate.
            # Operators can add certificate-based protocols after configuring TLS.
            defaults: list[tuple[str, int, dict]] = [
                ("shadowsocks", 8443, {"method": "aes-256-gcm"}),
                # Reality's SNI should be a real third-party TLS host whose
                # certificate gets "borrowed" for camouflage — NOT this
                # server's own domain, that would defeat the point. Keypair is
                # generated fresh by ProtocolConfig.defaults() below (real
                # X25519, same as `xray x25519`) — no .env setup required.
                ("vless",       443,  {"sni": getattr(settings, "REALITY_SNI", None) or "ya.ru"}),
            ]

            for name, port, extra in defaults:
                cfg = ProtocolConfig.defaults(name, port, extra)
                db.add(Protocol(node_id=node_id, name=name, port=port, config=cfg, is_active=True))

            await db.commit()
            logger.info(f"Seeded {len(defaults)} default protocols on local node #{node_id}")

    from app.core.config_writer import sync_node_config
    result = await sync_node_config(node_id)
    if result.get("status") != "applied":
        raise RuntimeError("initial_config_apply_failed")
