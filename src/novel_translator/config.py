from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình toàn cục, đọc từ biến môi trường (tiền tố NT_) hoặc file .env."""

    model_config = SettingsConfigDict(env_prefix="NT_", env_file=".env", extra="ignore")

    provider: str = "anthropic"
    model: str | None = None
    db_path: Path = Path("data/novels.db")
    max_segment_chars: int = 3000

    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
