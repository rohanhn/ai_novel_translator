"""HTTP API. Chỉ map request/response ↔ application services; không chứa logic nghiệp vụ."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from ...application.services import NotFoundError
from ...container import Container, get_container
from ...domain.models import Chapter, Novel
from ...domain.ports import TranslationError
from ...ingest.txt_loader import TxtLoader
from ...providers import available_providers
from .auth import auth_middleware
from .auth import router as auth_router
from .privacy import ROBOTS_TXT, noindex_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spec "Missing configuration": không có mật khẩu thì không khởi động.
    resolver = app.dependency_overrides.get(get_container, get_container)
    resolver().auth.ensure_configured()
    yield


app = FastAPI(title="Novel Translator API", version="0.1.0", lifespan=lifespan)
app.middleware("http")(auth_middleware)
# Đăng ký sau → bọc ngoài cùng: cả response 401/403 của auth cũng có header noindex.
app.middleware("http")(noindex_middleware)
app.include_router(auth_router)


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(ROBOTS_TXT)


# ---------- schemas ----------
class NovelOut(BaseModel):
    id: int
    title: str
    source_lang: str
    target_lang: str

    @classmethod
    def of(cls, n: Novel) -> NovelOut:
        return cls(id=n.id, title=n.title, source_lang=n.source_lang, target_lang=n.target_lang)


class ChapterSummary(BaseModel):
    index: int
    title: str
    translated_title: str | None
    status: str


class ChapterOut(ChapterSummary):
    source_text: str
    translated_text: str | None
    provider: str | None
    model: str | None

    @classmethod
    def of(cls, c: Chapter) -> ChapterOut:
        return cls(
            index=c.index, title=c.title, translated_title=c.translated_title,
            status=c.status.value, source_text=c.source_text,
            translated_text=c.translated_text, provider=c.provider, model=c.model,
        )


class TranslateIn(BaseModel):
    provider: str | None = None
    model: str | None = None
    force: bool = False


class GlossaryIn(BaseModel):
    source_term: str
    target_term: str
    note: str | None = None


# ---------- error mapping ----------
@app.exception_handler(NotFoundError)
async def _not_found(_, exc: NotFoundError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=404, content={"detail": str(exc)})


# ---------- routes ----------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/providers")
def providers():
    return {"providers": available_providers()}


@app.get("/novels", response_model=list[NovelOut])
def list_novels(c: Container = Depends(get_container)):
    return [NovelOut.of(n) for n in c.library.list_novels()]


@app.post("/novels", response_model=NovelOut, status_code=201)
async def upload_novel(file: UploadFile, title: str | None = None,
                       c: Container = Depends(get_container)):
    raw = (await file.read()).decode("utf-8", errors="replace")
    chapters = TxtLoader.parse(raw)
    if not chapters:
        raise HTTPException(400, "File rỗng")
    # Tái dùng use case import với loader trong bộ nhớ.
    from ...application.services import LibraryService

    svc = LibraryService(c.library.repo, _StaticLoader(chapters))
    novel, _ = svc.import_novel(Path(file.filename or "novel.txt"), title)
    return NovelOut.of(novel)


@app.get("/novels/{novel_id}/chapters", response_model=list[ChapterSummary])
def list_chapters(novel_id: int, c: Container = Depends(get_container)):
    return [
        ChapterSummary(index=ch.index, title=ch.title, translated_title=ch.translated_title,
                       status=ch.status.value)
        for ch in c.library.list_chapters(novel_id)
    ]


@app.get("/novels/{novel_id}/chapters/{index}", response_model=ChapterOut)
def get_chapter(novel_id: int, index: int, c: Container = Depends(get_container)):
    return ChapterOut.of(c.library.get_chapter(novel_id, index))


@app.post("/novels/{novel_id}/chapters/{index}/translate", response_model=ChapterOut)
def translate_chapter(novel_id: int, index: int, body: TranslateIn,
                      c: Container = Depends(get_container)):
    try:
        ch = c.translation.translate_chapter(
            novel_id, index, provider=body.provider, model=body.model, force=body.force
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except TranslationError as e:
        raise HTTPException(502, str(e)) from e
    return ChapterOut.of(ch)


@app.get("/novels/{novel_id}/glossary", response_model=list[GlossaryIn])
def list_glossary(novel_id: int, c: Container = Depends(get_container)):
    return [GlossaryIn(source_term=g.source_term, target_term=g.target_term, note=g.note)
            for g in c.glossary.list_terms(novel_id)]


@app.put("/novels/{novel_id}/glossary", response_model=GlossaryIn)
def set_glossary(novel_id: int, body: GlossaryIn, c: Container = Depends(get_container)):
    c.library.get_novel(novel_id)
    c.glossary.set_term(novel_id, body.source_term, body.target_term, body.note)
    return body


@app.delete("/novels/{novel_id}/glossary/{source_term}", status_code=204)
def delete_glossary(novel_id: int, source_term: str, c: Container = Depends(get_container)):
    if not c.glossary.remove_term(novel_id, source_term):
        raise HTTPException(404, "Không có thuật ngữ")


class _StaticLoader:
    def __init__(self, chapters):
        self._chapters = chapters

    def load(self, path):
        return self._chapters
