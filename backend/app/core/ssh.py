"""Async SSH client using asyncssh"""

import asyncio
import asyncssh
from typing import Optional


class SSHClient:
    def __init__(self, host: str, port: int, username: str, private_key_pem: str):
        self.host = host
        self.port = port
        self.username = username
        self.private_key_pem = private_key_pem
        self._conn: Optional[asyncssh.SSHClientConnection] = None

    async def connect(self, timeout: int = 15):
        key = asyncssh.import_private_key(self.private_key_pem)
        self._conn = await asyncssh.connect(
            self.host,
            port=self.port,
            username=self.username,
            client_keys=[key],
            known_hosts=None,       # skip host key verification (production: use known_hosts)
            connect_timeout=timeout,
        )

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
