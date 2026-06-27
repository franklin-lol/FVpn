#!/usr/bin/env bash
# UniProxy Installer v1.0
# One-command full deployment: bash <(curl -s https://raw.githubusercontent.com/your-repo/UniProxy/main/install.sh)
set -euo pipefail

###############################################################################
# GLOBALS
###############################################################################
UNIPROXY_DIR="/opt/uniproxy"
LOG_FILE="/var/log/uniproxy-install.log"
VERSION="1.0.0"
PANEL_PORT=2095
XRAY_VERSION="1.8.10"
SINGBOX_VERSION="1.9.0"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[!]${NC} $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "${RED}[✗]${NC} $*" | tee -a "$LOG_FILE"; exit 1; }
info() { echo -e "${BLUE}[→]${NC} $*" | tee -a "$LOG_FILE"; }

###############################################################################
# BANNER
###############################################################################
banner() {
cat <<'EOF'
 _   _       _ ____                      
| | | |_ __ (_)  _ \ _ __ _____  ___   _
| | | | '_ \| | |_) | '__/ _ \ \/ / | | |
| |_| | | | | |  __/| | | (_) >  <| |_| |
 \___/|_| |_|_|_|   |_|  \___/_/\_\\__, |
                                    |___/ 
       Unified Proxy Management v1.0
EOF
}

###############################################################################
# OS DETECTION
###############################################################################
detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_NAME=$ID
        OS_VERSION=$VERSION_ID
    else
        err "Cannot detect OS. Supported: Ubuntu 20.04+, Debian 11+"
    fi

    case "$OS_NAME" in
        ubuntu)
            [[ $(echo "$OS_VERSION >= 20.04" | bc) -eq 1 ]] || err "Ubuntu 20.04+ required. Got: $OS_VERSION"
            PKG_MGR="apt-get"
            ;;
        debian)
            [[ $(echo "$OS_VERSION >= 11" | bc) -eq 1 ]] || err "Debian 11+ required. Got: $OS_VERSION"
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

    log "OS: $OS_NAME $OS_VERSION | Arch: $ARCH"
}

###############################################################################
# DEPENDENCIES
###############################################################################
install_deps() {
    info "Installing system dependencies..."
    export DEBIAN_FRONTEND=noninteractive
    $PKG_MGR update -qq
    $PKG_MGR install -y -qq \
        curl wget git unzip jq bc openssl \
        python3 python3-pip python3-venv \
        certbot ufw systemd ca-certificates \
        nginx supervisor cron 2>>"$LOG_FILE"

    # Docker
    if ! command -v docker &>/dev/null; then
        info "Installing Docker..."
        curl -fsSL https://get.docker.com | sh >>"$LOG_FILE" 2>&1
        systemctl enable docker --now
    fi

    # Docker Compose v2
    if ! docker compose version &>/dev/null 2>&1; then
        COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$ARCH"
        curl -fsSL "$COMPOSE_URL" -o /usr/local/bin/docker-compose
        chmod +x /usr/local/bin/docker-compose
        ln -sf /usr/local/bin/docker-compose /usr/local/lib/docker/cli-plugins/docker-compose
    fi

    log "Dependencies installed"
}

###############################################################################
# XRAY-CORE
###############################################################################
install_xray() {
    info "Installing Xray-core $XRAY_VERSION..."
    local URL="https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${ARCH_SHORT}.zip"
    local TMP=$(mktemp -d)
    curl -fsSL "$URL" -o "$TMP/xray.zip"
    unzip -q "$TMP/xray.zip" -d "$TMP/xray"
    install -m 755 "$TMP/xray/xray" /usr/local/bin/xray
    rm -rf "$TMP"

    mkdir -p /usr/local/share/xray /etc/xray
    # Download geoip/geosite
    curl -fsSL "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-${ARCH_SHORT}.zip" || true
    wget -qO /usr/local/share/xray/geoip.dat \
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geoip.dat" || warn "geoip.dat download failed (optional)"
    wget -qO /usr/local/share/xray/geosite.dat \
        "https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/geosite.dat" || warn "geosite.dat download failed (optional)"

    log "Xray-core installed: $(xray version | head -1)"
}

