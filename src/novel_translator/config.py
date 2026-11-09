from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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

    # Đăng nhập: hash argon2 (tạo bằng `novel hash-password`), không bao giờ là mật khẩu gốc.
    password_hash: SecretStr | None = None
    # IP (phân tách bằng dấu phẩy) của reverse proxy được tin để đọc X-Forwarded-For.
    trusted_proxy: str | None = None
    # Cookie Secure (bắt buộc với HTTPS); chỉ tắt khi chạy thử qua http://localhost.
    cookie_secure: bool = True

    # PostgreSQL: postgresql://<role>:<pass>@<host>:5432/<db>; pool nhỏ vì instance dùng chung
    database_url: str | None = None
    db_pool_max: int = 5
    # Chỉ cắt chương thành nhiều request khi vượt ngưỡng này (ký tự).
    chapter_char_limit: int = 20000

    # Bản build của web app (SvelteKit SPA). Không tồn tại → chỉ chạy API.
    web_dir: Path = Path("web/build")

    # Chỉ cho dev/kiểm tra giao diện: độ trễ (giây) giữa các dòng của provider `echo`.
    echo_delay: float = 0.0

    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434/v1"

    def chain_steps(self) -> list[ChainStep]:
        return parse_chain(self.chain)
