from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Cấu hình toàn cục, đọc từ biến môi trường (tiền tố NT_) hoặc file .env."""

    model_config = SettingsConfigDict(env_prefix="NT_", env_file=".env", extra="ignore")

    provider: str = "anthropic"
    model: str | None = None
    # PostgreSQL: postgresql://<role>:<pass>@<host>:5432/<db>; pool nhỏ vì instance dùng chung
    database_url: str | None = None
    db_pool_max: int = 5
    max_segment_chars: int = 3000

    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"
