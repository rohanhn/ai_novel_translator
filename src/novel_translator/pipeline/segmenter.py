"""Tách chương thành các đoạn vừa với 1 lần gọi LLM, không cắt giữa đoạn văn."""

from __future__ import annotations


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.splitlines() if p.strip()]


def segment(text: str, max_chars: int) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars phải > 0")
    segments: list[str] = []
    buf: list[str] = []
    size = 0
    for para in split_paragraphs(text):
        # Đoạn văn đơn lẻ quá dài: cắt cứng theo max_chars.
        while len(para) > max_chars:
            if buf:
                segments.append("\n".join(buf))
                buf, size = [], 0
            segments.append(para[:max_chars])
            para = para[max_chars:]
        if buf and size + len(para) + 1 > max_chars:
            segments.append("\n".join(buf))
            buf, size = [], 0
        buf.append(para)
        size += len(para) + 1
    if buf:
        segments.append("\n".join(buf))
    return segments
