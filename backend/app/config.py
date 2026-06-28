"""FVpn Configuration"""

import json
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:////data/fvpn.db"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_PASSWORD: str = "fvpn"

    # Security
    JWT_SECRET: str = "changeme-generate-with-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # Admin
    MASTER_PASSWORD: str = "admin"

    # Domain / TLS
    DOMAIN: str = "localhost"
    CERT_PATH: str = "/etc/fvpn/ssl/cert.pem"
    KEY_PATH: str = "/etc/fvpn/ssl/key.pem"

    # Panel
    PANEL_PORT: int = 2095

    # CORS — stored as str to avoid pydantic-settings JSON-parse failure on "*"
    # Use the `.cors_list` property everywhere in application code.
    # Accepted formats in .env:
    #   CORS_ORIGINS=*
    #   CORS_ORIGINS=https://a.com,https://b.com
    #   CORS_ORIGINS=["https://a.com","https://b.com"]
    CORS_ORIGINS: str = "*"

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
    # Parsed properties — use these instead of the raw str fields
    # -------------------------------------------------------------------------

    @property
    def cors_list(self) -> list[str]:
        """Parse CORS_ORIGINS string → list for CORSMiddleware."""
        v = (self.CORS_ORIGINS or "").strip()
        if not v or v == "*":
            return ["*"]
        if v.startswith("["):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(i) for i in parsed]
            except json.JSONDecodeError:
                pass
        return [i.strip() for i in v.split(",") if i.strip()]

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
