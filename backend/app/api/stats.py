"""Stats API — dashboard metrics"""

import psutil
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from backend.app import User, Node, Protocol, EventLog
from app.api.auth import require_admin

router = APIRouter()


@router.get("/dashboard")
async def dashboard_stats(
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for main dashboard"""
    # Counts
    total_users  = (await db.execute(select(func.count(User.id)))).scalar()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    total_nodes  = (await db.execute(select(func.count(Node.id)))).scalar()
    online_nodes = (await db.execute(select(func.count(Node.id)).where(Node.status == "online"))).scalar()
    total_protos = (await db.execute(select(func.count(Protocol.id)))).scalar()

    # Traffic sums
    traffic_in  = (await db.execute(select(func.sum(Node.traffic_in)))).scalar()  or 0
    traffic_out = (await db.execute(select(func.sum(Node.traffic_out)))).scalar() or 0

    # System resources
    cpu    = psutil.cpu_percent(interval=0.5)
    ram    = psutil.virtual_memory()
    disk   = psutil.disk_usage("/")
    net    = psutil.net_io_counters()

    # Node latency list
    nodes_res = await db.execute(
        select(Node.name, Node.status, Node.latency_ms, Node.group)
        .where(Node.is_active == True)
    )
    nodes = [
        {"name": r[0], "status": r[1], "latency_ms": r[2], "group": r[3]}
        for r in nodes_res.all()
    ]

    # Recent events
    logs_res = await db.execute(
        select(EventLog).order_by(EventLog.created_at.desc()).limit(20)
    )
    logs = [
        {"level": l.level, "source": l.source, "message": l.message, "at": l.created_at.isoformat()}
        for l in logs_res.scalars().all()
    ]

    return {
        "users":     {"total": total_users,  "active": active_users},
        "nodes":     {"total": total_nodes,  "online": online_nodes},
        "protocols": {"total": total_protos},
        "traffic":   {"in_bytes": traffic_in, "out_bytes": traffic_out},
        "system": {
            "cpu_pct":      cpu,
            "ram_total_gb": round(ram.total / 1e9, 2),
            "ram_used_gb":  round(ram.used  / 1e9, 2),
            "ram_pct":      ram.percent,
            "disk_total_gb": round(disk.total / 1e9, 2),
            "disk_used_gb":  round(disk.used  / 1e9, 2),
            "disk_pct":      disk.percent,
            "net_sent_gb":  round(net.bytes_sent / 1e9, 3),
            "net_recv_gb":  round(net.bytes_recv / 1e9, 3),
        },
        "nodes_list": nodes,
        "recent_logs": logs,
        "generated_at": datetime.utcnow().isoformat(),
    }


@router.get("/nodes/{node_id}/history")
async def node_traffic_history(
    node_id: int,
    days: int = 7,
    _=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Returns placeholder time-series — hook to real metrics collector"""
    # In production: query InfluxDB / Prometheus / timescale
    # Here: return mock structure so frontend renders correctly
    result = await db.execute(select(Node).where(Node.id == node_id))
    node = result.scalar_one_or_none()
    if not node:
        from fastapi import HTTPException
        raise HTTPException(404, "Node not found")

    import random
    base = datetime.utcnow()
    points = []
    for i in range(days * 24):
        ts = base - timedelta(hours=days * 24 - i)
        points.append({
            "ts": ts.isoformat(),
            "in_mbps":  round(random.uniform(0, 100), 2),
            "out_mbps": round(random.uniform(0, 80),  2),
        })
    return {"node_id": node_id, "name": node.name, "points": points}


@router.get("/system")
async def system_stats(_=Depends(require_admin)):
    cpu     = psutil.cpu_percent(percpu=True)
    ram     = psutil.virtual_memory()
    disk    = psutil.disk_usage("/")
    net     = psutil.net_io_counters()
    boot    = datetime.fromtimestamp(psutil.boot_time())

    return {
        "cpu_cores":  len(cpu),
        "cpu_pct":    cpu,
        "ram": {
            "total_gb": round(ram.total / 1e9, 2),
            "used_gb":  round(ram.used  / 1e9, 2),
            "free_gb":  round(ram.free  / 1e9, 2),
            "pct":      ram.percent,
        },
        "disk": {
            "total_gb": round(disk.total / 1e9, 2),
            "used_gb":  round(disk.used  / 1e9, 2),
            "free_gb":  round(disk.free  / 1e9, 2),
            "pct":      disk.percent,
        },
        "network": {
            "sent_gb": round(net.bytes_sent / 1e9, 3),
            "recv_gb": round(net.bytes_recv / 1e9, 3),
        },
        "uptime_hours": round((datetime.now() - boot).total_seconds() / 3600, 1),
        "boot_time": boot.isoformat(),
    }
