"""Server cho kiểm tra giao diện bằng Playwright (không dùng trong production).

- Dùng database TEST (NT_TEST_DATABASE_URL, tên phải kết thúc bằng `_test`): xóa sạch schema
  rồi nạp dữ liệu mẫu. Không chạy cùng lúc với pytest.
- Provider `echo` có độ trễ để thấy streaming; mật khẩu cố định E2E_PASSWORD.

Chạy từ gốc repo: `.venv/bin/python web/e2e/server.py [port]`
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
E2E_PASSWORD = "e2e-mat-khau"


def _test_db_url() -> str:
    url = os.environ.get("NT_TEST_DATABASE_URL")
    if not url:
        from dotenv import dotenv_values

        url = dotenv_values(ROOT / ".env").get("NT_TEST_DATABASE_URL")
    if not url:
        sys.exit("Thiếu NT_TEST_DATABASE_URL (xem .env.example).")
    if not urlparse(url).path.lstrip("/").endswith("_test"):
        sys.exit("NT_TEST_DATABASE_URL phải trỏ tới database có tên kết thúc bằng _test.")
    return url


def _chapters(n: int, prefix: str) -> str:
    para = "林动站在山上，看着远方的青阳镇，心中暗暗发誓一定要变强。"
    return "".join(
        f"第{i}章 {prefix}{i}\n" + "\n".join(f"{k}. {para}" for k in range(1, 9)) + "\n"
        for i in range(1, n + 1)
    )


def seed(c, tmp: Path) -> None:
    from novel_translator.domain.models import GlossarySuggestion

    def novel(name: str, n: int, prefix: str) -> int:
        p = tmp / f"{name}.txt"
        p.write_text(_chapters(n, prefix), encoding="utf-8")
        return c.library.import_novel(p)[0].id

    a = novel("vu-dong-can-khon", 12, "少年")
    b = novel("pham-nhan-tu-tien", 8, "修仙")
    novel("gia-thien", 5, "遮天")
    for i in (1, 2, 3, 4):
        c.translation.translate_chapter(a, i)
    c.editing.edit_chapter(a, 3, "Tổ thạch", "Bản biên tập tay của chương 3.")
    from novel_translator.domain.models import ChapterStatus

    def patch(index: int, **fields) -> None:
        ch = c.repo.get_chapter(a, index)
        for k, v in fields.items():
            setattr(ch, k, v)
        c.repo.update_chapter(ch)

    patch(2, chain_step=2, model="gemini-3.5-flash-lite")  # model dự phòng
    patch(3, glossary_outdated=True)  # đã biên tập + bộ tên đã đổi
    patch(4, possible_omission=True)
    patch(5, status=ChapterStatus.FAILED)
    c.glossary.set_term(a, "林动", "Lâm Động", "nhân vật chính")
    c.repo.add_suggestion(GlossarySuggestion(a, "苏柔", "Tô Nhu", "person"))
    c.repo.add_suggestion(GlossarySuggestion(a, "青阳镇", "Thanh Dương trấn", "place"))
    c.translation.translate_chapter(b, 1)
    c.reader.save_progress(b, 1, 0.5)
    c.reader.save_progress(a, 4, 0.62)  # đọc gần nhất


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    url = _test_db_url()
    os.chdir(ROOT)
    import tempfile

    import uvicorn

    from novel_translator.config import Settings
    from novel_translator.container import build_container, get_container
    from novel_translator.interfaces.api.app import app
    from novel_translator.security import hash_password
    from novel_translator.storage.db import create_pool

    pool = create_pool(url, 4, var_name="NT_TEST_DATABASE_URL")
    with pool.connection() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    settings = Settings(
        _env_file=None, provider="echo", echo_delay=float(os.environ.get("E2E_ECHO_DELAY", "0.15")),
        password_hash=hash_password(E2E_PASSWORD), cookie_secure=False,
        web_dir=ROOT / "web" / "build", database_url=url,
    )
    container = build_container(settings, pool=pool)
    with tempfile.TemporaryDirectory() as tmp:
        # dữ liệu mẫu dịch ngay, không trễ
        container.translation.provider_factory("echo", None).delay = 0  # type: ignore[attr-defined]
        seed(container, Path(tmp))
        container.translation.provider_factory("echo", None).delay = settings.echo_delay  # type: ignore[attr-defined]
    app.dependency_overrides[get_container] = lambda: container
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
