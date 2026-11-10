"""So khớp chương đang lưu với chương trong file mới (spec `chapter-update`, design D1).

Thuần Python, không phụ thuộc: tính điểm nối (chế độ thêm), kết quả tải lại cả bộ và vị trí
đọc mới. Hai mức khớp:
- khớp nội dung: text gốc giống nhau sau khi bỏ khoảng trắng đầu/cuối dòng và dòng trống;
- khớp tiêu đề: cùng số chương và cùng phần tên (bỏ khoảng trắng, NFKC).
Khóa nằm trong `Keyer` để nguồn khác (vd. link URL) cắm thêm khóa định danh riêng.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from . import chapter_split

VOLUME_SEPARATOR = " · "  # chapter_split ghép tiêu đề quyển vào trước tiêu đề chương
_LEADING_SEPARATORS = ":：-–—.．、"
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class StoredRef:
    """Chương đang lưu (chỉ phần cần để so khớp)."""

    index: int
    title: str
    source_text: str
    status: str = "pending"


@dataclass(frozen=True)
class Incoming:
    """Chương trong file mới; `position` là thứ tự 1..n trong kết quả tách."""

    position: int
    title: str
    body: str
    heading_number: int | None = None


TitleKey = tuple[int | None, str]


def content_key(text: str) -> str:
    """Băm nội dung sau khi bỏ khoảng trắng đầu/cuối mỗi dòng, dòng trống, chuẩn hóa NFKC."""
    norm = unicodedata.normalize("NFKC", text.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [ln.strip() for ln in norm.split("\n")]
    joined = "\n".join(ln for ln in lines if ln)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _norm_name(s: str) -> str:
    s = _WS.sub("", unicodedata.normalize("NFKC", s))
    return s.lstrip(_LEADING_SEPARATORS).casefold()


def title_number(title: str) -> int | None:
    """Số chương đọc được từ tiêu đề (bỏ tiền tố quyển), None nếu không có."""
    parts = chapter_split.heading_parts(title.rsplit(VOLUME_SEPARATOR, 1)[-1])
    if parts and parts[0] is chapter_split.HeadingKind.CHAPTER:
        return parts[1]
    return None


def title_key(title: str) -> TitleKey:
    """(số chương, phần tên chuẩn hóa). Bỏ tiền tố quyển; không đọc được số → (None, cả tiêu đề)."""
    last = title.rsplit(VOLUME_SEPARATOR, 1)[-1]
    parts = chapter_split.heading_parts(last)
    if parts and parts[0] is chapter_split.HeadingKind.CHAPTER:
        return parts[1], _norm_name(parts[2])
    return None, _norm_name(last)


class Keyer:
    """Các khóa so khớp; lớp con có thể đổi cách tính (vd. thêm khóa URL chương)."""

    def content(self, text: str) -> str:
        return content_key(text)

    def title(self, title: str) -> TitleKey:
        return title_key(title)


DEFAULT_KEYER = Keyer()


# --- Cảnh báo -------------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeWarning:
    code: str
    message: str
    params: dict


# --- Chế độ thêm ----------------------------------------------------------------------------

ANCHOR_LOOKBACK = 5  # ngoài chương cuối, thử thêm tối đa 5 chương trước nó


@dataclass(frozen=True)
class Anchor:
    stored_index: int
    position: int  # vị trí trong file (Incoming.position)
    match: str  # "content" | "title"


@dataclass
class AppendPlan:
    anchor: Anchor | None
    needs_start: bool  # không tự xác định được: người dùng phải chọn chương bắt đầu
    to_add: list[Incoming]
    warnings: list[MergeWarning]
    differing: list[StoredRef]  # chương trước điểm nối: cùng tiêu đề nhưng nội dung khác

    @property
    def nothing_new(self) -> bool:
        return not self.needs_start and not self.to_add


@dataclass(frozen=True)
class _Keys:
    content: list[str]
    title: list[TitleKey]


def _incoming_keys(incoming: list[Incoming], keyer: Keyer) -> _Keys:
    return _Keys([keyer.content(i.body) for i in incoming], [keyer.title(i.title) for i in incoming])


def _find_last(stored: StoredRef, incoming: list[Incoming], keys: _Keys,
               keyer: Keyer) -> Anchor | None:
    for keys_of, key, match in ((keys.content, keyer.content(stored.source_text), "content"),
                                (keys.title, keyer.title(stored.title), "title")):
        for i in range(len(incoming) - 1, -1, -1):
            if keys_of[i] == key:
                return Anchor(stored.index, incoming[i].position, match)
    return None


def _number_of(inc: Incoming) -> int | None:
    return inc.heading_number if inc.heading_number is not None else title_number(inc.title)


def _differing(stored: list[StoredRef], incoming: list[Incoming], keys: _Keys, before: int,
               keyer: Keyer) -> list[StoredRef]:
    """Chương đang lưu cùng tiêu đề với một chương trong file (trước vị trí `before`) nhưng nội
    dung khác: chế độ thêm không đụng tới, chỉ báo để người dùng cân nhắc tải lại."""
    by_title: dict[TitleKey, list[StoredRef]] = {}
    for s in stored:
        by_title.setdefault(keyer.title(s.title), []).append(s)
    contents = {keyer.content(s.source_text) for s in stored}
    found: dict[int, StoredRef] = {}
    for i, inc in enumerate(incoming):
        if inc.position >= before or keys.content[i] in contents:
            continue
        for s in by_title.get(keys.title[i], []):
            found.setdefault(s.index, s)
    return [found[i] for i in sorted(found)]


def plan_append(stored: list[StoredRef], incoming: list[Incoming], start: int | None = None,
                keyer: Keyer = DEFAULT_KEYER) -> AppendPlan:
    """Chương sẽ thêm vào cuối truyện. `start`: vị trí trong file do người dùng chọn."""
    stored = sorted(stored, key=lambda s: s.index)
    warnings: list[MergeWarning] = []
    keys = _incoming_keys(incoming, keyer)
    if start is not None:
        if not 1 <= start <= len(incoming):
            raise ValueError(f"Chương bắt đầu phải trong khoảng 1..{len(incoming)}.")
        return AppendPlan(None, False, [i for i in incoming if i.position >= start], warnings,
                          _differing(stored, incoming, keys, start, keyer))
    if not stored:
        return AppendPlan(None, False, list(incoming), warnings, [])

    for s in reversed(stored[-(ANCHOR_LOOKBACK + 1):]):
        anchor = _find_last(s, incoming, keys, keyer)
        if anchor:
            return AppendPlan(anchor, False, [i for i in incoming if i.position > anchor.position],
                              warnings, _differing(stored, incoming, keys, anchor.position, keyer))

    last_num = next((n for s in reversed(stored) if (n := title_number(s.title)) is not None),
                    None)
    first_num = next((n for i in incoming if (n := _number_of(i)) is not None), None)
    if last_num is not None and first_num is not None and first_num > last_num:
        if first_num > last_num + 1:
            lo, hi = last_num + 1, first_num - 1
            missing = str(lo) if lo == hi else f"{lo}–{hi}"
            warnings.append(MergeWarning(
                "gap", f"File bắt đầu từ chương {first_num}; thiếu chương {missing}.",
                {"from": lo, "to": hi},
            ))
        return AppendPlan(None, False, list(incoming), warnings, [])
    return AppendPlan(None, True, [], warnings, [])