###############################################################################
# SING-BOX
###############################################################################
install_singbox() {
    info "Installing Sing-box $SINGBOX_VERSION..."
    local URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VERSION}/sing-box-${SINGBOX_VERSION}-linux-${ARCH_SHORT}.tar.gz"
    local TMP=$(mktemp -d)
    curl -fsSL "$URL" -o "$TMP/singbox.tar.gz"
    tar -xzf "$TMP/singbox.tar.gz" -C "$TMP"
    install -m 755 "$TMP/sing-box-${SINGBOX_VERSION}-linux-${ARCH_SHORT}/sing-box" /usr/local/bin/sing-box
    rm -rf "$TMP"
    mkdir -p /etc/sing-box
    log "Sing-box installed: $(sing-box version | head -1)"
}

###############################################################################
# CERTIFICATES
###############################################################################
setup_certs() {
    read -rp "$(echo -e "${BLUE}[?]${NC} Domain name (leave blank for self-signed): ")" DOMAIN

    mkdir -p /etc/uniproxy/ssl

    if [[ -z "$DOMAIN" ]]; then
        warn "No domain — generating self-signed certificate"
        openssl req -x509 -newkey rsa:4096 -keyout /etc/uniproxy/ssl/key.pem \
            -out /etc/uniproxy/ssl/cert.pem -days 3650 -nodes \
            -subj "/CN=uniproxy.local" 2>>"$LOG_FILE"
        DOMAIN="uniproxy.local"
        CERT_MODE="self-signed"
    else
        info "Obtaining Let's Encrypt certificate for $DOMAIN..."
        # Stop nginx temporarily if running
        systemctl stop nginx 2>/dev/null || true
        certbot certonly --standalone -d "$DOMAIN" --non-interactive \
            --agree-tos --register-unsafely-without-email \
            --preferred-challenges http 2>>"$LOG_FILE" || {
            warn "Certbot failed — falling back to self-signed"
            openssl req -x509 -newkey rsa:4096 -keyout /etc/uniproxy/ssl/key.pem \
                -out /etc/uniproxy/ssl/cert.pem -days 3650 -nodes \
                -subj "/CN=$DOMAIN" 2>>"$LOG_FILE"
            CERT_MODE="self-signed"
        }
        if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
            ln -sf "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" /etc/uniproxy/ssl/cert.pem
            ln -sf "/etc/letsencrypt/live/$DOMAIN/privkey.pem"   /etc/uniproxy/ssl/key.pem
            CERT_MODE="letsencrypt"
        fi
    fi

    log "Certificate: $CERT_MODE for $DOMAIN"
    echo "DOMAIN=$DOMAIN" >> /etc/uniproxy/env
}

###############################################################################
# FIREWALL
###############################################################################
setup_firewall() {
    info "Configuring UFW firewall..."
    ufw --force reset >>"$LOG_FILE" 2>&1
    ufw default deny incoming
    ufw default allow outgoing
    for PORT in 22 80 443 2095 2096 8080 8443; do
        ufw allow "$PORT/tcp"
    done
    ufw allow 443/udp   # QUIC/HTTP3 for Hysteria2
    ufw allow 8443/udp
    ufw --force enable
    log "Firewall configured: ports 22,80,443,2095,2096,8080,8443"
}

