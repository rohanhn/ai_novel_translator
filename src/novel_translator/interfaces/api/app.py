"""HTTP API. Chỉ map request/response ↔ application services; không chứa logic nghiệp vụ.

Mọi endpoint nằm dưới `/api` (trừ `/health`, `/robots.txt`), chia router theo nhóm.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from ...container import get_container
from . import errors
from .auth import auth_middleware
from .auth import router as auth_router
from .privacy import ROBOTS_TXT, noindex_middleware
from .routers import chapters, glossary, library, prefetch, reading, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spec "Missing configuration": không có mật khẩu thì không khởi động.
    resolver = app.dependency_overrides.get(get_container, get_container)
    resolver().auth.ensure_configured()
    yield


app = FastAPI(title="Novel Translator API", version="0.2.0", lifespan=lifespan)
app.middleware("http")(auth_middleware)
# Đăng ký sau → bọc ngoài cùng: cả response 401/403 của auth cũng có header noindex.
app.middleware("http")(noindex_middleware)
errors.install(app)
for r in (auth_router, library.router, chapters.router, glossary.router, reading.router,
          prefetch.router, settings.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(ROBOTS_TXT)
