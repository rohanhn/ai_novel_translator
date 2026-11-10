"""HTTP auth (design D7): cookie session, CSRF bằng header, chặn brute-force theo IP."""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Sequence

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ...application.auth import SESSION_IDLE, InvalidCredentialsError, LoginLockedError
from ...config import IPNetwork
from ...container import Container, get_container

COOKIE = "nt_session"
CSRF_HEADER = "X-Requested-With"
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Không cần session: endpoint login, health check, robots. Ngoài ra mọi đường dẫn của web app
# (shell SPA + asset tĩnh, không chứa dữ liệu) đều công khai, xem is_public.
PUBLIC_PATHS = frozenset({"/health", "/api/health", "/robots.txt", "/api/auth/login"})

router = APIRouter(prefix="/api/auth", tags=["auth"])


def container_of(request: Request) -> Container:
    resolver = request.app.dependency_overrides.get(get_container, get_container)
    return resolver()


def is_public(path: str) -> bool:
    from .web import is_web_path

    return path in PUBLIC_PATHS or is_web_path(path)


def client_ip(request: Request, trusted: Sequence[IPNetwork]) -> str:
    """IP thật của client. Chỉ tin X-Forwarded-For khi kết nối đến từ proxy tin cậy (IP hoặc
    dải CIDR); lấy địa chỉ cuối cùng (do proxy tin cậy ghi vào)."""
    peer = request.client.host if request.client else "unknown"
    if _in_networks(peer, trusted):
        hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",")]
        hops = [h for h in hops if _is_ip(h)]
        if hops:
            return hops[-1]
    return peer


def _in_networks(value: str, nets: Sequence[IPNetwork]) -> bool:
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False  # peer không phải IP (vd. "unknown") thì không tin
    return any(addr in net for net in nets)


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


async def auth_middleware(request: Request, call_next):
    if request.method in MUTATING and not request.headers.get(CSRF_HEADER):
        return JSONResponse(status_code=403,
                            content={"detail": f"Thiếu header {CSRF_HEADER}."})
    if not is_public(request.url.path) and not container_of(request).auth.authenticate(
            request.cookies.get(COOKIE)):
        return JSONResponse(status_code=401, content={"detail": "Chưa đăng nhập."})
    return await call_next(request)


class LoginIn(BaseModel):
    password: str


@router.post("/login", status_code=204)
def login(body: LoginIn, request: Request, response: Response):
    c = container_of(request)
    ip = client_ip(request, c.settings.trusted_proxy_networks)
    try:
        token = c.auth.login(body.password, ip)
    except LoginLockedError as e:
        return JSONResponse(
            status_code=429, content={"detail": str(e)},
            headers={"Retry-After": str(math.ceil(e.retry_after.total_seconds()))},
        )
    except InvalidCredentialsError as e:
        return JSONResponse(status_code=401, content={"detail": str(e)})
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_IDLE.total_seconds()), httponly=True,
        secure=c.settings.cookie_secure, samesite="lax", path="/",
    )
    response.status_code = 204
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    container_of(request).auth.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax",
                           secure=container_of(request).settings.cookie_secure)
    response.status_code = 204
    return response


@router.get("/me")
def me():
    """Đã qua middleware nghĩa là session hợp lệ."""
    return {"authenticated": True}
