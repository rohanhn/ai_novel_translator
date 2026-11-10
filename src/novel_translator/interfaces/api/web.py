"""Phục vụ web app (SvelteKit SPA tĩnh, design D8) ở `/` cùng process với API.

- File có thật trong `web_dir` → trả file đó. Asset có hash (`/_app/immutable/`) cache lâu.
- Đường dẫn khác (deep link như `/novels/1/chapters/12`) → `index.html`; router phía client
  hiển thị đúng trang. Shell SPA không chứa dữ liệu nên không cần session; dữ liệu đi qua
  `/api` (cần session, 401 → client chuyển sang `/login`).
- `/api/...` không khớp route nào → 404 JSON, không trả `index.html`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

from .auth import container_of

API_PREFIX = "/api/"
# Không bao giờ coi là trang của SPA (vẫn cần session như API).
PROTECTED_NON_API = frozenset({"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})

router = APIRouter(include_in_schema=False)


def is_web_path(path: str) -> bool:
    return not (path.startswith(API_PREFIX) or path == "/api" or path in PROTECTED_NON_API)


def _safe_file(root: Path, rel: str) -> Path | None:
    """File trong `root` ứng với đường dẫn URL, chặn thoát ra ngoài (`..`, symlink)."""
    if not rel:
        return None
    try:
        candidate = (root / rel).resolve()
        candidate.relative_to(root)
    except (ValueError, OSError):
        return None
    return candidate if candidate.is_file() else None


@router.get("/{path:path}")
def spa(path: str, request: Request):
    if not is_web_path(request.url.path):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    root = Path(container_of(request).settings.web_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=404, content={
            "detail": "Chưa build web app (cd web && npm run build)."})
    file = _safe_file(root, path)
    if file is not None:
        immutable = path.startswith("_app/immutable/")
        headers = {"Cache-Control": "public, max-age=31536000, immutable" if immutable
                   else "no-cache"}
        return FileResponse(file, headers=headers)
    return FileResponse(index, headers={"Cache-Control": "no-cache"})
