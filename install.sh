#!/usr/bin/env bash
# FVpn Installer v1.1
# One-command deploy: bash <(curl -s https://raw.githubusercontent.com/franklin-lol/FVpn/main/install.sh)
set -euo pipefail
umask 077

###############################################################################
# GLOBALS
###############################################################################
PANEL_PORT=2095
XRAY_VERSION="1.8.24"
SINGBOX_VERSION="1.9.0"

LOG_FILE="/var/log/fvpn-install.log"

# Auto-detect project directory:
# If install.sh lives inside the cloned repo (docker-compose.yml is a sibling),
# use that directory. Otherwise clone into /opt/fvpn.
SCRIPT_DIR="$(if cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null; then pwd; else pwd; fi)"
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
            [[ "${OS_VERSION%%.*}" -ge 20 ]] || err "Ubuntu 20.04+ required (got $OS_VERSION)"
            PKG_MGR="apt-get"
            ;;
        debian)
            [[ "${OS_VERSION%%.*}" -ge 11 ]] || err "Debian 11+ required (got $OS_VERSION)"
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
        cron iproute2 2>>"$LOG_FILE"

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
compose() {
    docker compose --project-directory "$UNIPROXY_DIR" -f "$UNIPROXY_DIR/docker-compose.yml" "$@"
}

