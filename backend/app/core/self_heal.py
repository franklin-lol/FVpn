"""Self-Healing Service — monitors nodes and restarts failed services"""

import asyncio
import logging
from datetime import datetime

import httpx

from app.config import settings

logger = logging.getLogger("uniproxy.selfheal")


class SelfHealService:
    """
    Runs every HEALTH_CHECK_INTERVAL seconds:
    1. Checks all active nodes via HTTP ping
    2. Restarts sing-box/xray if they're down
    3. Logs all events to DB
    """

    def __init__(self):
        self._running = False

    async def run(self):
        self._running = True
        logger.info("SelfHealService started")
        while self._running:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.error("SelfHeal cycle failed error_type=%s", type(error).__name__)
            await asyncio.sleep(settings.HEALTH_CHECK_INTERVAL)
        logger.info("SelfHealService stopped")

    async def _cycle(self):
        from app.database import SessionLocal
        from app.models import Node, EventLog
        from sqlalchemy import select

        async with SessionLocal() as db:
            result = await db.execute(select(Node).where(Node.is_active.is_(True)))
            nodes = result.scalars().all()

        tasks = [self._check_node(n) for n in nodes]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check local services
        await self._check_local_services()

        async with SessionLocal() as db:
            for node, r in zip(nodes, results):
                if isinstance(r, Exception):
                    logger.warning("Node check failed node_id=%s error_type=%s", node.id, type(r).__name__)
                    ev = EventLog(
                        level="warn",
                        source=f"node:{node.id}",
                        message="Health check failed; inspect node connectivity",
                    )
                    db.add(ev)
            await db.commit()

    async def _check_node(self, node) -> bool:
        from app.database import SessionLocal
        from app.models import Node, EventLog
        from sqlalchemy import select
        import time

        t0 = time.monotonic()
        restart_node = None
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(settings.HEALTH_CHECK_URL)
                latency = (time.monotonic() - t0) * 1000
                status = "online"
        except Exception:
            latency = None
            status = "offline"

        async with SessionLocal() as db:
            result = await db.execute(select(Node).where(Node.id == node.id))
            n = result.scalar_one_or_none()
            if n:
                prev_status = n.status
                n.status = status
                n.latency_ms = latency
                n.last_check = datetime.utcnow()

                if prev_status == "online" and status == "offline":
                    logger.warning(f"Node {n.name} ({n.host}) went OFFLINE — attempting restart")
                    ev = EventLog(
                        level="warn",
                        source=f"node:{n.id}",
                        message="Node offline — attempting SSH restart",
                    )
                    db.add(ev)
                    restart_node = n

                elif prev_status == "offline" and status == "online":
                    logger.info(f"Node {n.name} came back ONLINE")
                    ev = EventLog(
                        level="info",
                        source=f"node:{n.id}",
                        message="Node recovered and is online",
                    )
                    db.add(ev)

                await db.commit()

        if restart_node is not None:
            await self._try_restart_node(restart_node)
        return status == "online"

    async def _try_restart_node(self, node):
        """SSH into the node and restart proxy services"""
        if not node.ssh_key:
            logger.warning(f"No SSH key for node {node.name} — cannot auto-restart")
            return

        ssh = None
        try:
            from app.core.ssh import SSHClient
            ssh = SSHClient(node.host, node.ssh_port, node.ssh_user, node.ssh_key)
            await ssh.connect(timeout=10)
            for svc in ("xray", "sing-box", "hysteria-server", "shadowsocks-libev"):
                stdout, _, code = await ssh.exec(f"systemctl is-active {svc} 2>/dev/null")
                if stdout.strip() == "active":
                    await ssh.exec(f"systemctl restart {svc}")
                    logger.info(f"Restarted {svc} on {node.name}")
        except Exception as error:
            logger.error("SSH restart failed node_id=%s error_type=%s", node.id, type(error).__name__)
        finally:
            if ssh is not None:
                try:
                    await ssh.disconnect()
                except Exception as error:
                    logger.warning("SSH disconnect failed node_id=%s error_type=%s", node.id, type(error).__name__)

    async def _check_local_services(self):
        """Restart local xray/sing-box if systemd reports failure"""
        import asyncio
        for svc in ("xray", "sing-box"):
            proc = await asyncio.create_subprocess_shell(
                f"systemctl is-active {svc}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if stdout.decode().strip() not in ("active", ""):
                logger.warning(f"Local service {svc} not active — restarting")
                await asyncio.create_subprocess_shell(f"systemctl restart {svc}")
