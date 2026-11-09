"""CLI: `novel <lệnh>`. Chỉ parse tham số + in kết quả; logic nằm trong application/."""

from __future__ import annotations

from pathlib import Path

import typer

from ...application.services import NotFoundError
from ...container import get_container
from ...domain.ports import TranslationError

app = typer.Typer(help="Dịch truyện Trung → Việt bằng LLM.", no_args_is_help=True)
glossary_app = typer.Typer(help="Quản lý bảng thuật ngữ của truyện.", no_args_is_help=True)
app.add_typer(glossary_app, name="glossary")


def _fail(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


@app.command("import")
def import_novel(path: Path, title: str | None = typer.Option(None, help="Tên truyện")):
    """Nhập truyện từ file .txt (tự tách chương theo 第X章)."""
    novel, n = get_container().library.import_novel(path, title)
    typer.echo(f"Đã nhập truyện #{novel.id} '{novel.title}' — {n} chương")


@app.command("list")
def list_novels():
    """Liệt kê các truyện đã nhập."""
    for n in get_container().library.list_novels():
        typer.echo(f"#{n.id}\t{n.title}\t{n.source_lang}→{n.target_lang}")


@app.command("chapters")
def list_chapters(novel_id: int):
    """Liệt kê chương và trạng thái dịch."""
    try:
        for ch in get_container().library.list_chapters(novel_id):
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
):
    """Dịch một hoặc nhiều chương."""
    svc = get_container().translation
    for i in range(start, (end or start) + 1):
        try:
            ch = svc.translate_chapter(novel_id, i, provider=provider, model=model, force=force)
            typer.echo(f"✓ Chương {i}: {ch.translated_title} ({ch.provider}/{ch.model})")
        except (NotFoundError, TranslationError, ValueError) as e:
            _fail(f"✗ Chương {i}: {e}")


@app.command("show")
def show(novel_id: int, index: int, source: bool = typer.Option(False, help="Hiện bản gốc")):
    """In nội dung một chương."""
    try:
        ch = get_container().library.get_chapter(novel_id, index)
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
        out = get_container().exports.export(novel_id, dest, fmt)
    except (NotFoundError, ValueError) as e:
        _fail(str(e))
    typer.echo(f"Đã xuất: {out}")


@glossary_app.command("set")
def glossary_set(novel_id: int, source: str, target: str, note: str | None = None):
    get_container().glossary.set_term(novel_id, source, target, note)
    typer.echo(f"{source} → {target}")


@glossary_app.command("list")
def glossary_list(novel_id: int):
    for g in get_container().glossary.list_terms(novel_id):
        typer.echo(f"{g.source_term}\t{g.target_term}\t{g.note or ''}")


@glossary_app.command("rm")
def glossary_rm(novel_id: int, source: str):
    if not get_container().glossary.remove_term(novel_id, source):
        _fail(f"Không có thuật ngữ '{source}'")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000):
    """Chạy HTTP API (FastAPI)."""
    import uvicorn

    uvicorn.run("novel_translator.interfaces.api.app:app", host=host, port=port)


if __name__ == "__main__":
    app()
