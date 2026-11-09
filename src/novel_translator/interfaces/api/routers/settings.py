"""Cài đặt: chuỗi provider đang dùng và các provider có sẵn (spec interfaces)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ....container import Container, get_container
from ....providers import available_providers

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def settings(c: Container = Depends(get_container)):
    """Không bao giờ trả về giá trị key; chỉ cho biết đã cấu hình hay chưa."""
    s = c.settings
    return {
        "chain": [{"step": i, "provider": st.provider, "model": st.model}
                  for i, st in enumerate(s.chain_steps(), start=1)],
        "provider_override": s.provider,
        "available_providers": available_providers(),
        "gemini_key_configured": bool(s.gemini_api_key and s.gemini_api_key.get_secret_value()),
        "prefetch_enabled": c.prefetch.enabled(),
    }
