"""Generate disposable core-check inputs without reading installation files."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.core.singbox import build_singbox_server_config
from app.core.xray import build_xray_server_config
from app.lib.config_generator import ConfigGenerator, ProtocolConfig

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture.invalid")])
now = datetime.now(timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256()))
(root / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
(root / "key.pem").write_bytes(key.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
))
protocols = []
for index, protocol in enumerate(("vless", "trojan", "vmess", "hysteria2", "shadowsocks", "tuic", "shadowtls")):
    protocols.append({"name": protocol, "port": 10000 + index,
                      "config": ProtocolConfig.defaults(protocol, 10000 + index, {"sni": "fixture.invalid"})})
for core, builder in (("xray", build_xray_server_config), ("singbox", build_singbox_server_config)):
    (root / f"{core}.json").write_text(json.dumps(builder(protocols)))
    (root / f"{core}-empty.json").write_text(json.dumps(builder([])))

# Exercise the actual client builder, including the paired ShadowTLS outbound.
# WireGuard is deliberately absent: stored server keys are not client peers.
client = ConfigGenerator(domain="fixture.invalid")
for protocol in protocols:
    client.add_protocol(protocol["name"], "fixture.invalid", protocol["port"],
                        tag=f"fixture-{protocol['name']}", **protocol["config"])
(root / "singbox-client.json").write_text(client.generate("singbox"))

