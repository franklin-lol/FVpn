"""Monitor service — broadcasts system stats via WebSocket every 5s"""

import asyncio
import logging

import psutil

logger = logging.getLogger("uniproxy.monitor")


class MonitorService:
    def __init__(self, ws_manager):
        self.ws = ws_manager
        self._running = False

    async def run(self):
        self._running = True
        logger.info("MonitorService started")
        while self._running:
            try:
                await self._broadcast()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Monitor broadcast error: {e}")
            await asyncio.sleep(5)

    async def _broadcast(self):
        if not self.ws.connections:
            return  # No clients — skip expensive queries

        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory()
        net = psutil.net_io_counters()

        from app.database import SessionLocal
        from backend.app import Node, User
        from sqlalchemy import select, func

        async with SessionLocal() as db:
            online_nodes  = (await db.execute(
                select(func.count(Node.id)).where(Node.status == "online")
            )).scalar()
            active_users  = (await db.execute(
                select(func.count(User.id)).where(User.is_active == True)
            )).scalar()

        payload = {
            "type": "stats",
            "cpu_pct":      cpu,
            "ram_pct":      ram.percent,
            "ram_used_gb":  round(ram.used  / 1e9, 2),
            "net_sent_kb":  round(net.bytes_sent / 1e3, 1),
            "net_recv_kb":  round(net.bytes_recv / 1e3, 1),
            "online_nodes": online_nodes,
            "active_users": active_users,
        }
        await self.ws.broadcast(payload)
