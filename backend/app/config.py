"""
SilentVoice AI — Backend Configuration
Reads settings from environment variables (or a .env file at the project root).
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve the .env file relative to the project root (two levels above this file)
_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # CORS
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # App
    app_env: str = "development"
    log_level: str = "info"

    # Phase 2 — Project scanning
    # Path to the project root to scan (relative to the silentvoice-ai/ directory
    # or absolute). Defaults to the bundled demo_project.
    project_root: str = "demo_project"

    # Phase 3 — Groq AI
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    # Maximum file size (bytes) that can be sent to Groq for analysis.
    # Files larger than this return a friendly "too large" message.
    max_file_size_for_ai: int = 102_400  # 100 KB

    # Phase 6 — Code modification proposals
    # Maximum number of pending proposals held in memory at once.
    # When capacity is reached the oldest proposal is evicted.
    max_pending_changes: int = 50
    # Time-to-live (seconds) for a pending proposal before cleanup_expired() removes it.
    pending_change_ttl_seconds: int = 3600  # 1 hour

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def project_root_path(self) -> str:
        """
        Return the resolved absolute path to the configured project root.
        Resolves relative paths against the .env file location (project root).
        """
        if not self.project_root:
            return ""
        p = Path(self.project_root)
        if p.is_absolute():
            return str(p)
        # Resolve relative to the silentvoice-ai/ directory (parent of backend/)
        base = Path(__file__).resolve().parents[2]
        return str((base / p).resolve())


settings = Settings()
