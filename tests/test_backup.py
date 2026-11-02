"""Backups must preserve committed SQLite data and restore only in isolation."""

import io
import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from app.core.backup import BackupError, create_backup, verify_backup


SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, hashed_password TEXT);
CREATE TABLE nodes (id INTEGER PRIMARY KEY, host TEXT);
CREATE TABLE protocols (id INTEGER PRIMARY KEY, node_id INTEGER REFERENCES nodes(id));
CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, user_id INTEGER REFERENCES users(id), token TEXT);
CREATE TABLE event_logs (id INTEGER PRIMARY KEY);
"""


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "live database.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    connection.execute("INSERT INTO users VALUES (1, 'committed', 'synthetic-hash')")
    connection.commit()
    yield path, connection
    connection.close()


def url(path):
    return "sqlite+aiosqlite:///" + path.as_posix()


def archived_database(archive, destination):
    with tarfile.open(archive, "r:gz") as source:
        with source.extractfile("database/fvpn.db") as stream:
            destination.write_bytes(stream.read())
    return sqlite3.connect(destination)


def test_snapshot_includes_wal_commits_and_excludes_uncommitted_changes(database, tmp_path):
    path, writer = database
    writer.execute("INSERT INTO users VALUES (2, 'not-committed', 'synthetic-hash')")
    config = tmp_path / "synthetic-xray"
    config.mkdir()
    (config / "config.json").write_text('{"synthetic": true}')

    result = create_backup(url(path), tmp_path / "backups", config_dirs={"xray": config})

    with archived_database(result.archive, tmp_path / "restored.db") as restored:
        assert restored.execute("SELECT username FROM users").fetchall() == [("committed",)]
    with tarfile.open(result.archive) as archive:
        assert archive.extractfile("config/xray/config.json").read() == b'{"synthetic": true}'
        assert not any(member.name.endswith(("-wal", "-shm")) for member in archive)
    assert result.size_bytes == result.archive.stat().st_size
    assert writer.execute("SELECT username FROM users WHERE id=2").fetchone() == ("not-committed",)
    writer.rollback()
    assert verify_backup(result.archive) is None
    assert list(result.archive.parent.glob(".backup-*")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX secret file modes")
def test_archive_and_directory_are_private(database, tmp_path):
    path, _ = database
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir(mode=0o755)
    result = create_backup(url(path), backup_dir, config_dirs={})
    assert backup_dir.stat().st_mode & 0o777 == 0o700
    assert result.archive.stat().st_mode & 0o777 == 0o600


def test_missing_database_does_not_create_database_or_publish_archive(tmp_path):
    missing = tmp_path / "missing.db"
    with pytest.raises(BackupError):
        create_backup(url(missing), tmp_path / "backups", config_dirs={})
    assert not missing.exists()
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []


@pytest.mark.parametrize("database_url", ["postgresql://localhost/database", "sqlite:///:memory:",
                                          "sqlite:///file:live.db?mode=rw", "sqlite://server/live.db"])
def test_rejects_non_file_sqlite_urls(database_url, tmp_path):
    with pytest.raises(BackupError):
        create_backup(database_url, tmp_path / "backups", config_dirs={})


def test_corrupt_database_is_not_published(tmp_path):
    path = tmp_path / "broken.db"
    path.write_bytes(b"this is not sqlite")
    with pytest.raises(BackupError):
        create_backup(url(path), tmp_path / "backups", config_dirs={})
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []
    assert list((tmp_path / "backups").glob(".backup-*")) == []


def test_missing_application_schema_is_not_published(tmp_path):
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER)")
    with pytest.raises(BackupError):
        create_backup(url(path), tmp_path / "backups", config_dirs={})
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []


def test_foreign_key_violation_is_not_published(database, tmp_path):
    path, connection = database
    connection.execute("INSERT INTO subscriptions VALUES(1, 999, 'synthetic-token')")
    connection.commit()
    with pytest.raises(BackupError):
        create_backup(url(path), tmp_path / "backups", config_dirs={})
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []


def test_retention_removes_only_expired_matching_regular_archives(database, tmp_path):
    path, _ = database
    backups = tmp_path / "backups"
    backups.mkdir()
    old = backups / "uniproxy_20000101_000000_old.tar.gz"
    unrelated = backups / "operator.tar.gz"
    recent = backups / "uniproxy_20990101_000000_recent.tar.gz"
    directory = backups / "uniproxy_directory.tar.gz"
    for candidate in (old, unrelated, recent):
        candidate.write_bytes(b"synthetic archive")
    directory.mkdir()
    expired = time.time() - 8 * 86400
    os.utime(old, (expired, expired))
    os.utime(unrelated, (expired, expired))
    os.utime(directory, (expired, expired))

    create_backup(url(path), backups, config_dirs={}, keep_days=7)

    assert not old.exists()
    assert unrelated.exists() and recent.exists() and directory.is_dir()


@pytest.mark.parametrize("name, kind", [("../outside", tarfile.REGTYPE),
                                       ("/outside", tarfile.REGTYPE),
                                       ("config/xray/link", tarfile.SYMTYPE),
                                       ("config/xray/link", tarfile.LNKTYPE),
                                       ("config/xray/device", tarfile.CHRTYPE),
                                       ("config\\..\\outside", tarfile.REGTYPE)])
def test_restore_verification_rejects_unsafe_archive_members(tmp_path, name, kind):
    archive_path = tmp_path / "hostile.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = "../../outside" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
        member.size = 0
        archive.addfile(member, io.BytesIO(b""))
    with pytest.raises(BackupError):
        verify_backup(archive_path)
    assert not (tmp_path / "outside").exists()


def test_restore_verification_rejects_oversized_archive_before_extraction(tmp_path):
    archive_path = tmp_path / "bomb.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("database/fvpn.db")
        member.size = 1025
        archive.addfile(member, io.BytesIO(b"0" * 1025))
    with pytest.raises(BackupError):
        verify_backup(archive_path, max_bytes=1024)


def test_restore_verification_rejects_too_many_archive_members(tmp_path):
    archive_path = tmp_path / "many-members.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for index in range(3):
            archive.addfile(tarfile.TarInfo(f"config/item{index}"), io.BytesIO(b""))
    with pytest.raises(BackupError):
        verify_backup(archive_path, max_members=2)


def test_cli_creates_verified_archive_using_only_synthetic_settings(database, tmp_path):
    path, _ = database
    environment = os.environ.copy()
    environment.update({
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "backend"),
        "DATABASE_URL": url(path), "BACKUP_DIR": str(tmp_path / "unused"),
        "XRAY_CONFIG": str(tmp_path / "missing-xray" / "config.json"),
        "SINGBOX_CONFIG": str(tmp_path / "missing-singbox" / "config.json"),
        "CERT_PATH": str(tmp_path / "missing-tls" / "cert.pem"),
        "KEY_PATH": str(tmp_path / "missing-tls" / "key.pem"),
    })
    created = subprocess.run(
        [sys.executable, "-m", "app.core.backup", "--backup-dir", str(tmp_path / "backups")],
        env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert created.returncode == 0, created.stderr
    result = json.loads(created.stdout)
    assert result["verified"] is True
    archive = tmp_path / "backups" / result["archive"]
    assert verify_backup(archive) is None
    checked = subprocess.run(
        [sys.executable, "-m", "app.core.backup", "--verify", str(archive)],
        env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=10,
    )
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout) == {"verified": True}


def test_restore_verification_rejects_duplicate_members(tmp_path):
    archive_path = tmp_path / "duplicate.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for _ in range(2):
            archive.addfile(tarfile.TarInfo("database/fvpn.db"), io.BytesIO(b""))
    with pytest.raises(BackupError):
        verify_backup(archive_path)


def test_restore_verification_rejects_corrupt_snapshot_without_touching_live(database, tmp_path):
    path, connection = database
    archive_path = tmp_path / "corrupt.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        member = tarfile.TarInfo("database/fvpn.db")
        member.size = 7
        archive.addfile(member, io.BytesIO(b"corrupt"))
    with pytest.raises(BackupError):
        verify_backup(archive_path)
    assert connection.execute("SELECT username FROM users").fetchall() == [("committed",)]
    assert path.exists()


def test_failed_config_collection_preserves_existing_archives(database, tmp_path):
    path, _ = database
    config = tmp_path / "not-a-directory"
    config.write_bytes(b"synthetic")
    backups = tmp_path / "backups"
    backups.mkdir()
    previous = backups / "uniproxy_20000101_000000_previous.tar.gz"
    previous.write_bytes(b"previous backup")
    os.utime(previous, (0, 0))
    with pytest.raises(BackupError):
        create_backup(url(path), backups, config_dirs={"xray": config})
    assert list(backups.iterdir()) == [previous]


def test_locked_database_times_out_without_publishing(database, tmp_path):
    path, connection = database
    connection.rollback()
    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("BEGIN EXCLUSIVE")
    started = time.monotonic()
    try:
        with pytest.raises(BackupError):
            create_backup(url(path), tmp_path / "backups", config_dirs={}, timeout=0.1)
    finally:
        connection.rollback()
    assert time.monotonic() - started < 2
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []


def test_concurrent_backups_publish_distinct_verified_archives(database, tmp_path):
    path, _ = database
    barrier = threading.Barrier(2)

    def run_backup():
        barrier.wait(timeout=5)
        return create_backup(url(path), tmp_path / "backups", config_dirs={})

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: run_backup(), range(2)))
    assert first.archive != second.archive
    for result in (first, second):
        assert verify_backup(result.archive) is None


def test_api_runs_backup_in_thread_and_reports_verified_metadata(database, tmp_path, monkeypatch):
    import asyncio

    from app.api import system

    path, _ = database
    for key, value in {
        "DATABASE_URL": url(path), "BACKUP_DIR": str(tmp_path / "backups"),
        "XRAY_CONFIG": str(tmp_path / "xray" / "config.json"),
        "SINGBOX_CONFIG": str(tmp_path / "singbox" / "config.json"),
        "CERT_PATH": str(tmp_path / "tls" / "cert.pem"),
        "KEY_PATH": str(tmp_path / "tls" / "key.pem"),
    }.items():
        monkeypatch.setattr(system.settings, key, value)
    main_thread = threading.get_ident()
    worker_threads = []
    real_backup = system.create_configured_backup

    def observed_backup(settings):
        worker_threads.append(threading.get_ident())
        return real_backup(settings)

    monkeypatch.setattr(system, "create_configured_backup", observed_backup)
    response = asyncio.run(system.trigger_backup())
    assert response["status"] == "backup_complete"
    assert response["verified"] is True
    assert response["size_bytes"] > 0
    assert worker_threads[0] != main_thread
    assert verify_backup(tmp_path / "backups" / response["archive"]) is None


def test_api_failure_does_not_expose_database_or_secret_values(tmp_path, monkeypatch):
    import asyncio

    from fastapi import HTTPException

    from app.api import system

    monkeypatch.setattr(system.settings, "DATABASE_URL", url(tmp_path / "private-secret.db"))
    monkeypatch.setattr(system.settings, "BACKUP_DIR", str(tmp_path / "backups"))
    with pytest.raises(HTTPException) as error:
        asyncio.run(system.trigger_backup())
    assert error.value.status_code == 500
    assert "private-secret" not in str(error.value.detail)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_config_symlink_cannot_include_files_outside_allowed_directory(database, tmp_path):
    path, _ = database
    config = tmp_path / "config"
    config.mkdir()
    secret = tmp_path / "unrelated-secret"
    secret.write_bytes(b"synthetic secret")
    (config / "escape").symlink_to(secret)
    with pytest.raises(BackupError):
        create_backup(url(path), tmp_path / "backups", config_dirs={"xray": config})
    assert list((tmp_path / "backups").glob("*.tar.gz")) == []
