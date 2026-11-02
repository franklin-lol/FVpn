"""Async SSH client using asyncssh"""

import asyncio
import logging
import os
import tempfile
import weakref
from pathlib import Path
from typing import Optional

import asyncssh


logger = logging.getLogger("uniproxy.ssh")
KNOWN_HOSTS_PATH = Path("/data/ssh_known_hosts")
# The deployment has one worker. Each loop serializes enrollment and reads
# across connections; filesystem work runs off the event loop.
_pin_locks: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def _read_pins(path: Path) -> bytes:
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return b""
    os.chmod(path, 0o600)
    return data


def _write_pins(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".ssh-known-hosts-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class _HostVerifier(asyncssh.SSHClient):
    def __init__(self, pins: bytes):
        self.pins = asyncssh.import_known_hosts(pins.decode("ascii"))
        self.accepted_key: asyncssh.SSHKey | None = None
        self.new_key = False

    def validate_host_public_key(self, host: str, addr: str, port: int,
                                 key: asyncssh.SSHKey) -> bool:
        # Match the configured host, not a resolved address shared by other
        # hosts. Nonstandard ports are separate OpenSSH identities.
        identity = host if port == 22 else f"[{host}]:{port}"
        trusted, authorities, revoked, *_ = self.pins.match(identity, "", None)
        if (key in revoked or (trusted and key not in trusted) or authorities
                or (self.accepted_key is not None and self.accepted_key != key)):
            logger.error("SSH host key rejected host=%s port=%s fingerprint=%s",
                         host, port, key.get_fingerprint("sha256"))
            return False
        self.accepted_key = key
        self.new_key = not trusted
        return True


class SSHClient:
    def __init__(self, host: str, port: int, username: str, private_key_pem: str,
                 *, known_hosts_path: Path | None = None):
        if not host or any(character.isspace() or character in ",*?!|[]" for character in host):
            raise ValueError("Invalid SSH host")
        self.host = host
        self.port = port
        self.username = username
        self.private_key_pem = private_key_pem
        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self.known_hosts_path = known_hosts_path or KNOWN_HOSTS_PATH
        self.host_key_fingerprint: str | None = None

    async def connect(self, timeout: int = 15):
        loop = asyncio.get_running_loop()
        lock = _pin_locks.setdefault(loop, asyncio.Lock())
        async with lock:
            pins = await asyncio.to_thread(_read_pins, self.known_hosts_path)
            verifier = _HostVerifier(pins)
            key = await asyncio.to_thread(asyncssh.import_private_key, self.private_key_pem)
            connection = await asyncssh.connect(
                self.host, port=self.port, username=self.username,
                client_keys=[key], client_factory=lambda: verifier,
                # Empty trust list activates the callback. None would bypass
                # host-key verification entirely in AsyncSSH 2.14.2.
                known_hosts=b"", connect_timeout=timeout,
            )
            try:
                if verifier.accepted_key is None:
                    raise RuntimeError("SSH server did not supply a verified public key")
                fingerprint = verifier.accepted_key.get_fingerprint("sha256")
                if verifier.new_key:
                    identity = self.host if self.port == 22 else f"[{self.host}]:{self.port}"
                    public_key = verifier.accepted_key.export_public_key("openssh").strip()
                    data = pins + (b"\n" if pins and not pins.endswith(b"\n") else b"")
                    data += identity.encode("ascii") + b" " + public_key + b"\n"
                    # Finish an atomic write even if the caller is cancelled;
                    # the enrollment lock must cover its whole lifetime.
                    write = asyncio.create_task(asyncio.to_thread(_write_pins, self.known_hosts_path, data))
                    try:
                        await asyncio.shield(write)
                    except asyncio.CancelledError:
                        await write
                        raise
                    logger.info("SSH host key enrolled host=%s port=%s fingerprint=%s",
                                self.host, self.port, fingerprint)
                self.host_key_fingerprint = fingerprint
            except BaseException:
                connection.close()
                await connection.wait_closed()
                raise
            self._conn = connection

    async def exec(self, cmd: str, timeout: int = 120) -> tuple[str, str, int]:
        if not self._conn:
            raise RuntimeError("SSH not connected")
        result = await asyncio.wait_for(
            self._conn.run(cmd, check=False),
            timeout=timeout,
        )
        return result.stdout, result.stderr, result.exit_status

    async def upload(self, local_path: str, remote_path: str):
        if not self._conn:
            raise RuntimeError("SSH not connected")
        async with self._conn.start_sftp_client() as sftp:
            await sftp.put(local_path, remote_path)

    async def upload_content(self, content: str, remote_path: str):
        if not self._conn:
            raise RuntimeError("SSH not connected")
        async with self._conn.start_sftp_client() as sftp:
            async with sftp.open(remote_path, "w") as f:
                await f.write(content)

    async def disconnect(self):
        if self._conn:
            self._conn.close()
            await self._conn.wait_closed()
            self._conn = None
