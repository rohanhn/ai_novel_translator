from __future__ import annotations

import re
import time
from collections.abc import Iterable, Iterator

from ..domain.models import CompletionRequest
from ..domain.ports import StreamingProvider, TranslationError

_MARKER = re.compile(r"^\s*<<\s*[A-Z]+\s*>>\s*$")


class EchoProvider(StreamingProvider):
    """Provider giả cho test/dev: trả lại nguyên văn input, không gọi mạng. Mỗi dòng nội dung
    có tiền tố `[VI] `; dòng dấu mốc (`<<TITLE>>`, `<<BODY>>`...) và dòng trống giữ nguyên, nên
    output đúng định dạng 3 phần mà pipeline yêu cầu.

    - `stream()` phát từng dòng, mỗi dòng cách nhau `delay` giây.
    - `errors`: hàng đợi lỗi cho các lần gọi kế tiếp; phần tử `None` = lần gọi đó thành công.
      Lỗi được ném trước khi phát text (giống 429 của API thật).
    - `midstream_error`: ném sau dòng đầu tiên (giả lập lỗi khi stream đã chạy một phần).
    - `end_error`: ném sau dòng cuối (giả lập truncated/refusal phát hiện ở cuối luồng).
    """

    name = "echo"
    default_model = "echo"

    def __init__(
        self,
        delay: float = 0.0,
        errors: Iterable[TranslationError | None] = (),
        midstream_error: TranslationError | None = None,
        end_error: TranslationError | None = None,
        name: str = "echo",
    ) -> None:
        self.name = name
        self.delay = delay
        self.errors = list(errors)
        self.midstream_error = midstream_error
        self.end_error = end_error
        self.calls = []

    def stream(self, request: CompletionRequest, policy=None, on_event=None) -> Iterator[str]:
        self.calls.append(request)
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        return self._lines(request)

    def _lines(self, request: CompletionRequest) -> Iterator[str]:
        lines = [
            line if not line.strip() or _MARKER.match(line) else f"[VI] {line}"
            for line in request.user.splitlines(keepends=True)
        ]
        for i, line in enumerate(lines):
            if self.delay:
                time.sleep(self.delay)
            yield line
            if i == 0 and self.midstream_error is not None:
                raise self.midstream_error
        if self.end_error is not None:
            raise self.end_error
