"""FVpn Configuration"""

import json
import re
from functools import lru_cache
from ipaddress import ip_address
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:////data/fvpn.db"

    # Security
    JWT_SECRET: str = Field(default="", repr=False)
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Admin
    MASTER_PASSWORD: str = "admin"

    # Domain / TLS
    DOMAIN: str = "localhost"
    CERT_PATH: str = "/etc/fvpn/ssl/cert.pem"
    KEY_PATH: str = "/etc/fvpn/ssl/key.pem"

    # Panel
    PANEL_PORT: int = Field(default=2095, ge=1, le=65535)
    TRUSTED_PROXY_IPS: str = "172.20.0.10"

    # CORS — stored as str to avoid pydantic-settings JSON-parse failure on "*"
    # Use the `.cors_list` property everywhere in application code.
    # Accepted formats in .env:
    #   CORS_ORIGINS=  (panel origin; legacy '*' also resolves to panel)
    #   CORS_ORIGINS=https://a.com,https://b.com
    #   CORS_ORIGINS=["https://a.com","https://b.com"]
    CORS_ORIGINS: str = ""

    # Xray / Sing-box
    XRAY_BIN: str = "/usr/local/bin/xray"
    SINGBOX_BIN: str = "/usr/local/bin/sing-box"
    XRAY_CONFIG: str = "/etc/xray/config.json"
    SINGBOX_CONFIG: str = "/etc/sing-box/config.json"

    # VLESS Reality
    REALITY_PRIVATE_KEY: str = ""
    REALITY_PUBLIC_KEY: str = ""

    # Telegram Bot — stored as str, use `.admin_ids` property in code.
    # Accepted formats:
    #   TELEGRAM_ADMIN_IDS=
    #   TELEGRAM_ADMIN_IDS=123456789
    #   TELEGRAM_ADMIN_IDS=123456789,987654321
    #   TELEGRAM_ADMIN_IDS=[123456789,987654321]
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: str = ""

    # Self-healing
    HEALTH_CHECK_URL: str = "http://www.gstatic.com/generate_204"
    HEALTH_CHECK_INTERVAL: int = 300

    # Backup
    BACKUP_DIR: str = "/data/backups"
    BACKUP_S3_BUCKET: str = ""

    # -------------------------------------------------------------------------

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str) -> str:
        if len(value.strip().encode("utf-8")) < 32 or value.strip().lower() in {
            "changeme-generate-with-openssl-rand-hex-32",
            "change-me-generate-with-openssl-rand-hex-32",
            "your-secret-key-change-in-production",
        }:
            raise ValueError("JWT_SECRET must be a private secret of at least 32 bytes")
        return value

    @model_validator(mode="after")
    def validate_network_settings(self) -> "Settings":
        # Validate eagerly: invalid security settings must prevent startup.
        self.cors_list
        self.trusted_proxy_ips
        return self

    @staticmethod
    def _origin(value: str) -> str:
        if not value or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
            raise ValueError("CORS origins must be HTTP(S) origins without credentials or paths")
        try:
            parsed = urlsplit(value)
            port = parsed.port
            host = parsed.hostname
            if (
                parsed.scheme not in {"https", "http"}
                or not host
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or "?" in value
                or "#" in value
                or (port is not None and not 1 <= port <= 65535)
            ):
                raise ValueError
            try:
                ip_address(host)
            except ValueError:
                labels = host.encode("idna").decode("ascii").split(".")
                if len(host) > 253 or any(
                    not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                    for label in labels
                ):
                    raise ValueError
        except (ValueError, UnicodeError):
            raise ValueError("CORS origins must be valid HTTP(S) origins") from None
        return value.rstrip("/")

    @property
    def trusted_proxy_ips(self) -> frozenset[str]:
        try:
            return frozenset(str(ip_address(part.strip())) for part in self.TRUSTED_PROXY_IPS.split(",") if part.strip())
        except ValueError:
            raise ValueError("TRUSTED_PROXY_IPS must contain comma-separated IP addresses") from None
    # Parsed properties — use these instead of the raw str fields
    # -------------------------------------------------------------------------

    @property
    def cors_list(self) -> list[str]:
        """Use the panel origin by default; reject ambiguous origin rules."""
        v = (self.CORS_ORIGINS or "").strip()
        if not v or v == "*":
            return [self._origin(f"https://{self.DOMAIN}:{self.PANEL_PORT}")]
        if v.startswith("["):
            try:
                parsed = json.loads(v)
                if not isinstance(parsed, list) or not parsed or not all(isinstance(i, str) for i in parsed):
                    raise ValueError("CORS_ORIGINS must contain an array of origins")
                return [self._origin(i) for i in parsed]
            except json.JSONDecodeError:
                raise ValueError("CORS_ORIGINS must contain valid JSON") from None
        return [self._origin(i.strip()) for i in v.split(",")]

    @property
    def admin_ids(self) -> list[int]:
        """Parse TELEGRAM_ADMIN_IDS string → list[int]."""
        v = (self.TELEGRAM_ADMIN_IDS or "").strip()
        if not v:
            return []
        if v.startswith("["):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [int(i) for i in parsed]
            except (json.JSONDecodeError, ValueError):
                pass
        result = []
        for part in v.split(","):
            part = part.strip()
            if part.lstrip("-").isdigit():
                result.append(int(part))
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
