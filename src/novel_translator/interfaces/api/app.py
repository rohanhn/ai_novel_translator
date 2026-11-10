"""HTTP API. Chỉ map request/response ↔ application services; không chứa logic nghiệp vụ.

Mọi endpoint nằm dưới `/api` (trừ `/health` là bí danh của `/api/health`, và `/robots.txt`),
chia router theo nhóm.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ...container import get_container
from . import errors, web
from .auth import COOKIE, auth_middleware, container_of
from .auth import router as auth_router
from .privacy import ROBOTS_TXT, noindex_middleware
from .routers import chapters, glossary, imports, library, prefetch, reading, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Spec "Missing configuration": không có mật khẩu thì không khởi động.
    resolver = app.dependency_overrides.get(get_container, get_container)
    c = resolver()
    c.auth.ensure_configured()
    # Logger của uvicorn đã có handler → dòng này hiện trong `docker compose logs`.
    logging.getLogger("uvicorn.error").info("Novel Translator %s", c.settings.version)
    yield


app = FastAPI(title="Novel Translator API", version="0.2.0", lifespan=lifespan)
app.middleware("http")(auth_middleware)
# Đăng ký sau → bọc ngoài cùng: cả response 401/403 của auth cũng có header noindex.
app.middleware("http")(noindex_middleware)
errors.install(app)
for r in (auth_router, library.router, library.covers_router, imports.router, chapters.router, glossary.router, reading.router,
          prefetch.router, settings.router):
    app.include_router(r)


@app.get("/api/health")
@app.get("/health", include_in_schema=False)
def health(request: Request):
    """Công khai, cho HEALTHCHECK. Chỉ người đã đăng nhập mới thấy version (spec deployment
    "Health endpoint"); không bao giờ trả chi tiết lỗi."""
    c = container_of(request)
    ok = c.database_ok()
    body = {"status": "ok" if ok else "unavailable"}
    if ok and c.auth.authenticate(request.cookies.get(COOKIE)):
        body["version"] = c.settings.version
    return JSONResponse(status_code=200 if ok else 503, content=body)


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return PlainTextResponse(ROBOTS_TXT)


# Đăng ký cuối cùng: route bắt-tất-cả của SPA không được che các route ở trên.
app.include_router(web.router)
