"""Prompt dịch. System prompt giữ ổn định giữa các đoạn của cùng truyện để tận dụng prompt caching."""

from __future__ import annotations

from ..domain.models import GlossaryEntry, Novel

LANG_NAMES = {"zh": "tiếng Trung", "vi": "tiếng Việt", "en": "tiếng Anh"}

BASE_SYSTEM = """Bạn là dịch giả truyện mạng chuyên nghiệp, dịch từ {src} sang {tgt}.

Yêu cầu:
- Dịch trọn vẹn, đúng nghĩa, văn phong tự nhiên, mượt như truyện xuất bản tiếng Việt.
- Giữ nguyên số đoạn và thứ tự đoạn; mỗi đoạn nguồn tương ứng một đoạn dịch, ngăn cách bằng xuống dòng.
- Tên riêng, chiêu thức, cảnh giới, địa danh dùng Hán-Việt khi phù hợp với thể loại.
- Xưng hô phù hợp quan hệ nhân vật và bối cảnh (cổ đại/hiện đại).
- Chỉ trả về bản dịch, không giải thích, không thêm tiêu đề hay ghi chú.
{glossary}"""


def build_system_prompt(novel: Novel, glossary: list[GlossaryEntry]) -> str:
    glossary_block = ""
    if glossary:
        lines = "\n".join(
            f"- {g.source_term} → {g.target_term}" + (f" ({g.note})" if g.note else "")
            for g in sorted(glossary, key=lambda g: g.source_term)
        )
        glossary_block = f"\nBẢNG THUẬT NGỮ BẮT BUỘC (luôn dịch đúng như sau):\n{lines}\n"
    return BASE_SYSTEM.format(
        src=LANG_NAMES.get(novel.source_lang, novel.source_lang),
        tgt=LANG_NAMES.get(novel.target_lang, novel.target_lang),
        glossary=glossary_block,
    )
