"""
Bootstrap — runs once, on the very first backend startup ever.

This is the actual answer to "why isn't anything configured by default?":
nothing was seeding a node or protocols, so xray/sing-box always booted
with empty configs (inbounds: []) until an admin manually added a node via
SSH and clicked Auto-Setup. For a single-server self-hosted install, that's
backwards — the panel and the proxy core are already running on the SAME
machine, no SSH required.

This module creates one "Local Server" node (this very container host,
reachable at settings.DOMAIN) and provisions four ready-to-use protocols on
ports already opened by install.sh's firewall rules:

    VLESS-Reality   tcp/443   — only if Reality keys were generated at install
    Hysteria2       udp/443   — coexists with VLESS on the same port number;
                                 TCP and UDP sockets don't collide, and this
                                 is the same dual-protocol-on-443 trick
                                 Hiddify/3X-UI use for stealth
    Shadowsocks2022 tcp+udp/8443
    Trojan          tcp/8080  — tls_insecure=True by default, since a fresh
                                 install commonly has a self-signed cert

It then writes real Xray/Sing-box configs and restarts those sibling
containers, so the proxy stack is actually reachable within seconds of
`docker compose up` — zero manual setup for the common single-server case.
Multi-server fleets are still added the normal way via Nodes > Add Node.

Idempotency: guarded by atomically creating /data/.bootstrap_done as the
FIRST action (os.O_CREAT | os.O_EXCL is an atomic OS-level claim). uvicorn
runs 4 worker processes, each calling init_db() independently on startup —
without this atomic claim, all 4 would race past a plain `.exists()` check
and seed duplicate nodes/protocols. The flag also lives on the persisted
/data volume, so deliberately deleting the seeded node later does NOT
trigger re-seeding on the next container restart.
"""

import asyncio
import logging
import os
from pathlib import Path

from app.config import settings

logger = logging.getLogger("fvpn.bootstrap")

FLAG_FILE = Path("/data/.bootstrap_done")


async def run_once() -> None:
    # Atomic claim — exactly one of the 4 uvicorn workers wins this race.
    try:
        FLAG_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(FLAG_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return  # another worker claimed it, or this ran on a previous boot

    try:
        await _seed()
        logger.info("Bootstrap complete")
    except Exception as e:
        # Never let a bootstrap failure block app startup — manual node/
        # protocol creation via the UI still works regardless.
        logger.error(f"Bootstrap failed (add nodes/protocols manually via the panel): {e}", exc_info=True)


async def _seed() -> None:
    logger.info("First boot — provisioning default local node and protocols")

    from app.database import SessionLocal
    from backend.app import Node, Protocol
    from app.lib.config_generator import ProtocolConfig

    async with SessionLocal() as db:
        node = Node(
            name="Local Server",
            host=settings.DOMAIN,
            ssh_port=22,
            ssh_user="root",
            ssh_key=None,
            group="Local",
            status="online",
            is_active=True,
            meta={"local": True, "managed_by": "bootstrap"},
        )
        db.add(node)
        await db.commit()
        await db.refresh(node)
        node_id = node.id

        # (protocol name, port, config overrides) — see module docstring for port reasoning
        defaults: list[tuple[str, int, dict]] = [
            ("hysteria2",   443,  {"sni": settings.DOMAIN}),
            ("shadowsocks", 8443, {"method": "aes-256-gcm"}),
            ("trojan",      8080, {"sni": settings.DOMAIN, "tls_insecure": True}),
        ]

        if settings.REALITY_PRIVATE_KEY and settings.REALITY_PUBLIC_KEY:
            defaults.insert(0, ("vless", 443, {
                "private_key": settings.REALITY_PRIVATE_KEY,
                "public_key":  settings.REALITY_PUBLIC_KEY,
                # Reality's SNI should be a real third-party TLS host whose
                # certificate gets "borrowed" for camouflage — NOT this
                # server's own domain, that would defeat the point.
                "sni": "www.cloudflare.com",
            }))
        else:
            logger.warning(
                "REALITY_PRIVATE_KEY/REALITY_PUBLIC_KEY not set in .env — "
                "skipping VLESS-Reality auto-provision (install.sh's "
                "gen_reality_keys step may not have run; run `xray x25519` "
                "manually and add the keys to .env, then re-add the protocol)"
            )

        for name, port, extra in defaults:
            cfg = ProtocolConfig.defaults(name, port, extra)
            db.add(Protocol(node_id=node_id, name=name, port=port, config=cfg, is_active=True))

        await db.commit()
        logger.info(f"Seeded {len(defaults)} default protocols on local node #{node_id}")

    # Give the sibling fvpn-xray / fvpn-singbox containers a moment to finish
    # their own cold start before we try to `docker restart` them — they're
    # tiny Go binaries and start in parallel with this Python backend, which
    # is almost always slower to reach this point, but a small buffer here
    # costs nothing and avoids a needless first-run warning in the logs.
    await asyncio.sleep(3)

    try:
        from app.core.config_writer import sync_node_config
        result = await sync_node_config(node_id)
        logger.info(f"Initial config sync — xray={result['xray']} singbox={result['singbox']}")
    except Exception as e:
        logger.error(
            f"Initial config sync failed: {e} — the node/protocols were still "
            f"created; trigger a manual sync via Protocols page or "
            f"POST /api/protocols/sync/{node_id}"
        )
