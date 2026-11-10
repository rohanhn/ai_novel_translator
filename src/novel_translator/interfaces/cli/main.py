"""CLI: `novel <lệnh>`. Chỉ parse tham số + in kết quả; logic nằm trong application/."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from ...application.services import NotFoundError
from ...container import Container, DatabaseConfigError, get_container
from ...domain.models import ChainEvent
from ...domain.ports import DailyQuotaError, TranslationError

app = typer.Typer(help="Dịch truyện Trung → Việt bằng LLM.", no_args_is_help=True)
glossary_app = typer.Typer(help="Quản lý bảng thuật ngữ của truyện.", no_args_is_help=True)
app.add_typer(glossary_app, name="glossary")


def _fail(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _c() -> Container:
    """Lấy container; lỗi cấu hình/kết nối database → thông báo rõ ràng rồi thoát mã 1."""
    try:
        return get_container()
    except DatabaseConfigError as e:
        _fail(str(e))


@app.command("import")
def import_novel(path: Path, title: str | None = typer.Option(None, help="Tên truyện")):
    """Nhập truyện từ file .txt (tự tách chương theo 第X章)."""
    res = _c().library.import_novel(path, title)
    novel, n = res.novel, res.chapters
    typer.echo(f"Đã nhập truyện #{novel.id} '{novel.title}' — {n} chương")


@app.command("list")
def list_novels():
    """Liệt kê các truyện đã nhập."""
    for n in _c().library.list_novels():
        typer.echo(f"#{n.id}\t{n.title}\t{n.source_lang}→{n.target_lang}")


@app.command("chapters")
def list_chapters(novel_id: int):
    """Liệt kê chương và trạng thái dịch."""
    try:
        for ch in _c().library.list_chapters(novel_id):
            typer.echo(f"{ch.index}\t[{ch.status.value}]\t{ch.translated_title or ch.title}")
    except NotFoundError as e:
        _fail(str(e))


@app.command("translate")
def translate(
    novel_id: int,
    start: int = typer.Argument(..., help="Chương bắt đầu"),
    end: int | None = typer.Argument(None, help="Chương kết thúc (mặc định = start)"),
    provider: str | None = typer.Option(None, "--provider", "-p"),
    model: str | None = typer.Option(None, "--model", "-m"),
    force: bool = typer.Option(False, help="Dịch lại cả chương đã dịch"),
    discard_edits: bool = typer.Option(
        False, "--discard-edits", help="Xác nhận dịch lại chương đã biên tập (mất bản sửa tay)"),
):
    """Dịch một hoặc nhiều chương qua chuỗi provider (hoặc --provider/--model để override)."""
    svc = _c().translation
    for i in range(start, (end or start) + 1):
        try:
            ch = svc.translate_chapter(novel_id, i, provider=provider, model=model, force=force,
                                       on_event=_print_chain_event,
                                       confirm_discard_edits=discard_edits)
        except DailyQuotaError as e:
            when = f" Reset lúc {_local(e.reset_at)}." if e.reset_at else ""
            _fail(f"✗ Chương {i}: hết lượt hôm nay ở mọi bước của chuỗi.{when}")
        except (NotFoundError, TranslationError, ValueError) as e:
            _fail(f"✗ Chương {i}: {e}")
        notes = []
        if ch.chain_step and ch.chain_step > 1:
            notes.append(f"bước dự phòng {ch.chain_step}")
        if ch.possible_omission:
            notes.append("có thể sót đoạn")
        extra = f" [{', '.join(notes)}]" if notes else ""
        typer.echo(f"✓ Chương {i}: {ch.translated_title} ({ch.provider}/{ch.model}){extra}")


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _print_chain_event(ev) -> None:
    if isinstance(ev, ChainEvent) and ev.kind == "waiting_for_quota":
        typer.secho(f"… {ev.model}: giới hạn tốc độ, chờ {ev.delay:.0f}s rồi thử lại",
                    fg=typer.colors.YELLOW, err=True)


@app.command("show")
def show(novel_id: int, index: int, source: bool = typer.Option(False, help="Hiện bản gốc")):
    """In nội dung một chương."""
    try:
        ch = _c().library.get_chapter(novel_id, index)
    except NotFoundError as e:
        _fail(str(e))
    if source or not ch.translated_text:
        typer.echo(f"{ch.title}\n\n{ch.source_text}")
    else:
        typer.echo(f"{ch.translated_title}\n\n{ch.translated_text}")


@app.command("export")
def export(novel_id: int, dest: Path, fmt: str = typer.Option("txt", "--format", "-f")):
    """Xuất các chương đã dịch ra file."""
    try:
        out = _c().exports.export(novel_id, dest, fmt)
    except (NotFoundError, ValueError) as e:
        _fail(str(e))
    typer.echo(f"Đã xuất: {out}")


@glossary_app.command("set")
def glossary_set(novel_id: int, source: str, target: str, note: str | None = None):
    _c().glossary.set_term(novel_id, source, target, note)
    typer.echo(f"{source} → {target}")


@glossary_app.command("list")
def glossary_list(novel_id: int):
    for g in _c().glossary.list_terms(novel_id):
        typer.echo(f"{g.source_term}\t{g.target_term}\t{g.note or ''}")


@glossary_app.command("rm")
def glossary_rm(novel_id: int, source: str):
    if not _c().glossary.remove_term(novel_id, source):
        _fail(f"Không có thuật ngữ '{source}'")


@app.command("hash-password")
def hash_password_cmd():
    """Tạo hash argon2 cho mật khẩu đăng nhập web (đặt vào NT_PASSWORD_HASH)."""
    from ...security import hash_password

    password = typer.prompt("Mật khẩu", hide_input=True, confirmation_prompt=True)
    if len(password) < 8:
        _fail("Mật khẩu cần ít nhất 8 ký tự.")
    typer.echo(hash_password(password))
    typer.secho("Đặt vào .env: NT_PASSWORD_HASH='<chuỗi trên>' (giữ dấu nháy đơn vì có ký tự $)",
                err=True, fg=typer.colors.YELLOW)


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Chạy HTTP API (FastAPI)."""
    import uvicorn

    from ...application.auth import AuthConfigError

    c = _c()  # kiểm tra database + migration trước khi nhận request
    try:
        c.auth.ensure_configured()
    except AuthConfigError as e:
        _fail(str(e))

    uvicorn.run("novel_translator.interfaces.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
