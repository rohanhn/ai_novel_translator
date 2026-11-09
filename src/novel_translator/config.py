from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_CHAIN = "gemini:gemini-3.5-flash,gemini:gemini-3.5-flash-lite"


@dataclass(frozen=True)
class ChainStep:
    provider: str
    model: str


def parse_chain(spec: str) -> list[ChainStep]:
    """'gemini:model-a,gemini:model-b' → [ChainStep, ...] (giữ thứ tự)."""
    steps: list[ChainStep] = []
    for raw in spec.split(","):
        raw = raw.strip()
        if not raw:
            continue
        provider, sep, model = raw.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError(f"NT_CHAIN sai định dạng ở '{raw}' (cần 'provider:model').")
        steps.append(ChainStep(provider.strip(), model.strip()))
    if not steps:
        raise ValueError("NT_CHAIN rỗng.")
    return steps


class Settings(BaseSettings):
    """Cấu hình toàn cục, đọc từ biến môi trường (tiền tố NT_) hoặc file .env."""

    model_config = SettingsConfigDict(env_prefix="NT_", env_file=".env", extra="ignore")

    # Chuỗi fallback mặc định cho bản dịch (design D2/D10). Một key cho mỗi provider: cấu hình
    # không cho phép gán key khác nhau theo bước (spec "No quota circumvention").
    chain: str = DEFAULT_CHAIN
    # Override cho CLI/dev: NT_PROVIDER bỏ qua chuỗi và dùng thẳng provider đó; NT_MODEL dùng
    # model đó (với provider của bước 1 nếu không đặt NT_PROVIDER). Để trống = dùng chuỗi.
    provider: str | None = None
    model: str | None = None

    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    gemini_timeout: float = 120.0

    # PostgreSQL: postgresql://<role>:<pass>@<host>:5432/<db>; pool nhỏ vì instance dùng chung
    database_url: str | None = None
    db_pool_max: int = 5
    # Chỉ cắt chương thành nhiều request khi vượt ngưỡng này (ký tự).
    chapter_char_limit: int = 20000

    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"

    def chain_steps(self) -> list[ChainStep]:
        return parse_chain(self.chain)
