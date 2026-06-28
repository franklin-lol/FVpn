#!/usr/bin/env bash
# FVpn Installer v1.1
# One-command deploy: bash <(curl -s https://raw.githubusercontent.com/franklin-lol/FVpn/main/install.sh)
set -euo pipefail

###############################################################################
# GLOBALS
###############################################################################
VERSION="1.1.0"
PANEL_PORT=2095
XRAY_VERSION="1.8.24"
SINGBOX_VERSION="1.9.0"

LOG_FILE="/var/log/fvpn-install.log"

# Auto-detect project directory:
# If install.sh lives inside the cloned repo (docker-compose.yml is a sibling),
# use that directory. Otherwise clone into /opt/fvpn.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
if [[ -f "$SCRIPT_DIR/docker-compose.yml" ]]; then
    UNIPROXY_DIR="$SCRIPT_DIR"
else
    UNIPROXY_DIR="/opt/fvpn"
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[x]${NC} $*" | tee -a "$LOG_FILE"; exit 1; }
info() { echo -e "${BLUE}[>]${NC} $*" | tee -a "$LOG_FILE"; }

###############################################################################
# BANNER
###############################################################################
banner() {
cat << 'EOF'
 _____  _   _
|  ___|| | | |_ __ _ __  _ __
| |_   | | | | '_ \| '_ \| '_ \
|  _|  | |_| | |_) | | | | | | |
|_|     \___/| .__/|_| |_|_| |_|
             |_|
     Unified Proxy Management v1.1
EOF
}

###############################################################################
# OS DETECTION
###############################################################################
detect_os() {
    [[ -f /etc/os-release ]] || err "Cannot detect OS."
    # shellcheck disable=SC1091
    source /etc/os-release
    OS_NAME=$ID
    OS_VERSION=$VERSION_ID

    case "$OS_NAME" in
        ubuntu)
            [[ $(echo "$OS_VERSION >= 20.04" | bc -l) -eq 1 ]] || err "Ubuntu 20.04+ required (got $OS_VERSION)"
            PKG_MGR="apt-get"
            ;;
        debian)
            [[ $(echo "$OS_VERSION >= 11" | bc -l) -eq 1 ]] || err "Debian 11+ required (got $OS_VERSION)"
            PKG_MGR="apt-get"
            ;;
        *)
            err "Unsupported OS: $OS_NAME. Use Ubuntu 20.04+ or Debian 11+"
            ;;
    esac

    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  ARCH_SHORT="amd64" ;;
        aarch64) ARCH_SHORT="arm64" ;;
        *)        err "Unsupported arch: $ARCH" ;;
    esac

    log "OS: $OS_NAME $OS_VERSION | Arch: $ARCH | Project dir: $UNIPROXY_DIR"
}

###############################################################################
# DEPENDENCIES
###############################################################################
install_deps() {
    info "Installing system dependencies..."
    export DEBIAN_FRONTEND=noninteractive
    $PKG_MGR update -qq 2>>"$LOG_FILE"
    $PKG_MGR install -y -qq \
        curl wget git unzip jq bc openssl \
        python3 python3-pip python3-venv \
        certbot ufw ca-certificates \
        cron 2>>"$LOG_FILE"

    # Docker
    if ! command -v docker &>/dev/null; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh >>"$LOG_FILE" 2>&1
        systemctl enable docker --now
    fi

    # Docker Compose v2 plugin
    if ! docker compose version &>/dev/null 2>&1; then
        info "Installing Docker Compose plugin..."
        # Create plugin dir (often missing on fresh installs)
        mkdir -p /usr/local/lib/docker/cli-plugins
        COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)"
        curl -fsSL "$COMPOSE_URL" -o /usr/local/lib/docker/cli-plugins/docker-compose
        chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
        # Also expose as standalone binary for scripts that call `docker-compose`
        ln -sf /usr/local/lib/docker/cli-plugins/docker-compose /usr/local/bin/docker-compose
    fi

    log "Dependencies installed"
}

