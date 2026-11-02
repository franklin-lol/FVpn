"""Consistent SQLite snapshots and isolated archive restoration checks.

Archives contain credentials. Keep them private and transfer only to trusted storage.
This module deliberately does not import application settings until the CLI runs.
"""

import argparse
import json
import math
import os
import shutil
import sqlite3
import stat
import sys
import tarfile
import tempfile
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Mapping, Protocol


MAX_ARCHIVE_BYTES = 4 * 1024**3
MAX_ARCHIVE_MEMBERS = 10000
SCHEMA_COLUMNS = {
    "users": {"id", "username", "hashed_password"},
    "nodes": {"id", "host"},
    "protocols": {"id", "node_id"},
    "subscriptions": {"id", "user_id", "token"},
    "event_logs": {"id"},
}


class BackupError(Exception):
    """Backup creation or isolated verification failed."""


class BackupSettings(Protocol):
    DATABASE_URL: str
    BACKUP_DIR: str
    XRAY_CONFIG: str
    SINGBOX_CONFIG: str
    CERT_PATH: str
    KEY_PATH: str


@dataclass(frozen=True)
class BackupResult:
    archive: Path
    size_bytes: int

    def metadata(self) -> dict[str, str | int | bool]:
        return {"archive": self.archive.name, "size_bytes": self.size_bytes, "verified": True}


def _database_path(database_url: str) -> Path:
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            value = database_url[len(prefix):]
            if value and value != ":memory:" and not value.startswith("file:") and "?" not in value and "#" not in value:
                return Path(value).resolve()
    raise BackupError("A file-backed SQLite database URL is required")


