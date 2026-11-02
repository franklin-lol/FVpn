"""
Sing-box server config writer.
Handles protocols NOT covered by Xray:
  Hysteria2, TUIC v5, ShadowTLS v3, WireGuard, native Shadowsocks 2022.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("fvpn.singbox")

SINGBOX_BIN       = os.environ.get("SINGBOX_BIN",       "/usr/local/bin/sing-box")
SINGBOX_CONTAINER_BIN = os.environ.get("SINGBOX_CONTAINER_BIN", "/usr/local/bin/sing-box")
SINGBOX_CONFIG    = os.environ.get("SINGBOX_CONFIG",    "/etc/sing-box/config.json")
SINGBOX_CONTAINER = os.environ.get("SINGBOX_CONTAINER", "fvpn-singbox")


###############################################################################
# INBOUND BUILDERS (server side)
###############################################################################

def _inbound_hysteria2(port: int, cfg: dict) -> dict:
    inbound: dict[str, Any] = {
        "type":     "hysteria2",
        "tag":      "hysteria2-in",
        "listen":   "0.0.0.0",
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
        "listen":      "0.0.0.0",
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
        "listen":      "0.0.0.0",
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
        "listen":      "0.0.0.0",
        "listen_port": port,
        "method":      cfg.get("method", "aes-256-gcm"),
        "password":    cfg.get("password", uuid.uuid4().hex),
        # no "network" key: sing-box only accepts "tcp" / "udp" singly here,
        # not the combined string "tcp,udp" (hard FATAL parse error on boot).
        # Omitting the field listens on both, which is what we want anyway.
        "multiplex":   {"enabled": True},
    }


def _inbound_wireguard(port: int, cfg: dict) -> dict:
    return {
        "type":        "wireguard",
        "tag":         "wireguard-in",
        "listen":      "0.0.0.0",
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
            tag = f"{base_tag}-{i}"
            i += 1
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
            # domain_strategy pins DNS resolution to A records only. Without
            # this, sing-box resolves AAAA too and tries IPv6 first on a VPS
            # with no IPv6 uplink — "network is unreachable" on every single
            # connection, plus the wasted RTT before it falls back to IPv4.
            {"type": "direct",   "tag": "direct",   "domain_strategy": "ipv4_only"},
            {"type": "block",    "tag": "block"},
        ],
        "route": {
            "rules": [
                # Client apps sometimes hardcode IPv6 literals (e.g. Google's
                # DoT resolver 2001:4860:4860::8888:853) and connect directly
                # — domain_strategy doesn't apply here, there's no domain to
                # resolve. This VPS has no IPv6 route, so those dials would
                # otherwise hang for the full timeout before failing. Reject
                # immediately so the client's own IPv4 fallback kicks in fast.
                {"ip_version": 6, "outbound": "block"},
                {"ip_is_private": True, "outbound": "block"},
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
    from app.core.config_apply import CoreConfig, apply_configs

    spec = CoreConfig("singbox", Path(config_path), SINGBOX_CONTAINER,
                      SINGBOX_CONTAINER_BIN, build_singbox_server_config(protocols))
    result = await apply_configs([spec])
    return result["singbox"] is True


async def validate_config(config_path: str = SINGBOX_CONFIG) -> tuple[bool, str]:
    from app.core.config_apply import CoreConfig, validate_candidate

    spec = CoreConfig("singbox", Path(config_path), SINGBOX_CONTAINER, SINGBOX_CONTAINER_BIN, {})
    return await validate_candidate(spec, Path(config_path))