###############################################################################
# XRAY-CORE
# Xray release archive naming: Xray-linux-64.zip (x86_64), Xray-linux-arm64-v8a.zip
###############################################################################
install_xray() {
    info "Installing Xray-core $XRAY_VERSION..."

    local XRAY_ARCH
    case "$ARCH" in
        x86_64)  XRAY_ARCH="64" ;;
        aarch64) XRAY_ARCH="arm64-v8a" ;;
        *)        err "Unsupported arch for Xray: $ARCH" ;;
    esac

    local URL="https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${XRAY_ARCH}.zip"
    local TMP
    TMP=$(mktemp -d)

    info "Downloading: $URL"
    curl -fsSL "$URL" -o "$TMP/xray.zip" || err "Xray download failed: $URL"
    unzip -q "$TMP/xray.zip" -d "$TMP/xray"
    install -m 755 "$TMP/xray/xray" /usr/local/bin/xray
    rm -rf "$TMP"

    mkdir -p /usr/local/share/xray /etc/xray

    wget -qO /usr/local/share/xray/geoip.dat \
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat" \
        || warn "geoip.dat download failed (optional)"
    wget -qO /usr/local/share/xray/geosite.dat \
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat" \
        || warn "geosite.dat download failed (optional)"

    log "Xray-core installed: $(xray version 2>/dev/null | head -1)"
}

###############################################################################
# SING-BOX
###############################################################################
install_singbox() {
    info "Installing Sing-box $SINGBOX_VERSION..."
    local URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-${ARCH_SHORT}.tar.gz"
    local TMP
    TMP=$(mktemp -d)

    curl -fsSL "$URL" -o "$TMP/singbox.tar.gz" || err "Sing-box download failed: $URL"
    tar -xzf "$TMP/singbox.tar.gz" -C "$TMP"
    install -m 755 "$TMP/sing-box-${SINGBOX_VERSION}-linux-${ARCH_SHORT}/sing-box" /usr/local/bin/sing-box
    rm -rf "$TMP"

    mkdir -p /etc/sing-box
    log "Sing-box installed: $(sing-box version 2>/dev/null | head -1)"
}

###############################################################################
# CERTIFICATES
###############################################################################
setup_certs() {
    read -rp "$(echo -e "${BLUE}[?]${NC} Domain name (blank = self-signed): ")" DOMAIN

    mkdir -p /etc/fvpn/ssl

    if [[ -z "${DOMAIN:-}" ]]; then
        warn "No domain — generating self-signed certificate"
        openssl req -x509 -newkey rsa:4096 \
            -keyout /etc/fvpn/ssl/key.pem \
            -out    /etc/fvpn/ssl/cert.pem \
            -days 3650 -nodes \
            -subj "/CN=fvpn.local" 2>>"$LOG_FILE"
        DOMAIN="localhost"
        CERT_MODE="self-signed"
    else
        info "Requesting Let's Encrypt certificate for $DOMAIN..."
        # Kill anything on port 80 before standalone mode
        systemctl stop nginx 2>/dev/null || true
        fuser -k 80/tcp 2>/dev/null || true
        sleep 1

        if certbot certonly --standalone -d "$DOMAIN" \
            --non-interactive --agree-tos \
            --register-unsafely-without-email \
            --preferred-challenges http 2>>"$LOG_FILE"; then
            ln -sf "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" /etc/fvpn/ssl/cert.pem
            ln -sf "/etc/letsencrypt/live/$DOMAIN/privkey.pem"   /etc/fvpn/ssl/key.pem
            CERT_MODE="letsencrypt"
        else
            warn "Certbot failed (domain may not resolve to this IP) — using self-signed"
            openssl req -x509 -newkey rsa:4096 \
                -keyout /etc/fvpn/ssl/key.pem \
                -out    /etc/fvpn/ssl/cert.pem \
                -days 3650 -nodes \
                -subj "/CN=$DOMAIN" 2>>"$LOG_FILE"
            CERT_MODE="self-signed"
        fi
    fi

    log "Certificate: $CERT_MODE for ${DOMAIN}"
}

###############################################################################
# FIREWALL
###############################################################################
setup_firewall() {
    info "Configuring UFW firewall..."
    ufw --force reset >>"$LOG_FILE" 2>&1
    ufw default deny incoming  >>"$LOG_FILE" 2>&1
    ufw default allow outgoing >>"$LOG_FILE" 2>&1
    for PORT in 22 80 443 2095 2096 8080 8443; do
        ufw allow "$PORT/tcp" >>"$LOG_FILE" 2>&1
    done
    ufw allow 443/udp  >>"$LOG_FILE" 2>&1   # QUIC / Hysteria2
    ufw allow 8443/udp >>"$LOG_FILE" 2>&1
    ufw --force enable >>"$LOG_FILE" 2>&1
    log "Firewall configured"
}