def _check_database(path: Path) -> None:
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise BackupError("Snapshot integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise BackupError("Snapshot foreign key check failed")
        for table, required in SCHEMA_COLUMNS.items():
            columns = {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}
            if not required <= columns:
                raise BackupError("Snapshot is missing the application schema")


def verify_backup(
    archive: Path, *, max_bytes: int = MAX_ARCHIVE_BYTES,
    max_members: int = MAX_ARCHIVE_MEMBERS,
) -> None:
    """Safely restore into a private temporary directory; never modify live data.

    Only regular files/directories under the documented archive roots are accepted.
    Extraction is manual so neither tar link semantics nor metadata can escape the
    private directory. Limits apply to the total expanded payload and member count.
    """
    try:
        with tempfile.TemporaryDirectory(prefix="fvpn-restore-") as temporary:
            root = Path(temporary)
            root.chmod(0o700)
            total = 0
            seen: set[str] = set()
            with tarfile.open(archive, "r:gz") as source:
                for count, member in enumerate(source, 1):
                    name = member.name
                    parts = PurePosixPath(name).parts
                    if (count > max_members or not parts or name.startswith("/")
                            or "\\" in name or ":" in name or ".." in parts
                            or name in seen or member.issparse()
                            or not (member.isfile() or member.isdir())
                            or parts[0] not in {"database", "config"}
                            or (parts[0] == "database" and name not in {"database", "database/fvpn.db"})):
                        raise BackupError("Unsafe archive member")
                    seen.add(name)
                    total += member.size
                    if member.size < 0 or total > max_bytes:
                        raise BackupError("Archive exceeds restoration limits")
                    target = root.joinpath(*parts)
                    if member.isdir():
                        target.mkdir(mode=0o700, parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    with closing(source.extractfile(member)) as stream, target.open("xb") as output:
                        target.chmod(0o600)
                        shutil.copyfileobj(stream, output, length=1024 * 1024)
            snapshot = root / "database" / "fvpn.db"
            if not snapshot.is_file():
                raise BackupError("Archive does not contain a database snapshot")
            _check_database(snapshot)
    except BackupError:
        raise
    except (OSError, sqlite3.Error, tarfile.TarError, EOFError, ValueError) as error:
        raise BackupError("Archive restoration verification failed") from error


def _snapshot(source: Path, destination: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout

    def progress(_status: int, _remaining: int, _total: int) -> None:
        if time.monotonic() >= deadline:
            raise BackupError("Database snapshot timed out")

    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=timeout)) as reader:
        with closing(sqlite3.connect(destination)) as writer:
            destination.chmod(0o600)
            reader.backup(writer, pages=256, progress=progress, sleep=min(timeout, 0.05))


def _add_config(archive: tarfile.TarFile, source: Path, name: str) -> None:
    if source.is_symlink():
        raise BackupError("Configuration symlinks are not supported")
    if not source.exists():
        return
    if not source.is_dir():
        raise BackupError("Configuration source must be a directory")
    archive.add(source, arcname=f"config/{name}", recursive=False)
    for child in sorted(source.rglob("*")):
        mode = child.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise BackupError("Configuration contains an unsupported file type")
        archive.add(child, arcname=f"config/{name}/{child.relative_to(source).as_posix()}", recursive=False)


def create_backup(
    database_url: str, backup_dir: Path, *, config_dirs: Mapping[str, Path] | None = None,
    timeout: float = 30, keep_days: int = 7,
) -> BackupResult:
    """Create, restore-verify and atomically publish a private archive.

    Every invocation owns its staging directory and UUID filename; concurrent API
    and cron invocations never share mutable snapshot files. Retention runs only
    after publication, and only against matching regular archive files.
    """
    if not math.isfinite(timeout) or timeout <= 0 or keep_days < 1:
        raise BackupError("Invalid backup timeout or retention")
    source = _database_path(database_url)
    backup_dir = Path(backup_dir)
    try:
        if backup_dir.is_symlink():
            raise BackupError("Backup directory cannot be a symlink")
        backup_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        backup_dir.chmod(0o700)
        with tempfile.TemporaryDirectory(prefix=".backup-", dir=backup_dir) as temporary:
            staging = Path(temporary)
            staging.chmod(0o700)
            snapshot = staging / "fvpn.db"
            _snapshot(source, snapshot, timeout)
            pending = staging / "archive.tar.gz"
            with pending.open("xb") as output:
                pending.chmod(0o600)
                with tarfile.open(fileobj=output, mode="w:gz", dereference=False) as archive:
                    archive.add(snapshot, arcname="database/fvpn.db")
                    for name, directory in (config_dirs or {}).items():
                        if not name or not name.isascii() or not all(c.isalnum() or c in "_-" for c in name):
                            raise BackupError("Invalid configuration archive label")
                        _add_config(archive, Path(directory), name)
                output.flush()
                os.fsync(output.fileno())
            verify_backup(pending)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            published = backup_dir / f"uniproxy_{stamp}_{uuid.uuid4().hex}.tar.gz"
            size = pending.stat().st_size
            os.replace(pending, published)
        cutoff = time.time() - keep_days * 86400
        for old in backup_dir.glob("uniproxy_*.tar.gz"):
            try:
                info = old.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_mtime < cutoff and old != published:
                    old.unlink()
            except FileNotFoundError:
                pass  # A concurrent successful invocation already pruned it.
        return BackupResult(published, size)
    except BackupError:
        raise
    except (OSError, sqlite3.Error, tarfile.TarError, ValueError) as error:
        raise BackupError("Backup creation failed") from error


def create_configured_backup(settings: BackupSettings) -> BackupResult:
    directories = {
        "xray": Path(settings.XRAY_CONFIG).parent,
        "singbox": Path(settings.SINGBOX_CONFIG).parent,
        "tls": Path(settings.CERT_PATH).parent,
    }
    if Path(settings.KEY_PATH).parent != directories["tls"]:
        directories["tls-key"] = Path(settings.KEY_PATH).parent
    return create_backup(settings.DATABASE_URL, Path(settings.BACKUP_DIR), config_dirs=directories)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify a private FVpn SQLite backup")
    parser.add_argument("--verify", type=Path, metavar="ARCHIVE")
    parser.add_argument("--backup-dir", type=Path)
    arguments = parser.parse_args()
    try:
        if arguments.verify is not None:
            verify_backup(arguments.verify)
            print(json.dumps({"verified": True}))
        else:
            from app.config import settings

            selected = settings.model_copy(update={"BACKUP_DIR": str(arguments.backup_dir)}) if arguments.backup_dir else settings
            print(json.dumps(create_configured_backup(selected).metadata()))
        return 0
    except BackupError:
        print("Backup failed; check database availability, permissions and configuration.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
