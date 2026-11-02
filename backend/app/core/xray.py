"""
Xray-core server config writer.
Reads active Protocol rows for a node, produces /etc/xray/config.json,
then restarts the sibling `fvpn-xray` Docker container to apply it.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger("fvpn.xray")

XRAY_BIN       = os.environ.get("XRAY_BIN",       "/usr/local/bin/xray")
XRAY_CONTAINER_BIN = os.environ.get("XRAY_CONTAINER_BIN", "/usr/bin/xray")
XRAY_CONFIG    = os.environ.get("XRAY_CONFIG",    "/etc/xray/config.json")
XRAY_CONTAINER = os.environ.get("XRAY_CONTAINER", "fvpn-xray")


###############################################################################
# INBOUND BUILDERS (server side)
###############################################################################

def _inbound_vless(port: int, cfg: dict) -> dict:
    """VLESS + XTLS-Vision + Reality"""
    return {
        "tag":      "vless-in",
        "listen":   "0.0.0.0",
        "port":     port,
        "protocol": "vless",
        "settings": {
            "clients": [
                {
                    "id":    cfg.get("uuid", str(uuid.uuid4())),
                    "flow":  cfg.get("flow", "xtls-rprx-vision"),
                    "email": "user@fvpn",
                }
            ],
            "decryption": "none",
        },
        "streamSettings": {
            "network":         "tcp",
            "security":        "reality",
            "realitySettings": {
                "show":        False,
                "dest":        f"{cfg.get('sni','www.cloudflare.com')}:443",
                "xver":        0,
                "serverNames": [cfg.get("sni", "www.cloudflare.com")],
                "privateKey":  cfg.get("private_key", ""),
                "shortIds":    [cfg.get("short_id", "")],
            },
        },
        "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]},
    }


def _inbound_trojan(port: int, cfg: dict) -> dict:
    return {
        "tag":      "trojan-in",
        "listen":   "0.0.0.0",
        "port":     port,
        "protocol": "trojan",
        "settings": {
            "clients": [{"password": cfg.get("password", ""), "email": "user@fvpn"}],
            "fallbacks": [{"dest": 80}],
        },
        "streamSettings": {
            "network":     "tcp",
            "security":    "tls",
            "tlsSettings": {
                "alpn":         ["h2", "http/1.1"],
                "certificates": [
                    {
                        "certificateFile": "/etc/fvpn/ssl/cert.pem",
                        "keyFile":         "/etc/fvpn/ssl/key.pem",
                    }
                ],
            },
        },
        "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
    }


def _inbound_shadowsocks(port: int, cfg: dict) -> dict:
    return {
        "tag":      "ss-in",
        "listen":   "0.0.0.0",
        "port":     port,
        "protocol": "shadowsocks",
        "settings": {
            "method":   cfg.get("method", "aes-256-gcm"),
            "password": cfg.get("password", ""),
            "network":  "tcp,udp",
        },
    }


def _inbound_vmess(port: int, cfg: dict) -> dict:
    return {
        "tag":      "vmess-in",
        "listen":   "0.0.0.0",
        "port":     port,
        "protocol": "vmess",
        "settings": {
            "clients": [{"id": cfg.get("uuid", str(uuid.uuid4())), "alterId": 0}]
        },
        "streamSettings": {
            "network":       "ws",
            "wsSettings":    {"path": cfg.get("path", "/vmess")},
            "security":      "tls",
            "tlsSettings":   {
                "certificates": [
                    {
                        "certificateFile": "/etc/fvpn/ssl/cert.pem",
                        "keyFile":         "/etc/fvpn/ssl/key.pem",
                    }
                ]
            },
        },
    }


_INBOUND_MAP = {
    "vless":       _inbound_vless,
    "vlessreality": _inbound_vless,
    "trojan":      _inbound_trojan,
    # "shadowsocks" is intentionally NOT registered here — sing-box owns it
    # exclusively (see app/core/singbox.py). Both cores run with
    # network_mode: host; registering the same protocol name in both
    # _INBOUND_MAP dicts means both containers try to bind the identical
    # host port, and one crash-loops on "address already in use".
    "vmess":       _inbound_vmess,
}



###############################################################################
# FULL CONFIG BUILDER
###############################################################################

def build_xray_server_config(protocols: list[dict]) -> dict:
    """
    protocols: list of dicts with keys:
        name, port, config (dict with protocol-specific params)
    """
    inbounds: list[dict] = []
    seen_tags: set[str] = set()

    for p in protocols:
        name = p["name"].lower().replace("-", "")
        builder = _INBOUND_MAP.get(name)
        if not builder:
            logger.warning(f"Xray: no inbound builder for protocol '{p['name']}' — skipped")
            continue

        inbound = builder(p["port"], p.get("config", {}))

        base_tag = inbound["tag"]
        tag = base_tag
        i = 2
        while tag in seen_tags:
            tag = f"{base_tag}-{i}"
            i += 1
        inbound["tag"] = tag
        seen_tags.add(tag)
        inbounds.append(inbound)

    config: dict[str, Any] = {
        "log": {
            "loglevel": "warning",
            "access":   "/var/log/xray/access.log",
            "error":    "/var/log/xray/error.log",
        },
        "api": {
            "tag":      "api",
            "services": ["HandlerService", "LoggerService", "StatsService"],
        },
        "stats":  {},
        "policy": {
            "levels": {"0": {"statsUserUplink": True, "statsUserDownlink": True}},
            "system": {"statsInboundUplink": True, "statsInboundDownlink": True},
        },
        "inbounds": [
            {
                "tag":      "api-in",
                "listen":   "127.0.0.1",
                "port":     62789,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"},
            },
            *inbounds,
        ],
        "outbounds": [
            {"tag": "direct",  "protocol": "freedom",  "settings": {}},
            {"tag": "blocked", "protocol": "blackhole", "settings": {"response": {"type": "http"}}},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "ip":      ["geoip:private"], "outboundTag": "blocked"},
                {"type": "field", "domain":  ["geosite:category-ads-all"], "outboundTag": "blocked"},
                {"type": "field", "inboundTag": ["api-in"], "outboundTag": "api"},
                {"type": "field", "network": "tcp,udp",   "outboundTag": "direct"},
            ],
        },
    }
    return config


###############################################################################
# WRITE + RELOAD
###############################################################################

async def write_and_reload(protocols: list[dict], config_path: str = XRAY_CONFIG) -> bool:
    from app.core.config_apply import CoreConfig, apply_configs

    spec = CoreConfig("xray", Path(config_path), XRAY_CONTAINER,
                      XRAY_CONTAINER_BIN, build_xray_server_config(protocols))
    result = await apply_configs([spec])
    return result["xray"] is True


async def validate_config(config_path: str = XRAY_CONFIG) -> tuple[bool, str]:
    from app.core.config_apply import CoreConfig, validate_candidate

    spec = CoreConfig("xray", Path(config_path), XRAY_CONTAINER, XRAY_CONTAINER_BIN, {})
    return await validate_candidate(spec, Path(config_path))
