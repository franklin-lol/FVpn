"""Real loopback handshakes, synthetic keys and private temporary pin files."""

import asyncio
import stat

import asyncssh
import pytest

from app.core.ssh import SSHClient


def test_first_seen_key_cannot_change_during_same_handshake():
    from app.core.ssh import _HostVerifier

    verifier = _HostVerifier(b"")
    first_key = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    changed_key = asyncssh.generate_private_key("ssh-ed25519").convert_to_public()
    assert verifier.validate_host_public_key("fixture.invalid", "127.0.0.1", 22, first_key)
    assert not verifier.validate_host_public_key("fixture.invalid", "127.0.0.1", 22, changed_key)


def test_first_contact_persists_openssh_pin_and_reports_fingerprint(tmp_path):
    async def scenario():
        host_key = asyncssh.generate_private_key("ssh-ed25519")
        client_key = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
        authenticated = []

        class Server(asyncssh.SSHServer):
            def begin_auth(self, username):
                authenticated.append(username)
                return False

        server = await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[host_key])
        pin_file = tmp_path / "pins" / "known_hosts"
        try:
            port = server.get_port()
            for _ in range(2):
                client = SSHClient("127.0.0.1", port, "fixture", client_key, known_hosts_path=pin_file)
                await client.connect()
                assert client.host_key_fingerprint == host_key.get_fingerprint("sha256")
                await client.disconnect()
            stored = pin_file.read_text()
            assert stored.startswith(f"[127.0.0.1]:{port} ssh-ed25519 ")
            assert len(stored.splitlines()) == 1
            assert "PRIVATE" not in stored
            assert stat.S_IMODE(pin_file.stat().st_mode) == 0o600
            assert authenticated == ["fixture", "fixture"]
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_changed_key_is_rejected_before_authentication(tmp_path):
    async def scenario():
        client_key = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
        authenticated = []

        class Server(asyncssh.SSHServer):
            def begin_auth(self, username):
                authenticated.append(username)
                return False

        original = asyncssh.generate_private_key("ssh-ed25519")
        server = await asyncssh.create_server(Server, "127.0.0.1", 0, server_host_keys=[original])
        port = server.get_port()
        pins = tmp_path / "known_hosts"
        client = SSHClient("127.0.0.1", port, "fixture", client_key, known_hosts_path=pins)
        await client.connect()
        await client.disconnect()
        before = pins.read_bytes()
        server.close()
        await server.wait_closed()
        replacement = await asyncssh.create_server(
            Server, "127.0.0.1", port, server_host_keys=[asyncssh.generate_private_key("ssh-ed25519")],
        )
        try:
            client = SSHClient("127.0.0.1", port, "fixture", client_key, known_hosts_path=pins)
            with pytest.raises(asyncssh.HostKeyNotVerifiable):
                await client.connect()
            with pytest.raises(RuntimeError, match="not connected"):
                await client.exec("must never run")
            assert authenticated == ["fixture"]
            assert pins.read_bytes() == before
        finally:
            replacement.close()
            await replacement.wait_closed()

    asyncio.run(scenario())


@pytest.mark.parametrize("same_host", [False, True])
def test_concurrent_first_contacts_preserve_both_pins(tmp_path, same_host):
    async def scenario():
        class Server(asyncssh.SSHServer):
            def begin_auth(self, username):
                return False

        servers = [await asyncssh.create_server(
            Server, "127.0.0.1", 0, server_host_keys=[asyncssh.generate_private_key("ssh-ed25519")],
        ) for _ in range(2)]
        private_key = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
        pins = tmp_path / "known_hosts"
        if same_host:
            servers_to_connect = [servers[0], servers[0]]
        else:
            servers_to_connect = servers
        clients = [SSHClient("127.0.0.1", server.get_port(), "fixture", private_key,
                             known_hosts_path=pins) for server in servers_to_connect]
        try:
            await asyncio.gather(*(client.connect() for client in clients))
            assert len(pins.read_text().splitlines()) == (1 if same_host else 2)
            await asyncio.gather(*(client.disconnect() for client in clients))
        finally:
            for server in servers:
                server.close()
                await server.wait_closed()

    asyncio.run(scenario())


def test_pin_write_failure_never_exposes_connection(tmp_path, monkeypatch):
    import app.core.ssh as ssh_module

    def fail_write(path, data):
        raise OSError("fixture disk failure")

    monkeypatch.setattr(ssh_module, "_write_pins", fail_write)

    async def scenario():
        class Server(asyncssh.SSHServer):
            def begin_auth(self, username):
                return False

        server = await asyncssh.create_server(
            Server, "127.0.0.1", 0, server_host_keys=[asyncssh.generate_private_key("ssh-ed25519")],
        )
        private_key = asyncssh.generate_private_key("ssh-ed25519").export_private_key().decode()
        client = SSHClient("127.0.0.1", server.get_port(), "fixture", private_key,
                           known_hosts_path=tmp_path / "known_hosts")
        try:
            with pytest.raises(OSError, match="fixture disk failure"):
                await client.connect()
            with pytest.raises(RuntimeError, match="not connected"):
                await client.exec("must never run")
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(scenario())


def test_self_heal_closes_ssh_and_redacts_exception_details(monkeypatch, caplog):
    from types import SimpleNamespace

    import app.core.ssh as ssh_module
    from app.core.self_heal import SelfHealService

    closed = []

    class SSH:
        def __init__(self, *args):
            pass

        async def connect(self, timeout):
            pass

        async def exec(self, command):
            raise RuntimeError("private-key-SENTINEL")

        async def disconnect(self):
            closed.append(True)

    monkeypatch.setattr(ssh_module, "SSHClient", SSH)
    node = SimpleNamespace(id=1, name="fixture", host="fixture.invalid", ssh_port=22,
                           ssh_user="fixture", ssh_key="private-key-SENTINEL")
    asyncio.run(SelfHealService()._try_restart_node(node))
    assert closed == [True]
    assert "private-key-SENTINEL" not in caplog.text