###############################################################################
# VLESS REALITY KEY GENERATION
###############################################################################
gen_reality_keys() {
    if command -v xray &>/dev/null; then
        local REALITY_KEYS
        REALITY_KEYS=$(xray x25519 2>/dev/null || echo "")
        if [[ -n "$REALITY_KEYS" ]]; then
            REALITY_PRIVATE=$(echo "$REALITY_KEYS" | grep "Private key:" | awk '{print $3}')
            REALITY_PUBLIC=$(echo  "$REALITY_KEYS" | grep "Public key:"  | awk '{print $3}')
            log "VLESS Reality keys generated"
        fi
    fi
    REALITY_PRIVATE="${REALITY_PRIVATE:-}"
    REALITY_PUBLIC="${REALITY_PUBLIC:-}"
}

###############################################################################
# ENV MANAGEMENT
# Rule: if .env exists → preserve it, only append missing keys.
#       if .env doesn't exist → generate everything fresh.
###############################################################################

# Append key=value to file only if key is not already present
_ensure_key() {
    local key="$1" value="$2" file="$3"
    if ! grep -q "^${key}=" "$file" 2>/dev/null; then
        echo "${key}=${value}" >> "$file"
    fi
}

setup_env() {
    local env_file="$UNIPROXY_DIR/.env"

    if [[ -f "$env_file" ]]; then
        log ".env exists — preserving existing values, appending missing keys"
        # Read existing MASTER_PASSWORD so we can show it in the summary
        MASTER_PASS=$(grep "^MASTER_PASSWORD=" "$env_file" 2>/dev/null | cut -d= -f2 || true)
        REDIS_PASS=$(grep  "^REDIS_PASSWORD="  "$env_file" 2>/dev/null | cut -d= -f2 || true)
    else
        log "Generating fresh .env..."
        touch "$env_file"
        MASTER_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 20)
        REDIS_PASS=$(openssl rand -hex 16)
    fi

    # Auto-generate JWT secret if missing
    local jwt_secret
    jwt_secret=$(grep "^JWT_SECRET=" "$env_file" 2>/dev/null | cut -d= -f2 || true)
    [[ -z "$jwt_secret" ]] && jwt_secret=$(openssl rand -hex 32)

    # Use defaults if variables are empty (first run or env existed but missing keys)
    [[ -z "${MASTER_PASS:-}" ]] && MASTER_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 20)
    [[ -z "${REDIS_PASS:-}"  ]] && REDIS_PASS=$(openssl rand -hex 16)

    # Append only missing keys — never overwrite existing values
    _ensure_key "PANEL_PORT"           "$PANEL_PORT"                                    "$env_file"
    _ensure_key "DOMAIN"               "${DOMAIN:-localhost}"                            "$env_file"
    _ensure_key "CERT_PATH"            "/etc/fvpn/ssl/cert.pem"                         "$env_file"
    _ensure_key "KEY_PATH"             "/etc/fvpn/ssl/key.pem"                          "$env_file"
    _ensure_key "MASTER_PASSWORD"      "$MASTER_PASS"                                   "$env_file"
    _ensure_key "JWT_SECRET"           "$jwt_secret"                                    "$env_file"
    _ensure_key "JWT_EXPIRE_MINUTES"   "1440"                                           "$env_file"
    _ensure_key "DATABASE_URL"         "sqlite+aiosqlite:////data/fvpn.db"              "$env_file"
    _ensure_key "REDIS_PASSWORD"       "$REDIS_PASS"                                    "$env_file"
    _ensure_key "REDIS_URL"            "redis://:${REDIS_PASS}@redis:6379/0"            "$env_file"
    _ensure_key "CORS_ORIGINS"         "*"                                               "$env_file"
    _ensure_key "XRAY_BIN"            "/usr/local/bin/xray"                             "$env_file"
    _ensure_key "SINGBOX_BIN"         "/usr/local/bin/sing-box"                         "$env_file"
    _ensure_key "XRAY_CONFIG"         "/etc/xray/config.json"                           "$env_file"
    _ensure_key "SINGBOX_CONFIG"      "/etc/sing-box/config.json"                       "$env_file"
    _ensure_key "REALITY_PRIVATE_KEY" "${REALITY_PRIVATE:-}"                            "$env_file"
    _ensure_key "REALITY_PUBLIC_KEY"  "${REALITY_PUBLIC:-}"                             "$env_file"
    _ensure_key "TELEGRAM_TOKEN"      ""                                                 "$env_file"
    _ensure_key "TELEGRAM_ADMIN_IDS"  ""                                                 "$env_file"
    _ensure_key "HEALTH_CHECK_URL"    "http://www.gstatic.com/generate_204"             "$env_file"
    _ensure_key "HEALTH_CHECK_INTERVAL" "300"                                            "$env_file"
    _ensure_key "BACKUP_DIR"          "/data/backups"                                    "$env_file"
    _ensure_key "BACKUP_S3_BUCKET"    ""                                                 "$env_file"

    # System-level copy for reference (scripts, cron, etc.)
    mkdir -p /etc/fvpn
    cp "$env_file" /etc/fvpn/env

    log ".env ready at $env_file"
}