ensure_checkout() {
    [[ -f "$UNIPROXY_DIR/docker-compose.yml" ]] && return
    if [[ -d "$UNIPROXY_DIR" ]] && [[ -n "$(find "$UNIPROXY_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
        err "$UNIPROXY_DIR is not an FVpn checkout and is not empty. Move its files aside or run install.sh from an existing checkout."
    fi
    git clone https://github.com/franklin-lol/FVpn "$UNIPROXY_DIR" \
        || err "git clone failed — check network and repo URL"
}

# Parse dotenv values without executing shell content. Never log the result.
env_value() {
    python3 - "$UNIPROXY_DIR/.env" "$1" <<'PY'
import pathlib
import re
import shlex
import sys

path = pathlib.Path(sys.argv[1])
value = ""
if path.is_file():
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(sys.argv[2]) + r"\s*=\s*(.*)$")
    for line in path.read_text().splitlines():
        match = pattern.match(line)
        if match:
            raw = match.group(1).strip()
            try:
                if raw.startswith(("'", '"')):
                    parts = shlex.split(raw, comments=True)
                    parsed = parts[0] if parts else ""
                else:
                    parsed = re.split(r"\s+#", raw, maxsplit=1)[0].strip()
                    if parsed.startswith("#"):
                        parsed = ""
                if parsed:
                    value = parsed
            except ValueError:
                raise SystemExit("Invalid quoting in environment configuration")
print(value)
PY
}

validate_domain() {
    [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] \
        && [[ "$1" != *..* ]] && [[ ${#1} -le 253 ]]
}

set_cert_paths() {
    CERT_PATH=$(env_value CERT_PATH)
    KEY_PATH=$(env_value KEY_PATH)
    CERT_PATH=${CERT_PATH:-/etc/fvpn/ssl/cert.pem}
    KEY_PATH=${KEY_PATH:-/etc/fvpn/ssl/key.pem}
    # Existing custom names remain supported inside the shared mount.
    local path parent
    for path in "$CERT_PATH" "$KEY_PATH"; do
        [[ "$path" == /etc/fvpn/ssl/* && "$path" != *'/../'* && "$path" != *'/./'* && "$path" != *$'\n'* ]] \
            || err "CERT_PATH and KEY_PATH must be files inside /etc/fvpn/ssl, the certificate directory mounted by Compose."
        parent=$(realpath -m "$(dirname "$path")")
        [[ "$parent" == /etc/fvpn/ssl || "$parent" == /etc/fvpn/ssl/* ]] \
            || err "Certificate parent directories must stay inside /etc/fvpn/ssl."
    done
    [[ "$CERT_PATH" != "$KEY_PATH" ]] || err "CERT_PATH and KEY_PATH must differ."
    [[ "$CERT_PATH" != /etc/fvpn/ssl/key.pem && "$KEY_PATH" != /etc/fvpn/ssl/cert.pem ]] \
        || err "The default cert.pem and key.pem names cannot be swapped."
}

valid_cert_pair() {
    [[ -s "$1" && -s "$2" ]] || return 1
    openssl x509 -in "$1" -checkend 0 -noout >/dev/null 2>&1 || return 1
    local cert_public key_public
    cert_public=$(openssl x509 -in "$1" -pubkey -noout 2>/dev/null) || return 1
    key_public=$(openssl pkey -in "$2" -pubout 2>/dev/null) || return 1
    [[ "$cert_public" == "$key_public" ]]
}

publish_certs() {
    local source_cert="$1" source_key="$2" staged_cert staged_key
    valid_cert_pair "$source_cert" "$source_key" || err "Certificate and private key are invalid, expired or do not match."
    mkdir -p "$(dirname "$CERT_PATH")" "$(dirname "$KEY_PATH")"
    staged_cert=$(mktemp "${CERT_PATH}.XXXXXX")
    staged_key=$(mktemp "${KEY_PATH}.XXXXXX")
    install -m 644 "$source_cert" "$staged_cert"
    install -m 600 "$source_key" "$staged_key"
    # Rename replaces legacy Let's Encrypt symlinks with regular files. The
    # complete PEM is visible through existing directory bind mounts at once.
    mv -fT "$staged_cert" "$CERT_PATH"
    mv -fT "$staged_key" "$KEY_PATH"
    # nginx uses fixed in-container names, even with custom backend paths.
    if [[ "$CERT_PATH" != /etc/fvpn/ssl/cert.pem ]]; then
        staged_cert=$(mktemp /etc/fvpn/ssl/cert.pem.XXXXXX)
        install -m 644 "$CERT_PATH" "$staged_cert"
        mv -fT "$staged_cert" /etc/fvpn/ssl/cert.pem
    fi
    if [[ "$KEY_PATH" != /etc/fvpn/ssl/key.pem ]]; then
        staged_key=$(mktemp /etc/fvpn/ssl/key.pem.XXXXXX)
        install -m 600 "$KEY_PATH" "$staged_key"
        mv -fT "$staged_key" /etc/fvpn/ssl/key.pem
    fi
}

http_port_free() {
    local listeners containers
    listeners=$(ss -H -ltn 'sport = :80') || err "Cannot inspect TCP port 80 with ss."
    containers=$(docker ps -q --filter publish=80) || err "Cannot inspect Docker port bindings."
    [[ -z "$listeners" && -z "$containers" ]]
}

# Stop only this checkout's nginx. Always bring it back, including on errors.
restore_nginx() {
    local status=$?
    trap - EXIT
    if [[ "${NGINX_STOPPED:-0}" == 1 ]]; then
        if ! compose start nginx >>"$LOG_FILE" 2>&1; then
            warn "FVpn nginx could not restart. Run docker compose up -d nginx in $UNIPROXY_DIR."
            status=1
        fi
    fi
    exit "$status"
}

release_own_http_port() {
    local running
    running=$(compose ps --status running --services nginx)
    if [[ "$running" == nginx ]]; then
        NGINX_STOPPED=1
        trap restore_nginx EXIT
        compose stop nginx >>"$LOG_FILE" 2>&1
    fi
    http_port_free || err "Port 80 is occupied by another service. Free it explicitly or configure certificates manually; FVpn will not stop other services."
}

reload_tls_services() {
    local service running
    running=$(compose ps --status running --services)
    for service in nginx xray singbox; do
        if grep -qx "$service" <<<"$running"; then
            compose restart "$service" >>"$LOG_FILE" 2>&1
        fi
    done
}

renew_certs() {
    DOMAIN="$1"
    validate_domain "$DOMAIN" || err "Invalid certificate domain."
    set_cert_paths
    # Serialize cron/manual renewal so one exit cannot restart nginx while
    # another Certbot invocation still needs the HTTP challenge port.
    exec 9>/etc/fvpn/cert-renew.lock
    flock -n 9 || return 0
    release_own_http_port
    certbot renew --cert-name "$DOMAIN" --standalone --non-interactive --no-directory-hooks >>"$LOG_FILE" 2>&1
    publish_certs "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "/etc/letsencrypt/live/$DOMAIN/privkey.pem"
    reload_tls_services
    log "Certificate files published for $DOMAIN"
}

setup_certs() {
    mkdir -p /etc/fvpn/ssl
    set_cert_paths
    DOMAIN=$(env_value DOMAIN)
    if [[ "$DOMAIN" == localhost ]]; then
        warn "Existing DOMAIN=localhost is preserved. Set DOMAIN in .env to the public hostname/IP for generated external links; enter that public address below for this installation."
    fi
    if [[ -z "$DOMAIN" || "$DOMAIN" == localhost ]]; then
        read -rp "$(echo -e "${BLUE}[?]${NC} Domain name or public IP (blank = detect public IPv4, self-signed): ")" DOMAIN
    fi
    if [[ -z "$DOMAIN" ]]; then
        DOMAIN=$(curl -4fsS --max-time 5 https://api.ipify.org 2>/dev/null || true)
        [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] \
            || err "Public IPv4 detection failed. Run again and enter the public IP or domain."
    fi
    validate_domain "$DOMAIN" || err "Enter a domain or IPv4 address without scheme, port or path."
    [[ "$DOMAIN" != localhost && "$DOMAIN" != 127.* && "$DOMAIN" != 0.0.0.0 ]] \
        || err "Enter the server's public domain or IP, not a loopback address."
    if valid_cert_pair "$CERT_PATH" "$KEY_PATH"; then
        publish_certs "$CERT_PATH" "$KEY_PATH"
        if [[ -f "/etc/letsencrypt/renewal/$DOMAIN.conf" ]]; then
            CERT_MODE="letsencrypt"
        else
            CERT_MODE="existing"
        fi
        log "Preserving existing certificate for $DOMAIN"
        return
    fi
    local temporary
    temporary=$(mktemp -d /etc/fvpn/ssl/.certificate.XXXXXX)
    CERT_MODE="self-signed"
    if [[ ! "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        info "Requesting Let's Encrypt certificate for $DOMAIN..."
        release_own_http_port
        if certbot certonly --standalone -d "$DOMAIN" \
            --cert-name "$DOMAIN" --non-interactive --agree-tos \
            --register-unsafely-without-email \
            --preferred-challenges http --no-directory-hooks 2>>"$LOG_FILE"; then
            publish_certs "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "/etc/letsencrypt/live/$DOMAIN/privkey.pem"
            CERT_MODE="letsencrypt"
        else
            warn "Certbot failed — using a self-signed certificate. Check DNS and inbound port 80 before requesting a trusted certificate."
        fi
    fi
    if [[ "$CERT_MODE" == self-signed ]]; then
        warn "Generating self-signed certificate; browsers will require a certificate exception"
        openssl req -x509 -newkey rsa:4096 \
            -keyout "$temporary/key.pem" \
            -out "$temporary/cert.pem" \
            -days 3650 -nodes \
            -subj "/CN=$DOMAIN" 2>>"$LOG_FILE"
        publish_certs "$temporary/cert.pem" "$temporary/key.pem"
    fi
    rm -rf "$temporary"
    reload_tls_services
    if [[ "${NGINX_STOPPED:-0}" == 1 ]]; then
        compose start nginx >>"$LOG_FILE" 2>&1
        NGINX_STOPPED=0
        trap - EXIT
    fi
    log "Certificate: $CERT_MODE for ${DOMAIN}"
}

###############################################################################
# FIREWALL
###############################################################################
setup_firewall() {
    info "Configuring UFW firewall..."
    local ssh_ports="" local_port port ssh_config
    if [[ -n "${SSH_CONNECTION:-}" ]]; then
        read -r _ _ _ local_port <<<"$SSH_CONNECTION"
        ssh_ports="$local_port"
    fi
    if command -v sshd >/dev/null 2>&1; then
        ssh_config=$(sshd -T 2>/dev/null) || ssh_config=""
        ssh_ports+=" $(awk '$1 == "port" {print $2}' <<<"$ssh_config")"
    elif [[ -x /usr/sbin/sshd ]]; then
        ssh_config=$(/usr/sbin/sshd -T 2>/dev/null) || ssh_config=""
        ssh_ports+=" $(awk '$1 == "port" {print $2}' <<<"$ssh_config")"
    fi
    [[ -n "${ssh_ports//[[:space:]]/}" ]] \
        || err "Cannot determine SSH ports from SSH_CONNECTION or sshd -T. Firewall unchanged; configure SSH access explicitly before continuing."
    for port in $ssh_ports; do
        [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1 && "$port" -le 65535 ]] \
            || err "Cannot validate the SSH port. Firewall unchanged."
    done
    # Preserve all existing rules and policies. Add SSH before enabling UFW.
    for port in $ssh_ports; do
        ufw allow "$port/tcp" >>"$LOG_FILE" 2>&1
    done
    for PORT in 80 443 2095 2096 8080 8443; do
        ufw allow "$PORT/tcp" >>"$LOG_FILE" 2>&1
    done
    {
        ufw allow 443/udp   # QUIC / Hysteria2
        ufw allow 8443/udp
        ufw --force enable
    } >>"$LOG_FILE" 2>&1
    log "Firewall configured"
}

###############################################################################
# VLESS REALITY KEY GENERATION
###############################################################################
gen_reality_keys() {
    REALITY_PRIVATE=$(env_value REALITY_PRIVATE_KEY)
    REALITY_PUBLIC=$(env_value REALITY_PUBLIC_KEY)
    if [[ -n "$REALITY_PRIVATE" && -n "$REALITY_PUBLIC" ]]; then
        log "Preserving existing VLESS Reality key pair"
        return
    fi
    if [[ -n "$REALITY_PRIVATE" || -n "$REALITY_PUBLIC" ]]; then
        err "The existing Reality key pair is incomplete. Restore its matching REALITY_PRIVATE_KEY and REALITY_PUBLIC_KEY in .env before reinstalling."
    fi
    if command -v xray &>/dev/null; then
        local REALITY_KEYS
        REALITY_KEYS=$(xray x25519 2>/dev/null || echo "")
        if [[ -n "$REALITY_KEYS" ]]; then
            REALITY_PRIVATE=$(awk '/^Private key:/ {print $3}' <<<"$REALITY_KEYS")
            REALITY_PUBLIC=$(awk '/^Public key:/ {print $3}' <<<"$REALITY_KEYS")
            log "VLESS Reality keys generated"
        fi
    fi
    REALITY_PRIVATE="${REALITY_PRIVATE:-}"
    REALITY_PUBLIC="${REALITY_PUBLIC:-}"
    [[ -n "$REALITY_PRIVATE" && -n "$REALITY_PUBLIC" ]] || err "Could not generate a complete Reality key pair with the installed Xray binary."
}

###############################################################################
# ENV MANAGEMENT
# Rule: preserve nonempty values; fill missing or empty values.
#       if .env doesn't exist → generate everything fresh.
###############################################################################

# Preserve comments, spacing and nonempty values. Empty duplicate assignments
# are removed so they cannot override a retained value in dotenv consumers.
_ensure_key() {
    local key="$1" value="$2" file="$3"
    FVPN_ENV_VALUE="$value" python3 - "$key" "$file" <<'PY'
import os
import pathlib
import re
import tempfile
import sys

key, filename = sys.argv[1:]
path = pathlib.Path(filename)
lines = path.read_text().splitlines(keepends=True)
pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(key) + r"\s*=\s*(.*)$")
empty = re.compile(r'''^(?:''|""|)\s*(?:#.*)?$''')
matches = [(index, pattern.match(line.rstrip("\r\n"))) for index, line in enumerate(lines)]
matches = [(index, match) for index, match in matches if match]
filled = any(not empty.fullmatch(match.group(1).strip()) for _, match in matches)
empty_indexes = {index for index, match in matches if empty.fullmatch(match.group(1).strip())}
if filled:
    result = "".join(line for index, line in enumerate(lines) if index not in empty_indexes)
elif matches:
    first = matches[0][0]
    result = "".join(
        f"{key}={os.environ['FVPN_ENV_VALUE']}\n" if index == first else line
        for index, line in enumerate(lines) if index == first or index not in empty_indexes
    )
else:
    result = "".join(lines)
    if result and not result.endswith("\n"):
        result += "\n"
    result += f"{key}={os.environ['FVPN_ENV_VALUE']}\n"
descriptor, temporary = tempfile.mkstemp(prefix=".fvpn-env-", dir=path.parent)
try:
    with os.fdopen(descriptor, "w") as handle:
        handle.write(result)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
}

setup_env() {
    local env_file="$UNIPROXY_DIR/.env"

    if [[ -f "$env_file" ]]; then
        log ".env exists — preserving nonempty values, filling missing or empty keys"
    else
        log "Generating fresh .env..."
        touch "$env_file"
    fi
    chmod 600 "$env_file"
    MASTER_PASS=$(env_value MASTER_PASSWORD)

    # Auto-generate JWT secret if missing
    local jwt_secret
    jwt_secret=$(env_value JWT_SECRET)
    [[ -z "$jwt_secret" ]] && jwt_secret=$(openssl rand -hex 32)

    # Use defaults if variables are empty (first run or env existed but missing keys)
    [[ -z "${MASTER_PASS:-}" ]] && MASTER_PASS=$(openssl rand -hex 20)

    # Keep legacy Redis settings if present, but new installs do not need Redis.
    _ensure_key "PANEL_PORT"           "$PANEL_PORT"                                    "$env_file"
    _ensure_key "DOMAIN"               "$DOMAIN"                                        "$env_file"
    _ensure_key "CERT_PATH"            "$CERT_PATH"                                     "$env_file"
    _ensure_key "KEY_PATH"             "$KEY_PATH"                                      "$env_file"
    _ensure_key "MASTER_PASSWORD"      "$MASTER_PASS"                                   "$env_file"
    _ensure_key "JWT_SECRET"           "$jwt_secret"                                    "$env_file"
    _ensure_key "JWT_EXPIRE_MINUTES"   "1440"                                           "$env_file"
    _ensure_key "DATABASE_URL"         "sqlite+aiosqlite:////data/fvpn.db"              "$env_file"
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
    install -m 600 "$env_file" /etc/fvpn/env

    log ".env ready at $env_file"
}

###############################################################################
# DEPLOY PANEL
###############################################################################
deploy_panel() {
    info "Deploying FVpn panel..."

    if [[ -z "$(compose ps --status running --services nginx)" ]]; then
        http_port_free || err "Port 80 is occupied. Free it explicitly before starting FVpn nginx."
    fi

    cd "$UNIPROXY_DIR"

    # Build images and start (DOCKER_BUILDKIT=1 enables layer caching)
    DOCKER_BUILDKIT=1 compose up -d --build 2>>"$LOG_FILE" \
        || err "Docker compose failed — check $LOG_FILE"

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
ExecStart=/bin/bash $UNIPROXY_DIR/scripts/self_healing.sh
WorkingDirectory=$UNIPROXY_DIR
UMask=0077

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

    # Only this installation's certificate is renewed. The installer handles
    # regular-file publication and recovery of nginx even when Certbot fails.
    if [[ "$CERT_MODE" == letsencrypt ]]; then
        printf "0 3 * * * root /bin/bash '%s/install.sh' --renew-certs '%s'\n" "$UNIPROXY_DIR" "$DOMAIN" \
            > /etc/cron.d/fvpn-certrenew
    else
        printf '# FVpn certificate renewal is not configured for this certificate.\n' > /etc/cron.d/fvpn-certrenew
    fi

    # Backup every 6h
    echo "0 */6 * * * root /bin/bash $UNIPROXY_DIR/scripts/backup.sh" \
        > /etc/cron.d/fvpn-backup
    chmod 644 /etc/cron.d/fvpn-certrenew /etc/cron.d/fvpn-backup
    chmod 644 /etc/systemd/system/fvpn-watcher.service /etc/systemd/system/fvpn-watcher.timer

    systemctl daemon-reload
    systemctl enable --now fvpn-watcher.timer 2>/dev/null || true

    log "Systemd timer and cron jobs configured"
}

###############################################################################
# SUMMARY
###############################################################################
print_summary() {
    local PANEL_URL="https://${DOMAIN}:2095"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          FVpn Installation Complete                  ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  Panel   : ${BLUE}${PANEL_URL}${NC}"
    echo -e "${GREEN}║${NC}  Username: ${YELLOW}admin${NC}"
    echo -e "${GREEN}║${NC}  Password: stored in $UNIPROXY_DIR/.env (MASTER_PASSWORD)"
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
    chmod 600 "$LOG_FILE"

    if [[ "${1:-}" == --renew-certs ]]; then
        [[ $# -eq 2 ]] || err "Usage: install.sh --renew-certs DOMAIN"
        renew_certs "$2"
        return
    fi

    banner
    detect_os
    install_deps
    ensure_checkout
    # Checkout precedes .env creation; cloning into a nonempty directory fails.
    [[ "$UNIPROXY_DIR" =~ ^/[A-Za-z0-9_./-]+$ ]] \
        || err "Use a project directory without spaces or shell metacharacters so systemd and cron paths remain valid."
    touch "$UNIPROXY_DIR/.env"
    chmod 600 "$UNIPROXY_DIR/.env"
    mkdir -p /etc/fvpn
    exec 9>/etc/fvpn/cert-renew.lock
    flock -n 9 || err "Another FVpn installation, certificate renewal or watcher cycle is running. Try again after it completes."
    install_xray
    install_singbox
    setup_firewall
    setup_certs
    gen_reality_keys
    setup_env
    deploy_panel
    setup_services
    print_summary
}

main "$@"
