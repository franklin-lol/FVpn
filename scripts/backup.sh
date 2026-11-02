#!/usr/bin/env bash
# Run the same verified SQLite backup used by the admin API inside the backend.
set -euo pipefail
umask 077

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$PROJECT_DIR"

# BACKUP_DIR is a path inside the backend container's persistent /data volume.
# Without an override, the helper reads the backend's configured BACKUP_DIR.
BACKUP_ARGS=()
if [[ -n "${BACKUP_DIR:-}" ]]; then
    BACKUP_ARGS+=(--backup-dir "$BACKUP_DIR")
fi
RESULT=$(docker compose exec -T backend python -m app.core.backup "${BACKUP_ARGS[@]}")
printf '[BACKUP] %s\n' "$RESULT"

# Optional host AWS CLI upload: stream the private archive from the container.
# No host bind mount, secret contents, or AWS output is written to logs.
UPLOAD_BUCKET="${BACKUP_S3_BUCKET:-}"
if [[ -z "${BACKUP_S3_BUCKET+x}" ]]; then
    if ! UPLOAD_BUCKET=$(docker compose exec -T backend python -c \
        'from app.config import settings; print(settings.BACKUP_S3_BUCKET)' 2>/dev/null); then
        printf '[BACKUP] S3 settings unavailable; verified local archive retained\n' >&2
        UPLOAD_BUCKET=""
    fi
fi
if [[ -n "$UPLOAD_BUCKET" ]]; then
    if command -v aws >/dev/null 2>&1; then
        ARCHIVE=$(printf '%s' "$RESULT" | docker compose exec -T backend python -c \
            'import json,sys; print(json.load(sys.stdin)["archive"])')
        READ_ARCHIVE='
import os
import shutil
import sys
from pathlib import Path
from app.config import settings

root = Path(sys.argv[1] or settings.BACKUP_DIR)
name = sys.argv[2]
if Path(name).name != name or not name.startswith("uniproxy_") or not name.endswith(".tar.gz"):
    raise SystemExit("Invalid archive name")
fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
with os.fdopen(fd, "rb") as source:
    shutil.copyfileobj(source, sys.stdout.buffer)
'
        if docker compose exec -T backend python -c "$READ_ARCHIVE" "${BACKUP_DIR:-}" "$ARCHIVE" \
            | aws s3 cp - "s3://$UPLOAD_BUCKET/uniproxy/$ARCHIVE" --only-show-errors >/dev/null 2>&1; then
            printf '[BACKUP] S3 upload complete\n'
        else
            printf '[BACKUP] S3 upload failed; verified local archive retained\n' >&2
        fi
    else
        printf '[BACKUP] S3 upload skipped: host AWS CLI unavailable\n' >&2
    fi
fi
