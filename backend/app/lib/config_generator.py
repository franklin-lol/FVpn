"""
uniproxy-lib — ConfigGenerator
Generates client configs for: sing-box, clash, hiddify, shadowrocket, v2rayng
Protocols: hysteria2, shadowsocks, shadowtls, vless-reality, trojan, tuic, wireguard, ssh
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import yaml


###############################################################################
# BALANCER
###############################################################################
@dataclass
class Balancer:
    strategy: Literal["latency", "round-robin", "random"] = "latency"
    url: str = "http://www.gstatic.com/generate_204"
    interval: str = "1m"
    tolerance: int = 50          # ms — for latency strategy
    idle_timeout: str = "30m"


###############################################################################
# PROTOCOL CONFIG (internal repr)
###############################################################################
@dataclass
class ProxyEntry:
    name:      str              # hysteria2 | shadowsocks | shadowtls | vless | trojan | tuic | wireguard
    host:      str
    port:      int
    tag:       str              # display name in client
    extra:     dict = field(default_factory=dict)

    @property
    def proto(self) -> str:
        return self.name.lower().replace("-", "")


###############################################################################
# PROTOCOL DEFAULTS
###############################################################################
class ProtocolConfig:
    @staticmethod
    def defaults(name: str, port: int, extra: dict) -> dict:
        import secrets
        defaults_map = {
            "hysteria2":   {"password": secrets.token_hex(16), "obfs": "salamander", "obfs_password": secrets.token_hex(8), "tls_insecure": False},
            "shadowsocks": {"method": "aes-256-gcm", "password": secrets.token_hex(16)},
            "shadowtls":   {"password": secrets.token_hex(16), "sni": "www.apple.com", "version": 3},
            "vless":       {"uuid": str(uuid.uuid4()), "flow": "xtls-rprx-vision", "sni": "www.cloudflare.com", "public_key": "", "short_id": secrets.token_hex(4)},
            "trojan":      {"password": secrets.token_hex(16), "sni": "your-domain.com", "tls_insecure": False},
            "tuic":        {"uuid": str(uuid.uuid4()), "password": secrets.token_hex(16), "congestion": "bbr"},
            "wireguard":   {"private_key": "", "public_key": "", "preshared_key": "", "dns": "1.1.1.1,8.8.8.8", "mtu": 1420},
            "ssh":         {"username": "root", "private_key": ""},
        }
        base = defaults_map.get(name, {})
        base.update(extra)
        return base


###############################################################################
# MAIN GENERATOR
###############################################################################
class ConfigGenerator:
    def __init__(self, domain: str = "your-domain.com", core: str = "sing-box"):
        self.domain   = domain
        self.core     = core
        self._proxies: list[ProxyEntry] = []
        self._fallback_chain: list[str] = []

    def add_protocol(self, name: str, host: str, port: int,
                     tag: Optional[str] = None, **extra) -> "ConfigGenerator":
        entry = ProxyEntry(
            name=name,
            host=host,
            port=port,
            tag=tag or f"{name}-{host}:{port}",
            extra=extra,
        )
        self._proxies.append(entry)
        return self

    def set_fallback(self, chain: list[str]) -> "ConfigGenerator":
        self._fallback_chain = chain
        return self

    def generate(self, fmt: str, balancer: Optional[Balancer] = None) -> str:
        bl = balancer or Balancer()
        dispatch = {
            "sing-box":      self._gen_singbox,
            "singbox":       self._gen_singbox,
            "clash":         self._gen_clash,
            "hiddify":       self._gen_hiddify,
            "shadowrocket":  self._gen_shadowrocket,
            "v2rayng":       self._gen_v2rayng,
            "base64":        self._gen_base64,
        }
        fn = dispatch.get(fmt.lower())
        if not fn:
            raise ValueError(f"Unknown format: {fmt}. Supported: {list(dispatch.keys())}")
        return fn(bl)

    def to_base64(self, config: str) -> str:
        return base64.urlsafe_b64encode(config.encode()).decode()

    def export(self, fmt: str, path: str, balancer: Optional[Balancer] = None):
        content = self.generate(fmt, balancer)
        with open(path, "w") as f:
            f.write(content)

    def validate(self) -> list[str]:
        """Returns list of validation errors (empty = valid)"""
        errors = []
        if not self._proxies:
            errors.append("No protocols added")
        for p in self._proxies:
            if p.port < 1 or p.port > 65535:
                errors.append(f"{p.tag}: invalid port {p.port}")
            if not p.host:
                errors.append(f"{p.tag}: empty host")
        return errors

    ############################################################################
    # SING-BOX
    ############################################################################
    def _gen_singbox(self, bl: Balancer) -> str:
        outbounds = []
        tags = []

        for p in self._proxies:
            ob = self._singbox_outbound(p)
            if ob:
                outbounds.append(ob)
                tags.append(p.tag)

        # URLTest selector (balancer)
        outbounds.append({
            "type": "urltest",
            "tag":  "auto",
            "outbounds": tags,
            "url": bl.url,
            "interval": bl.interval,
            "tolerance": bl.tolerance,
            "idle_timeout": bl.idle_timeout,
        })
        # Manual selector
        outbounds.append({
            "type": "selector",
            "tag":  "proxy",
            "outbounds": ["auto"] + tags,
            "default": "auto",
        })
        # Built-ins
        outbounds += [
            {"type": "direct", "tag": "direct"},
            {"type": "block",  "tag": "block"},
            {"type": "dns",    "tag": "dns-out"},
        ]

        config = {
            "log":    {"level": "info", "timestamp": True},
            "dns":    self._singbox_dns(),
            "inbounds": [
                {"type": "tun",   "tag": "tun-in",  "inet4_address": "172.19.0.1/30", "auto_route": True, "strict_route": True},
                {"type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 2080},
                {"type": "http",  "tag": "http-in",  "listen": "127.0.0.1", "listen_port": 2081},
                {"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2082},
            ],
            "outbounds": outbounds,
            "route": self._singbox_route(),
        }
        return json.dumps(config, indent=2, ensure_ascii=False)

    def _singbox_outbound(self, p: ProxyEntry) -> Optional[dict]:
        base = {"tag": p.tag, "server": p.host, "server_port": p.port}
        e = p.extra

        if p.proto == "hysteria2":
            return {**base, "type": "hysteria2",
                    "password": e.get("password", ""),
                    "obfs": {"type": e.get("obfs", "salamander"), "password": e.get("obfs_password", "")} if e.get("obfs") else None,
                    "tls": {"enabled": True, "insecure": e.get("tls_insecure", False), "server_name": e.get("sni", p.host)}}

        if p.proto == "shadowsocks":
            return {**base, "type": "shadowsocks",
                    "method": e.get("method", "aes-256-gcm"),
                    "password": e.get("password", "")}

        if p.proto == "shadowtls":
            return {"type": "shadowtls", "tag": p.tag,
                    "server": p.host, "server_port": p.port,
                    "password": e.get("password", ""),
                    "version": e.get("version", 3),
                    "tls": {"enabled": True, "server_name": e.get("sni", "www.apple.com")}}

        if p.proto in ("vless", "vlessreality"):
            return {**base, "type": "vless",
                    "uuid": e.get("uuid", str(uuid.uuid4())),
                    "flow": e.get("flow", "xtls-rprx-vision"),
                    "tls": {"enabled": True, "server_name": e.get("sni", "www.cloudflare.com"),
                            "utls": {"enabled": True, "fingerprint": "chrome"},
                            "reality": {"enabled": True,
                                        "public_key": e.get("public_key", ""),
                                        "short_id":   e.get("short_id", "")}}}

        if p.proto == "trojan":
            return {**base, "type": "trojan",
                    "password": e.get("password", ""),
                    "tls": {"enabled": True, "server_name": e.get("sni", p.host),
                            "insecure": e.get("tls_insecure", False)}}

        if p.proto == "tuic":
            return {**base, "type": "tuic",
                    "uuid": e.get("uuid", str(uuid.uuid4())),
                    "password": e.get("password", ""),
                    "congestion_control": e.get("congestion", "bbr"),
                    "tls": {"enabled": True, "server_name": e.get("sni", p.host)}}

        if p.proto == "wireguard":
            return {"type": "wireguard", "tag": p.tag,
                    "server": p.host, "server_port": p.port,
                    "private_key": e.get("private_key", ""),
                    "peer_public_key": e.get("public_key", ""),
                    "pre_shared_key": e.get("preshared_key", ""),
                    "dns": e.get("dns", "1.1.1.1"),
                    "mtu": e.get("mtu", 1420)}

        if p.proto == "ssh":
            return {**base, "type": "ssh",
                    "user": e.get("username", "root"),
                    "private_key": e.get("private_key", "")}

        return None

    def _singbox_dns(self) -> dict:
        return {
            "servers": [
                {"tag": "dns-remote", "address": "https://1.1.1.1/dns-query", "strategy": "prefer_ipv4"},
                {"tag": "dns-local",  "address": "local", "detour": "direct"},
                {"tag": "dns-block",  "address": "rcode://success"},
            ],
            "rules": [
                {"rule_set": "geosite-ads", "server": "dns-block"},
                {"outbound": "any", "server": "dns-local"},
                {"rule_set": "geosite-geolocation-!cn", "server": "dns-remote"},
            ],
            "final": "dns-remote",
            "independent_cache": True,
        }

    def _singbox_route(self) -> dict:
        return {
            "rule_set": [
                {"type": "remote", "tag": "geosite-ads",
                 "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-category-ads-all.srs"},
                {"type": "remote", "tag": "geosite-geolocation-!cn",
                 "format": "binary", "url": "https://raw.githubusercontent.com/SagerNet/sing-geosite/rule-set/geosite-geolocation-not-cn.srs"},
            ],
            "rules": [
                {"protocol": "dns", "outbound": "dns-out"},
                {"rule_set": "geosite-ads", "outbound": "block"},
                {"rule_set": "geosite-geolocation-!cn", "outbound": "proxy"},
            ],
            "final": "direct",
            "auto_detect_interface": True,
        }

    ############################################################################
    # CLASH
    ############################################################################
    def _gen_clash(self, bl: Balancer) -> str:
        proxies = []
        names = []

        for p in self._proxies:
            px = self._clash_proxy(p)
            if px:
                proxies.append(px)
                names.append(p.tag)

        config = {
            "mixed-port": 7890,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            "external-controller": "127.0.0.1:9090",
            "dns": {
                "enable": True,
                "enhanced-mode": "fake-ip",
                "nameserver": ["1.1.1.1", "8.8.8.8"],
            },
            "proxies": proxies,
            "proxy-groups": [
                {
                    "name": "PROXY",
                    "type": "url-test" if bl.strategy == "latency" else bl.strategy,
                    "proxies": names,
                    "url": bl.url,
                    "interval": 60,
                    "tolerance": bl.tolerance,
                },
                {
                    "name": "Auto",
                    "type": "select",
                    "proxies": ["PROXY"] + names,
                },
            ],
            "rules": [
                "GEOIP,LAN,DIRECT",
                "GEOIP,CN,DIRECT",
                "MATCH,PROXY",
            ],
        }
        return yaml.dump(config, allow_unicode=True, sort_keys=False)

    def _clash_proxy(self, p: ProxyEntry) -> Optional[dict]:
        base = {"name": p.tag, "server": p.host, "port": p.port}
        e = p.extra

        if p.proto == "hysteria2":
            return {**base, "type": "hysteria2",
                    "password": e.get("password", ""),
                    "obfs": e.get("obfs", "salamander"),
                    "obfs-password": e.get("obfs_password", ""),
                    "sni": e.get("sni", p.host),
                    "skip-cert-verify": e.get("tls_insecure", False)}

        if p.proto == "shadowsocks":
            return {**base, "type": "ss",
                    "cipher": e.get("method", "aes-256-gcm"),
                    "password": e.get("password", "")}

        if p.proto in ("vless", "vlessreality"):
            return {**base, "type": "vless",
                    "uuid": e.get("uuid", ""),
                    "flow": e.get("flow", "xtls-rprx-vision"),
                    "tls": True,
                    "servername": e.get("sni", ""),
                    "reality-opts": {"public-key": e.get("public_key", ""),
                                     "short-id":   e.get("short_id", "")},
                    "client-fingerprint": "chrome",
                    "network": "tcp"}

        if p.proto == "trojan":
            return {**base, "type": "trojan",
                    "password": e.get("password", ""),
                    "sni": e.get("sni", p.host),
                    "skip-cert-verify": e.get("tls_insecure", False)}

        if p.proto == "tuic":
            return {**base, "type": "tuic",
                    "uuid": e.get("uuid", ""),
                    "password": e.get("password", ""),
                    "congestion-controller": e.get("congestion", "bbr"),
                    "sni": e.get("sni", p.host)}

        return None

    ############################################################################
    # HIDDIFY
    ############################################################################
    def _gen_hiddify(self, bl: Balancer) -> str:
        # Hiddify uses sing-box JSON under the hood with profile metadata
        sb_config = json.loads(self._gen_singbox(bl))
        hiddify = {
            "hiddify": {
                "name": "UniProxy",
                "author": "UniProxy v1",
                "support": self.domain,
            },
            **sb_config,
        }
        return json.dumps(hiddify, indent=2, ensure_ascii=False)

    ############################################################################
    # SHADOWROCKET
    ############################################################################
    def _gen_shadowrocket(self, bl: Balancer) -> str:
        """Shadowrocket uses base64-encoded URI list"""
        lines = [f"# UniProxy — {self.domain}", f"# Generated {__import__('datetime').datetime.utcnow()}", ""]
        for p in self._proxies:
            uri = self._uri(p)
            if uri:
                lines.append(uri)
        return "\n".join(lines)

    ############################################################################
    # V2RAYNG
    ############################################################################
    def _gen_v2rayng(self, bl: Balancer) -> str:
        """v2rayNG uses base64-encoded URI list identical to Shadowrocket"""
        uris = [self._uri(p) for p in self._proxies]
        uris = [u for u in uris if u]
        raw = "\n".join(uris)
        return base64.b64encode(raw.encode()).decode()

    ############################################################################
    # BASE64 (universal)
    ############################################################################
    def _gen_base64(self, bl: Balancer) -> str:
        uris = [self._uri(p) or "" for p in self._proxies]
        raw  = "\n".join(filter(None, uris))
        return base64.b64encode(raw.encode()).decode()

    ############################################################################
    # URI BUILDERS
    ############################################################################
    def _uri(self, p: ProxyEntry) -> Optional[str]:
        e = p.extra
        tag = p.tag

        if p.proto == "shadowsocks":
            user_info = base64.b64encode(f"{e.get('method','aes-256-gcm')}:{e.get('password','')}".encode()).decode()
            return f"ss://{user_info}@{p.host}:{p.port}#{_url_encode(tag)}"

        if p.proto == "hysteria2":
            params = f"obfs={e.get('obfs','salamander')}&obfs-password={e.get('obfs_password','')}&sni={e.get('sni',p.host)}"
            return f"hysteria2://{e.get('password','')}@{p.host}:{p.port}?{params}#{_url_encode(tag)}"

        if p.proto in ("vless", "vlessreality"):
            params = (f"type=tcp&security=reality"
                      f"&pbk={e.get('public_key','')}&sid={e.get('short_id','')}"
                      f"&fp=chrome&sni={e.get('sni','')}&flow={e.get('flow','xtls-rprx-vision')}")
            return f"vless://{e.get('uuid','')}@{p.host}:{p.port}?{params}#{_url_encode(tag)}"

        if p.proto == "trojan":
            params = f"sni={e.get('sni',p.host)}&allowInsecure={int(e.get('tls_insecure',False))}"
            return f"trojan://{e.get('password','')}@{p.host}:{p.port}?{params}#{_url_encode(tag)}"

        if p.proto == "tuic":
            params = f"congestion_control={e.get('congestion','bbr')}&sni={e.get('sni',p.host)}"
            return f"tuic://{e.get('uuid','')}:{e.get('password','')}@{p.host}:{p.port}?{params}#{_url_encode(tag)}"

        if p.proto == "wireguard":
            return (f"wireguard://{p.host}:{p.port}"
                    f"?publickey={e.get('public_key','')}&psk={e.get('preshared_key','')}"
                    f"&mtu={e.get('mtu',1420)}#{_url_encode(tag)}")

        return None


def _url_encode(s: str) -> str:
    from urllib.parse import quote
    return quote(s, safe="")
