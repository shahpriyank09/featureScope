from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    greptile_api_key: str | None = None
    greptile_mcp_url: str = "https://api.greptile.com/mcp"
    github_token: str | None = None

    codex_cli_path: str = "codex"
    codex_model: str | None = None
    codex_cli_timeout_seconds: float = Field(default=240, gt=0)

    claude_mem_enabled: bool = True
    claude_mem_base_url: str | None = None
    claude_mem_timeout_seconds: float = Field(default=30, gt=0)

    prism_cache_dir: Path = Path(".cache/prism")
    prism_offline_demo: bool = False
    log_level: str = "INFO"
    request_timeout_seconds: float = Field(default=90, gt=0)

    def resolved_claude_mem_base_url(self) -> str | None:
        """Resolve Claude-Mem's local worker without assuming a universal port."""

        if not self.claude_mem_enabled:
            return None
        if self.claude_mem_base_url:
            return self.claude_mem_base_url.rstrip("/")

        data_dir = Path(os.environ.get("CLAUDE_MEM_DATA_DIR", "~/.claude-mem")).expanduser()
        settings_path = data_dir / "settings.json"
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            port = payload.get("CLAUDE_MEM_WORKER_PORT")
            if port:
                return f"http://127.0.0.1:{int(port)}"
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        getuid = getattr(os, "getuid", None)
        uid = getuid() if getuid else 77
        return f"http://127.0.0.1:{37700 + (uid % 100)}"


def get_settings(**overrides: object) -> Settings:
    return Settings(**overrides)
