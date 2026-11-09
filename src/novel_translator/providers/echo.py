from __future__ import annotations

from ..domain.models import CompletionRequest, CompletionResult


class EchoProvider:
    """Provider giả cho test/dev: trả lại nguyên văn đoạn nguồn, không gọi mạng."""

    name = "echo"
    default_model = "echo"

    def __init__(self) -> None:
        self.calls: list[CompletionRequest] = []

    def complete(self, request: CompletionRequest) -> CompletionResult:
        self.calls.append(request)
        return CompletionResult(text=f"[VI] {request.user}", provider=self.name, model="echo")
