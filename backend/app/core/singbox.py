"""
Sing-box server config writer.
Handles protocols NOT covered by Xray:
  Hysteria2, TUIC v5, ShadowTLS v3, WireGuard, native Shadowsocks 2022.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("fvpn.singbox")

SINGBOX_BIN       = os.environ.get("SINGBOX_BIN",       "/usr/local/bin/sing-box")
SINGBOX_CONFIG    = os.environ.get("SINGBOX_CONFIG",    "/etc/sing-box/config.json")
SINGBOX_CONTAINER = os.environ.get("SINGBOX_CONTAINER", "fvpn-singbox")


###############################################################################
# INBOUND BUILDERS (server side)
###############################################################################

def _inbound_hysteria2(port: int, cfg: dict) -> dict:
    inbound: dict[str, Any] = {
        "type":     "hysteria2",
        "tag":      "hysteria2-in",
        "listen":   "::",
        "listen_port": port,
        "users": [
            {"password": cfg.get("password", uuid.uuid4().hex)}
        ],
        "tls": {
            "enabled":     True,
            "certificate_path": cfg.get("cert_path", "/etc/fvpn/ssl/cert.pem"),
            "key_path":         cfg.get("key_path",  "/etc/fvpn/ssl/key.pem"),
        },
    }
    if cfg.get("obfs"):
        inbound["obfs"] = {
            "type":     cfg.get("obfs", "salamander"),
            "password": cfg.get("obfs_password", uuid.uuid4().hex[:8]),
        }
    if cfg.get("masquerade_url"):
        inbound["masquerade"] = cfg["masquerade_url"]
    return inbound


def _inbound_tuic(port: int, cfg: dict) -> dict:
    return {
        "type":        "tuic",
        "tag":         "tuic-in",
        "listen":      "::",
        "listen_port": port,
        "users": [
            {
                "uuid":     cfg.get("uuid", str(uuid.uuid4())),
                "password": cfg.get("password", uuid.uuid4().hex),
            }
        ],
        "congestion_control": cfg.get("congestion", "bbr"),
        "auth_timeout":       "3s",
        "zero_rtt_handshake": False,
        "heartbeat":          "10s",
        "tls": {
            "enabled":          True,
            "alpn":             ["h3"],
            "certificate_path": cfg.get("cert_path", "/etc/fvpn/ssl/cert.pem"),
            "key_path":         cfg.get("key_path",  "/etc/fvpn/ssl/key.pem"),
        },
    }


def _inbound_shadowtls(port: int, cfg: dict) -> dict:
    """ShadowTLS v3 — requires a paired Shadowsocks inbound behind it"""
    local_ss_port = cfg.get("ss_port", port + 1000)
    return {
        "type":        "shadowtls",
        "tag":         "shadowtls-in",
        "listen":      "::",
        "listen_port": port,
        "version":     cfg.get("version", 3),
        "users": [
            {"name": "user1", "password": cfg.get("password", uuid.uuid4().hex)}
        ],
        "handshake": {
            "server":      cfg.get("sni", "www.apple.com"),
            "server_port": 443,
        },
        "strict_mode":  True,
        "detour":       "ss-behind-shadowtls",
        "__ss_local_port": local_ss_port,
    }


def _inbound_shadowsocks(port: int, cfg: dict) -> dict:
    return {
        "type":        "shadowsocks",
        "tag":         "ss-in",
        "listen":      "::",
        "listen_port": port,
        "method":      cfg.get("method", "aes-256-gcm"),
        "password":    cfg.get("password", uuid.uuid4().hex),
        "network":     "tcp,udp",
        "multiplex":   {"enabled": True},
    }


def _inbound_wireguard(port: int, cfg: dict) -> dict:
    return {
        "type":        "wireguard",
        "tag":         "wireguard-in",
        "listen":      "::",
        "listen_port": port,
        "system_interface": False,
        "interface_name":   "wg0",
        "local_address":    ["10.0.0.1/24", "fd00::1/64"],
        "private_key":      cfg.get("private_key", ""),
        "peers": [
            {
                "public_key":    cfg.get("client_public_key", cfg.get("public_key", "")),
                "allowed_ips":   ["0.0.0.0/0", "::/0"],
                "persistent_keepalive_interval": "30s",
            }
        ],
    }


_INBOUND_MAP = {
    "hysteria2":   _inbound_hysteria2,
    "tuic":        _inbound_tuic,
    "shadowtls":   _inbound_shadowtls,
    "shadowsocks": _inbound_shadowsocks,
    "wireguard":   _inbound_wireguard,
}


###############################################################################
# FULL CONFIG BUILDER
###############################################################################

def build_singbox_server_config(protocols: list[dict]) -> dict:
    inbounds: list[dict] = []
    seen_tags: set[str] = set()

    for p in protocols:
        name = p["name"].lower().replace("-", "")
        builder = _INBOUND_MAP.get(name)
        if not builder:
            logger.debug(f"sing-box: no builder for '{p['name']}' — skipped (likely handled by Xray)")
            continue

        inbound = builder(p["port"], p.get("config", {}))

        base_tag = inbound["tag"]
        tag, i = base_tag, 2
        while tag in seen_tags:
            tag = f"{base_tag}-{i}"; i += 1
        inbound["tag"] = tag
        seen_tags.add(tag)

        if name == "shadowtls":
            ss_port = inbound.pop("__ss_local_port", p["port"] + 1000)
            ss_cfg  = p.get("config", {})
            paired  = _inbound_shadowsocks(ss_port, ss_cfg)
            paired["tag"]    = "ss-behind-shadowtls"
            paired["listen"] = "127.0.0.1"
            inbounds.append(paired)

        inbounds.append(inbound)

    config: dict[str, Any] = {
        "log": {
            "level":     "warn",
            "timestamp": True,
        },
        "inbounds": inbounds,
        "outbounds": [
            {"type": "direct",   "tag": "direct"},
            {"type": "block",    "tag": "block"},
        ],
        "route": {
            "rules": [
                {"geoip":   "private", "outbound": "block"},
                {"geosite": "category-ads-all", "outbound": "block"},
            ],
            "final":                   "direct",
            "auto_detect_interface":   True,
        },
    }
    return config


###############################################################################
# WRITE + RELOAD
###############################################################################

async def write_and_reload(protocols: list[dict], config_path: str = SINGBOX_CONFIG) -> bool:
    config = build_singbox_server_config(protocols)

    if not config["inbounds"]:
        logger.info("sing-box: no applicable protocols — skipping config write")
        return True

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        tmp.replace(path)
        logger.info(f"sing-box config written to {path} ({len(config['inbounds'])} inbounds)")
    except OSError as e:
        logger.error(f"Failed to write sing-box config: {e}")
        return False

    return await _reload_singbox()


async def _reload_singbox() -> bool:
    """
    Restart the sibling fvpn-singbox Docker container so it picks up the
    freshly written config. Same reasoning as xray.py's _reload_xray —
    sing-box runs in its own container, not as a local process this backend
    container could SIGHUP or systemctl-restart directly.
    """
    proc = await asyncio.create_subprocess_exec(
        "docker", "restart", SINGBOX_CONTAINER,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode == 0:
        logger.info(f"{SINGBOX_CONTAINER} restarted")
        return True

    logger.error(f"{SINGBOX_CONTAINER} restart failed: {stderr.decode().strip()}")
    return False


async def validate_config(config_path: str = SINGBOX_CONFIG) -> tuple[bool, str]:
    """Run `sing-box check -c <path>` inside the sibling container."""
    proc = await asyncio.create_subprocess_exec(
        "docker", "exec", SINGBOX_CONTAINER, "sing-box", "check", "-c", config_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    ok  = proc.returncode == 0
    msg = (out + err).decode().strip()
    return ok, msg
