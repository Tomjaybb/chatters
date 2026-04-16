"""Central configuration loaded from .env and CLI overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    # Paths
    output_dir: Path = Path("./output")
    db_path: Path = Path("./output/pipeline.db")
    log_path: Path = Path("./output/logs/pipeline.log")

    # Instagram auth
    ig_username: str = ""
    ig_password: str = ""
    ig_sessions: list[tuple[str, str]] = field(default_factory=list)

    # Apify
    apify_api_key: str = ""

    # Proxies
    proxy_urls: list[str] = field(default_factory=list)

    # Rate limiting
    request_delay_min: float = 2.0
    request_delay_max: float = 7.0
    ig_max_rps: float = 0.4

    # Data retention
    retention_days: int = 90

    # Runtime flags
    dry_run: bool = False
    single_agency: str | None = None
    ig_provider: str = "instaloader"  # instaloader | apify | instagrapi

    def __post_init__(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)


def _parse_sessions(raw: str) -> list[tuple[str, str]]:
    """Parse ``user1:pass1,user2:pass2`` into a list of tuples."""
    sessions: list[tuple[str, str]] = []
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            user, passwd = pair.split(":", 1)
            sessions.append((user.strip(), passwd.strip()))
    return sessions


def load_config(env_file: str | Path | None = None, **overrides: object) -> Config:
    """Build a ``Config`` from ``.env`` file + optional keyword overrides."""
    load_dotenv(env_file or ".env")

    sessions_raw = os.getenv("IG_SESSIONS", "")

    cfg = Config(
        output_dir=Path(os.getenv("OUTPUT_DIR", "./output")),
        db_path=Path(os.getenv("DB_PATH", "./output/pipeline.db")),
        log_path=Path(os.getenv("LOG_PATH", "./output/logs/pipeline.log")),
        ig_username=os.getenv("IG_USERNAME", ""),
        ig_password=os.getenv("IG_PASSWORD", ""),
        ig_sessions=_parse_sessions(sessions_raw),
        apify_api_key=os.getenv("APIFY_API_KEY", ""),
        proxy_urls=[
            u.strip()
            for u in os.getenv("PROXY_URLS", "").split(",")
            if u.strip()
        ],
        request_delay_min=float(os.getenv("REQUEST_DELAY_MIN", "2.0")),
        request_delay_max=float(os.getenv("REQUEST_DELAY_MAX", "7.0")),
        ig_max_rps=float(os.getenv("IG_MAX_RPS", "0.4")),
        retention_days=int(os.getenv("RETENTION_DAYS", "90")),
    )

    for key, value in overrides.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    return cfg
