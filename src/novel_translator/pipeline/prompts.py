"""Prompt dịch theo định dạng 3 phần (design D1).

Phần hướng dẫn (system) cố định cho cả truyện + bộ tên hiện tại → giống hệt nhau giữa các
đoạn của cùng chương để provider cache được. Nội dung chương nằm ở phần user.
"""

from __future__ import annotations

from ..domain.models import GlossaryEntry, Novel

LANG_NAMES = {"zh": "tiếng Trung", "vi": "tiếng Việt", "en": "tiếng Anh"}

TITLE, BODY, NAMES = "<<TITLE>>", "<<BODY>>", "<<NAMES>>"

BASE_SYSTEM = """Bạn là dịch giả truyện mạng chuyên nghiệp, dịch từ {src} sang {tgt}.

Yêu cầu dịch:
- Dịch trọn vẹn, đúng nghĩa, văn phong tự nhiên, mượt như truyện xuất bản tiếng Việt.
- Giữ nguyên số đoạn và thứ tự đoạn: mỗi đoạn nguồn là MỘT dòng dịch; không gộp, không bỏ đoạn.
- Tên riêng, chiêu thức, cảnh giới, địa danh dùng Hán-Việt khi phù hợp với thể loại.
- Xưng hô phù hợp quan hệ nhân vật và bối cảnh (cổ đại/hiện đại).
- Không giải thích, không thêm ghi chú ngoài định dạng dưới đây.

Định dạng đầu vào: phần {title} (có thể không có) chứa tiêu đề chương, phần {body} chứa nội dung.

Định dạng trả lời (bắt buộc, đúng thứ tự, mỗi dấu mốc nằm trên một dòng riêng):
{title}
<tiêu đề đã dịch — chỉ có khi đầu vào có phần {title}>
{body}
<nội dung đã dịch, mỗi đoạn một dòng>
{names}
<mỗi dòng một tên riêng MỚI xuất hiện trong chương mà KHÔNG có trong bảng thuật ngữ, dạng:
nguyên văn | bản dịch | loại>

Phần {names} để trống nếu không có tên mới. Loại là một từ ngắn: nhân vật, địa danh, môn phái,
công pháp, cảnh giới, vật phẩm, khác.

Ví dụ:
Đầu vào:
{title}
第一章 少年
{body}
林动站在山顶，望着远方的青阳镇。
他握紧了拳头。
Trả lời:
{title}
Chương 1: Thiếu niên
{body}
Lâm Động đứng trên đỉnh núi, nhìn về phía trấn Thanh Dương ở nơi xa.
Hắn siết chặt nắm đấm.
{names}
林动 | Lâm Động | nhân vật
青阳镇 | trấn Thanh Dương | địa danh
{glossary}"""


def build_system_prompt(novel: Novel, glossary: list[GlossaryEntry]) -> str:
    glossary_block = ""
    if glossary:
        lines = "\n".join(
            f"- {g.source_term} → {g.target_term}" + (f" ({g.note})" if g.note else "")
            for g in sorted(glossary, key=lambda g: g.source_term)
        )
        glossary_block = (
            "\nBẢNG THUẬT NGỮ BẮT BUỘC (luôn dịch đúng như sau, không đưa vào phần "
            f"{NAMES}):\n{lines}\n"
        )
    return BASE_SYSTEM.format(
        src=LANG_NAMES.get(novel.source_lang, novel.source_lang),
        tgt=LANG_NAMES.get(novel.target_lang, novel.target_lang),
        title=TITLE, body=BODY, names=NAMES,
        glossary=glossary_block,
    )


def build_user_prompt(body: str, title: str | None = None) -> str:
    """Nội dung gửi đi. Đoạn đầu của chương kèm tiêu đề; các đoạn sau chỉ có BODY."""
    head = f"{TITLE}\n{title.strip()}\n" if title and title.strip() else ""
    return f"{head}{BODY}\n{body.strip()}\n"
