from __future__ import annotations

import time
from collections.abc import Iterable, Iterator

from ..domain.models import CompletionRequest
from ..domain.ports import StreamingProvider, TranslationError


class EchoProvider(StreamingProvider):
    """Provider giả cho test/dev: trả lại nguyên văn input (tiền tố `[VI] `), không gọi mạng.

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

    def stream(self, request: CompletionRequest) -> Iterator[str]:
        self.calls.append(request)
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        return self._lines(request)

    def _lines(self, request: CompletionRequest) -> Iterator[str]:
        lines = f"[VI] {request.user}".splitlines(keepends=True)
        for i, line in enumerate(lines):
            if self.delay:
                time.sleep(self.delay)
            yield line
            if i == 0 and self.midstream_error is not None:
                raise self.midstream_error
        if self.end_error is not None:
            raise self.end_error
