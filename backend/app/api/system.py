"""System control — services, logs, cert, backup
Docker-aware: uses `docker` CLI via subprocess to restart proxy containers.
"""

import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.auth import require_admin
from app.config import settings

router = APIRouter()

# In Docker mode, proxy services run as sibling containers.
# The backend container needs /var/run/docker.sock mounted to control them.
XRAY_CONTAINER    = os.environ.get("XRAY_CONTAINER",    "fvpn-xray")
SINGBOX_CONTAINER = os.environ.get("SINGBOX_CONTAINER", "fvpn-singbox")
_DOCKER_AVAILABLE = None  # lazily detected


async def _run(cmd: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return out.decode(), err.decode(), proc.returncode


async def _docker_available() -> bool:
    global _DOCKER_AVAILABLE
    if _DOCKER_AVAILABLE is None:
        _, _, code = await _run("docker info > /dev/null 2>&1")
        _DOCKER_AVAILABLE = (code == 0)
    return _DOCKER_AVAILABLE


async def _restart_proxy(container: str) -> tuple[bool, str]:
    """Restart a proxy container via Docker CLI or systemctl fallback."""
    if await _docker_available():
        out, err, code = await _run(f"docker restart {container}")
        if code == 0:
            return True, f"Container {container} restarted"
        # Container might not exist — try systemctl on the host via nsenter
        out2, err2, code2 = await _run(
            f"docker exec {container} echo ok 2>/dev/null || "
            f"systemctl restart {container.replace('fvpn-','')} 2>/dev/null"
        )
        return code2 == 0, (out2 + err2).strip() or "service not found"

    # No docker socket: try systemctl directly (non-Docker mode)
    svc = container.replace("fvpn-", "")
    out, err, code = await _run(f"systemctl restart {svc}")
    return code == 0, (out + err).strip() or f"{svc} restarted"


async def _is_running(container: str) -> bool:
    if await _docker_available():
        out, _, code = await _run(
            f"docker inspect --format='{{{{.State.Status}}}}' {container} 2>/dev/null"
        )
        return code == 0 and out.strip() == "running"
    svc = container.replace("fvpn-", "")
    out, _, _ = await _run(f"systemctl is-active {svc} 2>/dev/null")
    return out.strip() == "active"


###############################################################################
# Xray
###############################################################################
@router.post("/xray/restart")
async def restart_xray(_=Depends(require_admin)):
    ok, msg = await _restart_proxy(XRAY_CONTAINER)
    if not ok:
        raise HTTPException(500, detail=msg)
    return {"status": "restarted", "service": "xray", "detail": msg}


@router.get("/xray/status")
async def xray_status(_=Depends(require_admin)):
    active = await _is_running(XRAY_CONTAINER)
    return {"service": "xray", "active": active}


###############################################################################
# Sing-box
###############################################################################
@router.post("/singbox/restart")
async def restart_singbox(_=Depends(require_admin)):
    ok, msg = await _restart_proxy(SINGBOX_CONTAINER)
    if not ok:
        raise HTTPException(500, detail=msg)
    return {"status": "restarted", "service": "sing-box", "detail": msg}


@router.get("/singbox/status")
async def singbox_status(_=Depends(require_admin)):
    active = await _is_running(SINGBOX_CONTAINER)
    return {"service": "sing-box", "active": active}


###############################################################################
# Logs
###############################################################################
@router.get("/logs/uniproxy", response_class=PlainTextResponse)
async def get_logs(lines: int = 200, _=Depends(require_admin)):
    out, _, _ = await _run(
        f"tail -n {lines} /var/log/fvpn/app.log 2>/dev/null || "
        f"tail -n {lines} /var/log/uniproxy.log 2>/dev/null || "
        "echo 'No log file found'"
    )
    return out


@router.get("/logs/{service}", response_class=PlainTextResponse)
async def get_service_logs(service: str, lines: int = 100, _=Depends(require_admin)):
    allowed = {"xray", "sing-box", "singbox", "nginx", "fvpn-backend"}
    if service not in allowed:
        raise HTTPException(400, f"Allowed: {', '.join(allowed)}")

    # Try docker logs first, then journalctl
    container = f"fvpn-{service}" if not service.startswith("fvpn-") else service
    if await _docker_available():
        out, _, code = await _run(f"docker logs {container} --tail {lines} 2>&1")
        if code == 0:
            return out
    out, _, _ = await _run(f"journalctl -u {service} -n {lines} --no-pager 2>/dev/null")
    return out or "No logs available"


###############################################################################
# Backup
###############################################################################
@router.post("/backup")
async def trigger_backup(_=Depends(require_admin)):
    script = "/opt/fvpn/scripts/backup.sh"
    if not os.path.exists(script):
        raise HTTPException(404, "Backup script not found at /opt/fvpn/scripts/backup.sh")
    out, err, code = await _run(script)
    if code != 0:
        raise HTTPException(500, detail=err or "Backup failed")
    return {"status": "backup_complete", "output": out.strip()}


###############################################################################
# TLS Certificate
###############################################################################
@router.get("/cert/status")
async def cert_status(_=Depends(require_admin)):
    cert = settings.CERT_PATH
    out, _, code = await _run(f"openssl x509 -in {cert} -noout -dates 2>/dev/null")
    if code != 0:
        return {"domain": settings.DOMAIN, "valid": False, "error": f"Cannot read {cert}"}
    dates = {}
    for line in out.splitlines():
        if "notBefore" in line:
            dates["not_before"] = line.split("=", 1)[1].strip()
        if "notAfter" in line:
            dates["not_after"] = line.split("=", 1)[1].strip()
    return {"domain": settings.DOMAIN, "valid": True, **dates}


@router.post("/cert/renew")
async def renew_cert(_=Depends(require_admin)):
    out, err, code = await _run(
        f"certbot renew --cert-name {settings.DOMAIN} --non-interactive 2>&1"
    )
    return {"code": code, "output": (out + err).strip()}


###############################################################################
# Version info
###############################################################################
@router.get("/version")
async def version_info(_=Depends(require_admin)):
    xv, _, _  = await _run("xray version 2>/dev/null | head -1")
    sbv, _, _ = await _run("sing-box version 2>/dev/null | head -1")

    # Also try docker exec into proxy containers
    if not xv.strip() and await _docker_available():
        xv, _, _ = await _run(f"docker exec {XRAY_CONTAINER} xray version 2>/dev/null | head -1")
    if not sbv.strip() and await _docker_available():
        sbv, _, _ = await _run(f"docker exec {SINGBOX_CONTAINER} sing-box version 2>/dev/null | head -1")

    return {
        "fvpn":     settings.VERSION,
        "xray":     xv.strip()  or "not running",
        "sing_box": sbv.strip() or "not running",
    }
