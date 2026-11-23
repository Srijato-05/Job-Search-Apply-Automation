"""Application configuration, tunable pipeline thresholds, paths, and loopback token management."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from environment or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server & Storage Paths
    local_host: str = "127.0.0.1"
    local_port: int = 8000
    data_dir: Path = _REPO_ROOT / "data"
    fastembed_cache_dir: Path = _REPO_ROOT / ".fastembed_cache"
    embedding_model_name: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    log_level: str = "INFO"
    allowed_cors_origins: str = "http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"

    # Collector & Cooldown Settings
    jobspy_min_delay_sec: int = 4
    jobspy_max_delay_sec: int = 8
    jobspy_default_sites: str = "naukri,linkedin,indeed,glassdoor,google"
    circuit_breaker_cooldown_hours: int = 8
    collector_interval_hours: int = 4
    collector_max_concurrency: int = 5
    ats_http_timeout_sec: float = 15.0
    enable_background_scheduler: bool = False
    max_company_apps_30d: int = 3

    # 5-Gate Pipeline Thresholds (Tunable without code edits)
    semantic_threshold: float = 0.72
    dedup_similarity_threshold: float = 0.88
    dedup_stack_overlap_threshold: float = 0.70
    gate1_exp_buffer_years: float = 2.0
    exp_fit_lower_grace_years: float = 0.5
    exp_fit_upper_grace_years: float = 2.0
    exp_fit_stretch_years: float = 2.0
    tier_s_coverage_pct: float = 80.0
    tier_a_coverage_pct: float = 60.0
    tier_b_coverage_pct: float = 40.0
    tier_a_primary_ratio: float = 0.75
    tier_b_primary_ratio: float = 0.50
    tier_c_min_primary_ratio: float = 0.40
    tier_a_max_missing_secondary: int = 2
    tier_b_max_missing_primary: int = 1
    freshness_hours: int = 6
    jd_embed_max_chars: int = 2000

    @property
    def cors_origins_list(self) -> list[str]:
        base = f"http://{self.local_host}:{self.local_port}"
        origins = [base]
        for raw in self.allowed_cors_origins.split(","):
            cleaned = raw.strip()
            if cleaned and cleaned not in origins:
                origins.append(cleaned)
        return origins

    @property
    def jobspy_sites_list(self) -> list[str]:
        return [s.strip().lower() for s in self.jobspy_default_sites.split(",") if s.strip()]

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"

    @property
    def resumes_dir(self) -> Path:
        return self.data_dir / "resumes"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def token_path(self) -> Path:
        return self.data_dir / ".local_token"


def ensure_data_dirs(settings: Settings) -> None:
    """Create local runtime storage directories if missing."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.resumes_dir.mkdir(parents=True, exist_ok=True)
    settings.backups_dir.mkdir(parents=True, exist_ok=True)
    settings.fastembed_cache_dir.mkdir(parents=True, exist_ok=True)


def get_or_create_local_token(data_dir: Path) -> str:
    """Return the persisted local API auth token, generating one on first run."""
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file = data_dir / ".local_token"
    if token_file.exists():
        existing = token_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    token_file.write_text(token, encoding="utf-8")
    return token
