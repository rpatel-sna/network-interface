"""Runtime configuration loaded from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # No-op if .env absent; env vars already set take precedence


@dataclass
class Settings:
    # Local results database (required)
    db_host: str = field(default_factory=lambda: os.environ["DB_HOST"])
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "3306")))
    db_user: str = field(default_factory=lambda: os.environ["DB_USER"])
    db_password: str = field(default_factory=lambda: os.environ["DB_PASSWORD"])
    db_name: str = field(default_factory=lambda: os.environ["DB_NAME"])

    # External device source database (required)
    ext_db_host: str = field(default_factory=lambda: os.environ["EXT_DB_HOST"])
    ext_db_port: int = field(default_factory=lambda: int(os.getenv("EXT_DB_PORT", "3306")))
    ext_db_user: str = field(default_factory=lambda: os.environ["EXT_DB_USER"])
    ext_db_password: str = field(default_factory=lambda: os.environ["EXT_DB_PASSWORD"])
    ext_db_name: str = field(default_factory=lambda: os.environ["EXT_DB_NAME"])
    ext_db_query: str = field(default_factory=lambda: os.environ["EXT_DB_QUERY"])

    # Tuning (optional with defaults)
    max_threads: int = field(
        default_factory=lambda: int(os.getenv("MAX_THREADS", "10"))
    )
    ssh_timeout: int = field(
        default_factory=lambda: int(os.getenv("SSH_TIMEOUT", "30"))
    )

    # Logging (optional with defaults)
    log_file: str = field(default_factory=lambda: os.getenv("LOG_FILE", "inventory.log"))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


def _load_settings() -> Settings:
    missing = []
    for var in (
        "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME",
        "EXT_DB_HOST", "EXT_DB_USER", "EXT_DB_PASSWORD",
        "EXT_DB_NAME", "EXT_DB_QUERY",
    ):
        if not os.getenv(var):
            missing.append(var)
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy .env.example to .env and populate the values."
        )
    return Settings()


settings = _load_settings()
