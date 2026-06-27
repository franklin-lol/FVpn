"""System control — restart services, logs, backup"""

import asyncio
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from app.api.auth import require_admin
from app.config import settings

router = APIRouter()


async def _run(cmd: str) -> tuple[str, str, int]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode(), proc.returncode


@router.post("/xray/restart")
async def restart_xray(_=Depends(require_admin)):
    out, err, code = await _run("systemctl restart xray")
    if code != 0:
        raise HTTPException(500, detail=f"Failed: {err}")
    return {"status": "restarted", "service": "xray"}


@router.post("/singbox/restart")
async def restart_singbox(_=Depends(require_admin)):
    out, err, code = await _run("systemctl restart sing-box")
    if code != 0:
        raise HTTPException(500, detail=f"Failed: {err}")
    return {"status": "restarted", "service": "sing-box"}


@router.get("/xray/status")
async def xray_status(_=Depends(require_admin)):
    out, _, _ = await _run("systemctl is-active xray")
    return {"service": "xray", "active": out.strip() == "active"}


@router.get("/singbox/status")
async def singbox_status(_=Depends(require_admin)):
    out, _, _ = await _run("systemctl is-active sing-box")
    return {"service": "sing-box", "active": out.strip() == "active"}


@router.get("/logs/uniproxy", response_class=PlainTextResponse)
async def get_logs(lines: int = 200, _=Depends(require_admin)):
    out, _, _ = await _run(f"tail -n {lines} /var/log/uniproxy.log 2>/dev/null || echo 'No log file found'")
    return out


@router.get("/logs/{service}", response_class=PlainTextResponse)
async def get_service_logs(service: str, lines: int = 100, _=Depends(require_admin)):
    allowed = {"xray", "sing-box", "nginx", "uniproxy-backend"}
    if service not in allowed:
        raise HTTPException(400, f"Allowed: {', '.join(allowed)}")
    out, _, _ = await _run(f"journalctl -u {service} -n {lines} --no-pager 2>/dev/null")
    return out


@router.post("/backup")
async def trigger_backup(_=Depends(require_admin)):
    out, err, code = await _run(f"{settings.UNIPROXY_DIR if hasattr(settings, 'UNIPROXY_DIR') else '/opt/uniproxy'}/scripts/backup.sh")
    if code != 0:
        raise HTTPException(500, detail=err)
    return {"status": "backup_complete", "output": out.strip()}


@router.get("/cert/status")
async def cert_status(_=Depends(require_admin)):
    domain = settings.DOMAIN
    out, _, code = await _run(
        f"openssl x509 -in {settings.CERT_PATH} -noout -dates 2>/dev/null"
    )
    if code != 0:
        return {"domain": domain, "valid": False, "error": "Cannot read cert"}

    dates = {}
    for line in out.splitlines():
        if "notBefore" in line:
            dates["not_before"] = line.split("=", 1)[1].strip()
        if "notAfter" in line:
            dates["not_after"] = line.split("=", 1)[1].strip()

    return {"domain": domain, "valid": True, **dates}


@router.post("/cert/renew")
async def renew_cert(_=Depends(require_admin)):
    out, err, code = await _run(f"certbot renew --cert-name {settings.DOMAIN} --non-interactive 2>&1")
    return {"code": code, "output": (out + err).strip()}


@router.get("/version")
async def version_info(_=Depends(require_admin)):
    xray_v, _, _    = await _run("xray version 2>/dev/null | head -1")
    singbox_v, _, _ = await _run("sing-box version 2>/dev/null | head -1")
    return {
        "uniproxy": settings.VERSION,
        "xray":     xray_v.strip()    or "not installed",
        "sing_box": singbox_v.strip() or "not installed",
    }
