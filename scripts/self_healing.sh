#!/usr/bin/env bash
# UniProxy Self-Healing Script
# Runs via systemd timer every 5 minutes
# Checks: nodes reachability, local services, cert expiry, disk space
set -euo pipefail

LOG="/var/log/uniproxy.log"
DIR="/opt/uniproxy"
HEALTH_URL="http://www.gstatic.com/generate_204"
DISK_WARN_PCT=85
CERT_WARN_DAYS=30

log()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SELFHEAL] $*" | tee -a "$LOG"; }
warn() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]     $*" | tee -a "$LOG"; }
err()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR]    $*" | tee -a "$LOG"; }

###############################################################################
# 1. CHECK LOCAL PROXY SERVICES
###############################################################################
check_services() {
    for svc in xray sing-box; do
        if systemctl list-units --type=service | grep -q "${svc}.service"; then
            status=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
            if [[ "$status" != "active" ]]; then
                warn "$svc is $status — restarting"
                systemctl restart "$svc" && log "$svc restarted successfully" || err "$svc restart failed"
            fi
        fi
    done
}

###############################################################################
# 2. CHECK DOCKER CONTAINERS
###############################################################################
check_docker() {
    if ! command -v docker &>/dev/null; then return; fi

    for container in uniproxy-backend uniproxy-nginx uniproxy-frontend uniproxy-bot; do
        state=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null || echo "missing")
        if [[ "$state" != "running" ]]; then
            warn "Container $container is '$state' — restarting"
            docker start "$container" 2>>"$LOG" && log "$container started" || {
                err "$container start failed — running docker compose up"
                cd "$DIR" && docker compose up -d >>"$LOG" 2>&1
            }
        fi
    done
}

###############################################################################
# 3. CHECK INTERNET CONNECTIVITY
###############################################################################
check_internet() {
    if ! curl -fsS --max-time 5 -o /dev/null "$HEALTH_URL"; then
        warn "Internet connectivity check failed — may be temporary"
    fi
}

###############################################################################
# 4. CHECK DISK SPACE
###############################################################################
check_disk() {
    used_pct=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
    if [[ "$used_pct" -gt "$DISK_WARN_PCT" ]]; then
        warn "Disk usage at ${used_pct}% — cleaning Docker"
        docker system prune -f --volumes >>"$LOG" 2>&1 || true
        # Rotate logs
        find /var/log -name "*.log" -size +100M -exec truncate -s 50M {} \;
        log "Disk cleanup complete — now at $(df / | awk 'NR==2 {print $5}')"
    fi
}

###############################################################################
# 5. CHECK TLS CERT EXPIRY
###############################################################################
check_cert() {
    local cert="/etc/uniproxy/ssl/cert.pem"
    [[ -f "$cert" ]] || return

    expiry=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)
    if [[ -n "$expiry" ]]; then
        expiry_ts=$(date -d "$expiry" +%s 2>/dev/null || date -j -f "%b %d %T %Y %Z" "$expiry" +%s 2>/dev/null)
        now_ts=$(date +%s)
        days_left=$(( (expiry_ts - now_ts) / 86400 ))

        if [[ "$days_left" -le "$CERT_WARN_DAYS" ]]; then
            warn "TLS cert expires in ${days_left} days — attempting renewal"
            certbot renew --non-interactive >>"$LOG" 2>&1 && {
                log "Certificate renewed successfully"
                docker compose -f "$DIR/docker-compose.yml" restart nginx >>"$LOG" 2>&1 || true
            } || err "Certificate renewal failed — manual intervention required"
        fi
    fi
}

###############################################################################
# 6. CHECK BACKEND API HEALTH
###############################################################################
check_api() {
    if ! curl -fsS --max-time 5 -o /dev/null "http://localhost:8000/health"; then
        warn "Backend API health check failed — restarting container"
        docker restart uniproxy-backend >>"$LOG" 2>&1 || true
        sleep 5
        # Verify recovery
        if curl -fsS --max-time 5 -o /dev/null "http://localhost:8000/health"; then
            log "Backend recovered"
        else
            err "Backend still down after restart"
        fi
    fi
}

###############################################################################
# MAIN
###############################################################################
main() {
    log "Self-healing cycle started"
    check_services
    check_docker
    check_internet
    check_disk
    check_cert
    check_api
    log "Self-healing cycle complete"
}

main