###############################################################################
# DEPLOY PANEL
###############################################################################
deploy_panel() {
    info "Deploying FVpn panel..."

    # If project dir doesn't have docker-compose.yml, clone the repo
    if [[ ! -f "$UNIPROXY_DIR/docker-compose.yml" ]]; then
        info "Cloning repository into $UNIPROXY_DIR..."
        git clone https://github.com/franklin-lol/FVpn "$UNIPROXY_DIR" \
            || err "git clone failed — check network and repo URL"
    fi

    cd "$UNIPROXY_DIR"

    # Build images and start (DOCKER_BUILDKIT=1 enables layer caching)
    DOCKER_BUILDKIT=1 docker compose up -d --build 2>>"$LOG_FILE" \
        || warn "Docker compose reported errors — check $LOG_FILE"

    log "Panel containers started"
}

###############################################################################
# SYSTEMD TIMER — self-healing every 5 min
###############################################################################
setup_services() {
    info "Configuring systemd timer..."

    cat > /etc/systemd/system/fvpn-watcher.service << UNIT
[Unit]
Description=FVpn Self-Healing Watcher
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=$UNIPROXY_DIR/scripts/self_healing.sh

[Install]
WantedBy=multi-user.target
UNIT

    cat > /etc/systemd/system/fvpn-watcher.timer << UNIT
[Unit]
Description=FVpn Health Check Timer

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT

    # Cert renewal
    echo "0 3 * * * root certbot renew --quiet --post-hook 'docker compose -f $UNIPROXY_DIR/docker-compose.yml restart nginx'" \
        > /etc/cron.d/fvpn-certrenew

    # Backup every 6h
    echo "0 */6 * * * root $UNIPROXY_DIR/scripts/backup.sh" \
        > /etc/cron.d/fvpn-backup

    systemctl daemon-reload
    systemctl enable --now fvpn-watcher.timer 2>/dev/null || true

    log "Systemd timer and cron jobs configured"
}

###############################################################################
# SUMMARY
###############################################################################
print_summary() {
    local IP
    IP=$(curl -4s --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    local PANEL_URL="http://$IP:$PANEL_PORT"
    [[ "${DOMAIN:-localhost}" != "localhost" ]] && PANEL_URL="https://${DOMAIN}:$PANEL_PORT"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          FVpn Installation Complete                  ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  Panel   : ${BLUE}${PANEL_URL}${NC}"
    echo -e "${GREEN}║${NC}  Username: ${YELLOW}admin${NC}"
    echo -e "${GREEN}║${NC}  Password: ${YELLOW}${MASTER_PASS}${NC}"
    echo -e "${GREEN}║${NC}  TLS     : ${CERT_MODE:-self-signed} / ${DOMAIN:-localhost}"
    echo -e "${GREEN}║${NC}  Logs    : $LOG_FILE"
    echo -e "${GREEN}║${NC}  Config  : $UNIPROXY_DIR/.env"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}  Telegram bot: add TELEGRAM_TOKEN + TELEGRAM_ADMIN_IDS to .env${NC}"
    echo -e "${YELLOW}  Then run:  docker compose restart bot${NC}"
    echo ""
}

###############################################################################
# MAIN
###############################################################################
main() {
    [[ $EUID -ne 0 ]] && err "Run as root: sudo bash install.sh"

    mkdir -p "$(dirname "$LOG_FILE")"
    touch "$LOG_FILE"

    banner
    detect_os
    install_deps
    install_xray
    install_singbox
    setup_certs
    setup_firewall
    gen_reality_keys
    setup_env        # must run before deploy_panel (creates .env)
    deploy_panel
    setup_services
    print_summary
}

main "$@"
