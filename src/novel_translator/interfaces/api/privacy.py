"""Không cho công cụ tìm kiếm lập chỉ mục (spec access-control "No search indexing")."""

from __future__ import annotations

from fastapi import Request

ROBOTS_TXT = "User-agent: *\nDisallow: /\n"
NOINDEX = "noindex, nofollow"


async def noindex_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Robots-Tag"] = NOINDEX
    return response
