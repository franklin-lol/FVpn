#!/usr/bin/env bash
# FVpn watcher. Operates only on containers belonging to this Compose checkout.
set -euo pipefail
umask 077

LOG="/var/log/fvpn-watcher.log"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HEALTH_URL="http://www.gstatic.com/generate_204"
DISK_WARN_PCT=85
CERT_WARN_DAYS=30

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SELFHEAL] $*" | tee -a "$LOG"; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]     $*" | tee -a "$LOG"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR]    $*" | tee -a "$LOG"; }

compose() {
    docker compose --project-directory "$DIR" -f "$DIR/docker-compose.yml" "$@"
}

check_docker() {
    local service container state services
    services=$(compose config --services)
    while IFS= read -r service; do
        container=$(compose ps --all --quiet "$service")
        # Missing services may have been intentionally omitted at deployment.
        [[ -n "$container" ]] || continue
        while IFS= read -r container; do
            state=$(docker inspect --format='{{.State.Status}}' "$container")
            if [[ "$state" == exited || "$state" == created ]]; then
                warn "FVpn service $service is '$state' — starting"
                if compose start "$service" >>"$LOG" 2>&1; then
                    log "$service started"
                else
                    err "$service start failed; inspect its Compose logs"
                fi
                break
            fi
        done <<<"$container"
    done <<<"$services"
}

check_internet() {
    if ! curl -fsS --max-time 5 -o /dev/null "$HEALTH_URL"; then
        warn "Internet connectivity check failed — may be temporary"
    fi
}

check_disk() {
    local used_pct
    used_pct=$(df -P "$DIR" | awk 'NR==2 {gsub(/%/, "", $5); print $5}')
    if [[ "$used_pct" -gt "$DISK_WARN_PCT" ]]; then
        warn "Project filesystem usage is ${used_pct}%. Review FVpn logs and backups; no automatic data deletion is performed."
    fi
}

check_cert() {
    local cert="/etc/fvpn/ssl/cert.pem"
    [[ -f "$cert" ]] || return 0
    if ! openssl x509 -in "$cert" -noout -checkend "$((CERT_WARN_DAYS * 86400))" >/dev/null 2>&1; then
        warn "TLS certificate is invalid or expires within $CERT_WARN_DAYS days. Check /etc/cron.d/fvpn-certrenew and the installer log; self-signed certificates require manual replacement."
    fi
}

check_api() {
    local container health
    container=$(compose ps --quiet backend)
    [[ -n "$container" ]] || return 0
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")
    if [[ "$health" == unhealthy ]]; then
        warn "FVpn backend health check failed — restarting its Compose service"
        if compose restart backend >>"$LOG" 2>&1; then
            log "Backend restart requested; Docker health checks will verify recovery"
        else
            err "Backend restart failed; inspect its Compose logs"
        fi
    fi
}

main() {
    [[ -f "$DIR/docker-compose.yml" ]] || { err "Compose checkout not found at $DIR"; exit 1; }
    command -v docker >/dev/null 2>&1 || { err "Docker is unavailable"; exit 1; }
    mkdir -p /etc/fvpn
    # Do not restart nginx while renewal temporarily owns the HTTP port.
    exec 9>/etc/fvpn/cert-renew.lock
    flock -n 9 || exit 0
    log "Self-healing cycle started"
    check_docker
    check_internet
    check_disk
    check_cert
    check_api
    log "Self-healing cycle complete"
}

main