###############################################################################
# DEPLOY PANEL
###############################################################################
deploy_panel() {
    info "Deploying UniProxy panel..."
    mkdir -p "$UNIPROXY_DIR"

    # Clone or copy project files
    if [[ -d "/tmp/uniproxy-src" ]]; then
        cp -r /tmp/uniproxy-src/* "$UNIPROXY_DIR/"
    else
        # In production: git clone https://github.com/your-repo/UniProxy "$UNIPROXY_DIR"
        warn "Source not found at /tmp/uniproxy-src — using Docker pull"
    fi

    # Generate secrets
    MASTER_PASS=$(openssl rand -base64 24 | tr -d '/+=' | head -c 20)
    JWT_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)

    cat > /etc/uniproxy/env <<EOF
# UniProxy Environment
PANEL_PORT=$PANEL_PORT
MASTER_PASSWORD=$MASTER_PASS
JWT_SECRET=$JWT_SECRET
DB_PASSWORD=$DB_PASSWORD
UNIPROXY_DIR=$UNIPROXY_DIR
DOMAIN=${DOMAIN:-localhost}
CERT_PATH=/etc/uniproxy/ssl/cert.pem
KEY_PATH=/etc/uniproxy/ssl/key.pem
EOF

    # Copy env to project
    cp /etc/uniproxy/env "$UNIPROXY_DIR/.env"

    # Docker compose up
    cd "$UNIPROXY_DIR"
    docker compose pull >>"$LOG_FILE" 2>&1 || warn "Docker pull skipped — images may need building"
    docker compose up -d --build >>"$LOG_FILE" 2>&1 || warn "Docker compose failed — check $LOG_FILE"

    log "Panel deployed"
}

###############################################################################
# SYSTEMD SERVICES
###############################################################################
setup_services() {
    info "Creating systemd services..."

    # UniProxy watcher (self-healing)
    cat > /etc/systemd/system/uniproxy-watcher.service <<'UNIT'
[Unit]
Description=UniProxy Self-Healing Watcher
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
ExecStart=/opt/uniproxy/scripts/self_healing.sh
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

    cat > /etc/systemd/system/uniproxy-watcher.timer <<'UNIT'
[Unit]
Description=UniProxy Health Check Timer

[Timer]
OnBootSec=60
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
UNIT

    # Cert renewal cron
    echo "0 3 * * * root certbot renew --quiet --post-hook 'docker compose -f $UNIPROXY_DIR/docker-compose.yml restart nginx'" \
        > /etc/cron.d/uniproxy-certrenew

    # Backup cron
    echo "0 */6 * * * root $UNIPROXY_DIR/scripts/backup.sh" \
        > /etc/cron.d/uniproxy-backup

    systemctl daemon-reload
    systemctl enable uniproxy-watcher.timer --now 2>/dev/null || true
    log "Systemd services configured"
}

###############################################################################
# VLESS REALITY KEY GEN (precomputed for fast setup)
###############################################################################
gen_reality_keys() {
    if command -v xray &>/dev/null; then
        REALITY_KEYS=$(xray x25519 2>/dev/null || echo "")
        if [[ -n "$REALITY_KEYS" ]]; then
            REALITY_PRIVATE=$(echo "$REALITY_KEYS" | grep "Private key:" | awk '{print $3}')
            REALITY_PUBLIC=$(echo "$REALITY_KEYS" | grep "Public key:" | awk '{print $3}')
            echo "REALITY_PRIVATE_KEY=$REALITY_PRIVATE" >> /etc/uniproxy/env
            echo "REALITY_PUBLIC_KEY=$REALITY_PUBLIC"  >> /etc/uniproxy/env
            log "VLESS Reality keys generated"
        fi
    fi
}

###############################################################################
# COMPLETION SUMMARY
###############################################################################
print_summary() {
    local IP
    IP=$(curl -4s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    local PANEL_URL="http://$IP:$PANEL_PORT"
    [[ "${DOMAIN:-localhost}" != "localhost" ]] && PANEL_URL="https://${DOMAIN}:$PANEL_PORT"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        UniProxy Successfully Installed! 🚀           ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC} Panel URL:  ${BLUE}$PANEL_URL${NC}"
    echo -e "${GREEN}║${NC} Username:   ${YELLOW}admin${NC}"
    echo -e "${GREEN}║${NC} Password:   ${YELLOW}${MASTER_PASS:-[see /etc/uniproxy/env]}${NC}"
    echo -e "${GREEN}║${NC} Domain:     ${DOMAIN:-self-signed}"
    echo -e "${GREEN}║${NC} Log:        /var/log/uniproxy-install.log"
    echo -e "${GREEN}║${NC} Config:     /etc/uniproxy/env"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}[!] Save your password — it won't be shown again${NC}"
}

###############################################################################
# MAIN
###############################################################################
main() {
    [[ $EUID -ne 0 ]] && err "Run as root: sudo bash install.sh"
    mkdir -p /etc/uniproxy
    touch "$LOG_FILE"
    banner
    detect_os
    install_deps
    install_xray
    install_singbox
    setup_certs
    setup_firewall
    gen_reality_keys
    deploy_panel
    setup_services
    print_summary
}

main "$@"
