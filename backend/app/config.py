"""UniProxy Configuration"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    VERSION: str = "1.0.0"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:////data/uniproxy.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = "uniproxy"

    # Security
    JWT_SECRET: str = "changeme-generate-with-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24h

    # Admin
    MASTER_PASSWORD: str = "admin"

    # Domain / TLS
    DOMAIN: str = "localhost"
    CERT_PATH: str = "/etc/uniproxy/ssl/cert.pem"
    KEY_PATH: str = "/etc/uniproxy/ssl/key.pem"

    # Panel
    PANEL_PORT: int = 2095

    # CORS
    CORS_ORIGINS: list[str] = ["*"]

    # Xray/Singbox
    XRAY_BIN: str = "/usr/local/bin/xray"
    SINGBOX_BIN: str = "/usr/local/bin/sing-box"
    XRAY_CONFIG: str = "/etc/xray/config.json"
    SINGBOX_CONFIG: str = "/etc/sing-box/config.json"

    # Reality keys (generated at install time)
    REALITY_PRIVATE_KEY: str = ""
    REALITY_PUBLIC_KEY: str = ""

    # Telegram Bot
    TELEGRAM_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: list[int] = []

    # Self-healing
    HEALTH_CHECK_URL: str = "http://www.gstatic.com/generate_204"
    HEALTH_CHECK_INTERVAL: int = 300  # seconds

    # Backup
    BACKUP_DIR: str = "/data/backups"
    BACKUP_S3_BUCKET: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
