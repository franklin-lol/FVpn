"""Client exports never disclose server-side WireGuard key material."""

import asyncio
import base64
import json
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.lib.config_generator import ConfigGenerator, ProtocolConfig, ProxyEntry


FORMATS = ["singbox", "sing-box", "hiddify", "clash", "shadowrocket", "v2rayng", "base64"]
SECRET = "server-private-SENTINEL"


@pytest.mark.parametrize("fmt", FORMATS)
def test_new_vmess_client_and_server_share_persisted_uuid_and_transport(fmt):
    import yaml

    from app.core.xray import build_xray_server_config

    credentials = ProtocolConfig.defaults("vmess", 443, {"sni": "fixture.invalid"})
    assert str(UUID(credentials["uuid"])) == credentials["uuid"]
    original = dict(credentials)
    server = build_xray_server_config([{"name": "vmess", "port": 443, "config": credentials}])
    inbound = next(row for row in server["inbounds"] if row.get("protocol") == "vmess")
    server_uuid = inbound["settings"]["clients"][0]["id"]
    client = ConfigGenerator().add_protocol("vmess", "fixture.invalid", 443, **credentials).generate(fmt)
    if fmt in {"singbox", "sing-box", "hiddify"}:
        outbound = next(row for row in json.loads(client)["outbounds"] if row["type"] == "vmess")
        assert outbound["uuid"] == server_uuid
        assert outbound["transport"] == {"type": "ws", "path": inbound["streamSettings"]["wsSettings"]["path"]}
        assert outbound["tls"]["enabled"] is True
    elif fmt == "clash":
        outbound = yaml.safe_load(client)["proxies"][0]
        assert outbound["uuid"] == server_uuid
        assert outbound["network"] == "ws"
        assert outbound["ws-opts"]["path"] == credentials["path"]
        assert outbound["tls"] is True
    else:
        if fmt in {"base64", "v2rayng"}:
            client = base64.b64decode(client).decode()
        uri = next(line for line in client.splitlines() if line.startswith("vmess://"))
        outbound = json.loads(base64.b64decode(uri.removeprefix("vmess://")))
        assert outbound["id"] == server_uuid
        assert outbound["net"] == "ws"
        assert outbound["path"] == credentials["path"]
        assert outbound["tls"] == "tls"
    assert credentials == original


def test_explicit_vmess_uuid_is_preserved_for_new_protocol():
    explicit = "11111111-1111-4111-8111-111111111111"
    assert ProtocolConfig.defaults("vmess", 443, {"uuid": explicit})["uuid"] == explicit


@pytest.mark.parametrize("fmt", FORMATS)
def test_wireguard_is_excluded_from_every_export(fmt):
    generator = ConfigGenerator()
    generator.add_protocol("wireguard", "wg.invalid", 51820, private_key=SECRET, preshared_key=SECRET)
    generator.add_protocol("shadowsocks", "safe.invalid", 443, password="fixture-password")
    result = generator.generate(fmt)
    if fmt in {"base64", "v2rayng"}:
        result = base64.b64decode(result).decode()
    assert SECRET not in result
    assert "wg.invalid" not in result
    assert "wireguard" not in result
    assert "safe.invalid" in result


@pytest.mark.parametrize("serializer", ["_singbox_outbound", "_clash_proxy", "_uri"])
def test_individual_serializers_reject_wireguard(serializer):
    entry = ProxyEntry("wireguard", "wg.invalid", 51820, "wg", {"private_key": SECRET})
    assert getattr(ConfigGenerator(), serializer)(entry) is None


@pytest.mark.parametrize("fmt", FORMATS)
def test_wireguard_only_export_has_actionable_error(fmt):
    generator = ConfigGenerator().add_protocol("wireguard", "wg.invalid", 51820, private_key=SECRET)
    with pytest.raises(ValueError, match="No compatible client protocols"):
        generator.generate(fmt)


def test_shadowtls_uses_shadowsocks_wrapper_and_hidden_detour():
    generator = ConfigGenerator().add_protocol(
        "shadowtls", "tls.invalid", 443, tag="wrapped", password="shared-pass",
        method="aes-256-gcm", sni="cover.invalid",
    )
    config = json.loads(generator.generate("singbox"))
    outbounds = {outbound["tag"]: outbound for outbound in config["outbounds"]}
    assert outbounds["wrapped"]["type"] == "shadowsocks"
    assert outbounds["wrapped"]["password"] == "shared-pass"
    assert outbounds["wrapped"]["server"] == "tls.invalid"
    assert outbounds["wrapped"]["server_port"] == 443
    assert outbounds["wrapped"]["detour"] == "wrapped-shadowtls"
    assert outbounds["wrapped-shadowtls"]["type"] == "shadowtls"
    assert outbounds["wrapped-shadowtls"]["password"] == "shared-pass"
    assert outbounds["auto"]["outbounds"] == ["wrapped"]


def test_singbox_uses_typed_dns_servers_for_pinned_core():
    config = json.loads(ConfigGenerator().add_protocol(
        "shadowsocks", "fixture.invalid", 443, password="synthetic",
    ).generate("singbox"))
    assert config["dns"]["servers"][0]["type"] == "https"
    assert all("address" not in server for server in config["dns"]["servers"])
    assert not {"dns", "block"} & {outbound["type"] for outbound in config["outbounds"]}
    assert config["route"]["rules"][0] == {"protocol": "dns", "action": "hijack-dns"}
    assert config["inbounds"][0]["address"] == ["172.19.0.1/30"]
    assert config["route"]["default_domain_resolver"] == "dns-local"


def test_wireguard_only_subscription_returns_recoverable_error_and_preserves_record(tmp_path):
    from app.api.subscriptions import fetch_subscription
    from app.database import Base
    from app.models import Node, Protocol, Subscription, User

    async def scenario():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'exports.sqlite'}")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            node = Node(name="fixture", host="wg.invalid")
            user = User(username="fixture", hashed_password="unused")
            db.add_all([node, user])
            await db.flush()
            protocol = Protocol(node_id=node.id, name="wireguard", port=51820,
                                config={"private_key": SECRET})
            sub = Subscription(user_id=user.id, format="singbox")
            db.add_all([protocol, sub])
            await db.commit()
            with pytest.raises(HTTPException) as error:
                await fetch_subscription(sub.token, "singbox", db)
            assert error.value.status_code == 409
            assert "compatible" in error.value.detail.lower()
            assert protocol.config["private_key"] == SECRET
        await engine.dispose()

    asyncio.run(scenario())
