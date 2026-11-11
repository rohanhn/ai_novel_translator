"""CLI: `novel <lệnh>`. Chỉ parse tham số + in kết quả; logic nằm trong application/."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

from ...application.services import InvalidOperationError, NotFoundError
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
def import_novel(
    path: Path,
    title: str | None = typer.Option(None, help="Tên truyện"),
    lang: str | None = typer.Option(
        None, "--lang", help="Ngôn ngữ file: zh (raw, cần dịch) | vi (bản dịch có sẵn)."
    ),
    into: int | None = typer.Option(
        None, "--into", help="Thêm chương mới vào truyện có id này (nối sau chương cuối) thay "
        "vì tạo truyện mới. Tải lại cả bộ: dùng web."
    ),
):
    """Nhập truyện từ file .txt: tự tách chương (Trung/Việt) và nhận diện ngôn ngữ, lưu ngay."""
    if into is not None:
        if title is not None or lang is not None:
            _fail("--into không dùng cùng --title hoặc --lang (lấy theo truyện có sẵn).")
        _append_into(path, into)
        return
    if lang is not None and lang not in ("zh", "vi"):
        _fail("--lang chỉ nhận zh hoặc vi.")
    try:
        res = _c().library.import_novel(path, title, lang)
    except (ValueError, OSError) as e:
        _fail(str(e))
    novel = res.novel
    kind = "bản dịch có sẵn, đọc ngay" if novel.pretranslated else "raw tiếng Trung, cần dịch"
    typer.echo(f"Đã nhập truyện #{novel.id} '{novel.title}' — {res.chapters} chương ({kind})")
    if lang is None and res.detected_lang == "unknown":
        typer.secho("Cảnh báo: không nhận diện được ngôn ngữ, coi là tiếng Trung (zh). "
                    "Dùng --lang để chọn.", fg=typer.colors.YELLOW)
    for w in res.plan.warnings:
        typer.secho(f"Cảnh báo: {w.message}", fg=typer.colors.YELLOW)
    for ch in res.plan.chapters:
        for w in ch.warnings:
            typer.secho(f"Cảnh báo · chương {ch.number} '{ch.title}': {w.message}",
                        fg=typer.colors.YELLOW)


def _append_into(path: Path, novel_id: int) -> None:
    """`novel import <file> --into <id>` (spec chapter-update "CLI append")."""
    c = _c()
    try:
        text = c.library.loader.read_text(path)
        res, plan = c.chapter_updates.append_text(novel_id, text)
    except NotFoundError as e:
        _fail(str(e))
    except InvalidOperationError as e:
        _fail(f"{e} Dùng \"Cập nhật từ txt\" trên web để chọn chỗ nối hoặc tải lại cả bộ.")
    except (ValueError, OSError) as e:
        _fail(str(e))
    if plan.anchor:
        typer.echo(f"Điểm nối: sau chương {plan.anchor.stored_index} '{plan.anchor.title}'")
    else:
        typer.echo("Điểm nối: file bắt đầu ngay sau chương cuối (theo số chương)")
    for w in plan.warnings:
        typer.secho(f"Cảnh báo: {w.message}", fg=typer.colors.YELLOW)
    typer.echo(f"Đã thêm {res.added} chương vào truyện #{novel_id} '{res.novel.title}' "
               f"(tổng {res.chapter_count} chương)")
    if plan.differing:
        typer.secho(f"Lưu ý: {len(plan.differing)} chương cũ khác nội dung trong file, không bị "
                    "đổi; dùng tải lại cả bộ trên web nếu muốn cập nhật.", fg=typer.colors.YELLOW)


@app.command("list")
def list_novels():
    """Liệt kê các truyện đã nhập (id, tên, tác giả, ngôn ngữ)."""
    for n in _c().library.list_novels():
        typer.echo(f"#{n.id}\t{n.title}\t{n.author or '-'}\t{n.source_lang}→{n.target_lang}")


@app.command("edit")
def edit_novel(
    novel_id: int,
    title: str | None = typer.Option(None, "--title", help="Tên truyện mới"),
    author: str | None = typer.Option(None, "--author", help='Tác giả ("" để xoá)'),
    description: str | None = typer.Option(
        None, "--description", help='Giới thiệu ngắn, giữ xuống dòng ("" để xoá)'),
):
    """Sửa tên, tác giả, giới thiệu ngắn của truyện. Ảnh bìa: chỉ sửa trên web."""
    fields = {k: v for k, v in
              (("title", title), ("author", author), ("description", description))
              if v is not None}
    if not fields:
        _fail("Cần ít nhất một trong --title, --author, --description.")
    try:
        n = _c().library.update_details(novel_id, **fields)
    except (NotFoundError, ValueError) as e:
        _fail(str(e))
    typer.echo(f"Đã cập nhật truyện #{n.id}: '{n.title}'"
               f" · tác giả: {n.author or '-'}"
               f" · giới thiệu: {len(n.description or '')} ký tự")


@app.command("chapters")
def list_chapters(novel_id: int):
    """Liệt kê chương và trạng thái dịch."""
    try:
        for ch in _c().library.list_chapters(novel_id):
            flag = (f"\t[còn {ch.untranslated_han} chữ chưa dịch]"
                    if ch.untranslated_han else "")
            typer.echo(f"{ch.index}\t[{ch.status.value}]\t{ch.translated_title or ch.title}{flag}")
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
        if ch.untranslated_han:
            notes.append(f"còn {ch.untranslated_han} chữ chưa dịch")
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
