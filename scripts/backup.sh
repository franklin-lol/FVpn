#!/usr/bin/env bash
# UniProxy Backup Script — runs every 6h via cron
set -euo pipefail

LOG="/var/log/uniproxy.log"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE="$BACKUP_DIR/uniproxy_$TIMESTAMP.tar.gz"
KEEP_DAYS=7

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [BACKUP] $*" | tee -a "$LOG"; }

mkdir -p "$BACKUP_DIR"

log "Starting backup → $ARCHIVE"

# Collect items
ITEMS=()
[[ -f /data/uniproxy.db    ]] && ITEMS+=(/data/uniproxy.db)
[[ -d /etc/uniproxy        ]] && ITEMS+=(/etc/uniproxy)
[[ -d /etc/xray            ]] && ITEMS+=(/etc/xray)
[[ -d /etc/sing-box        ]] && ITEMS+=(/etc/sing-box)
[[ -d /etc/letsencrypt     ]] && ITEMS+=(/etc/letsencrypt)

if [[ ${#ITEMS[@]} -eq 0 ]]; then
    log "Nothing to back up"
    exit 0
fi

tar -czf "$ARCHIVE" "${ITEMS[@]}" 2>>"$LOG"
SIZE=$(du -sh "$ARCHIVE" | cut -f1)
log "Archive: $ARCHIVE ($SIZE)"

# S3 upload (optional)
if [[ -n "${BACKUP_S3_BUCKET:-}" ]] && command -v aws &>/dev/null; then
    log "Uploading to s3://$BACKUP_S3_BUCKET/uniproxy/"
    aws s3 cp "$ARCHIVE" "s3://$BACKUP_S3_BUCKET/uniproxy/$(basename "$ARCHIVE")" >>"$LOG" 2>&1 \
        && log "S3 upload OK" \
        || log "S3 upload failed (continuing)"
fi

# Prune old local backups
find "$BACKUP_DIR" -name "uniproxy_*.tar.gz" -mtime +$KEEP_DAYS -delete
COUNT=$(find "$BACKUP_DIR" -name "uniproxy_*.tar.gz" | wc -l)
log "Backup complete. $COUNT archive(s) retained (>${KEEP_DAYS}d pruned)"
