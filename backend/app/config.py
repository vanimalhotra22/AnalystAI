"""Application configuration.

The POC ships with a zero-setup SQLite default so the whole system can be run
without installing PostgreSQL.  Point DATABASE_URL at Postgres and everything
else works unchanged -- all data access goes through SQLAlchemy Core and portable ANSI SQL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- data layer -------------------------------------------------------
    database_url: str = f"sqlite:///{(ROOT / 'data' / 'insightpilot.db').as_posix()}"
    # A separate URL used by the agent's SQL tool.  In Postgres this should be a
    # role with SELECT-only grants; in SQLite we open the same file in ro mode.
    readonly_database_url: str | None = None

    # --- LLM --------------------------------------------------------------
    # "auto" picks the first provider with credentials, else the deterministic
    # rule-based planner/narrator so the demo always runs offline.
    llm_provider: Literal["auto", "anthropic", "openai", "gemini", "none"] = "auto"
    llm_model: str = "claude-sonnet-5"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None

    # --- synthetic data generation ---------------------------------------
    seed: int = 20260824
    history_start: str = "2025-01-01"
    history_end: str = "2026-07-31"

    # --- agent behaviour --------------------------------------------------
    max_investigation_steps: int = 14
    sql_row_limit: int = 5000

    # --- auth -------------------------------------------------------------
    # Signing key for session tokens.  Left unset it falls back to the dev key
    # below, and the API logs a warning at startup -- never ship that.
    DEV_JWT_SECRET: str = "dev-only-insecure-key-set-JWT_SECRET-in-production"
    jwt_secret: str | None = None
    session_minutes: int = 720
    cookie_name: str = "insightpilot_session"
    cookie_secure: bool = False      # True once served over HTTPS
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cors_origins: str = ""           # Comma-separated list of extra origins, e.g. https://my-app.vercel.app
    allow_vercel_preview: bool = True # Automatically allow *.vercel.app origins
    demo_account_enabled: bool = True
    demo_email: str = "demo@insightpilot.local"
    demo_password: str = "insight-demo-2026"

    @property
    def ro_url(self) -> str:
        if self.readonly_database_url:
            return self.readonly_database_url
        if self.database_url.startswith("sqlite:///"):
            path = self.database_url.replace("sqlite:///", "", 1)
            return f"sqlite:///file:{path}?mode=ro&uri=true"
        return self.database_url


settings = Settings()
