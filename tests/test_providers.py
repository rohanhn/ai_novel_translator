"""Provider: lỗi phân loại, streaming, Gemini (fixture từ spike), anthropic/openai (client giả).

Không gọi mạng thật.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from novel_translator.config import DEFAULT_CHAIN, ChainStep, Settings, parse_chain
from novel_translator.domain.models import CompletionRequest
from novel_translator.domain.ports import (
    DailyQuotaError,
    LLMProvider,
    ProviderConfigError,
    ProviderError,
    RateQuotaError,
    RefusalError,
    TranslationError,
    TruncatedError,
)
from novel_translator.providers import available_providers, create_provider
from novel_translator.providers.echo import EchoProvider
from novel_translator.providers.gemini import (
    GeminiProvider,
    classify_api_error,
    next_pacific_midnight,
)

FIXTURES = Path(__file__).parent / "fixtures"
REQ = CompletionRequest(system="sys", user="dòng 1\ndòng 2\ndòng 3", model=None)


def _drain(it, exc: type[Exception]) -> list[str]:
    """Đọc luồng tới khi gặp lỗi `exc`; trả về các mẩu text đã nhận trước lỗi."""
    got: list[str] = []
    with pytest.raises(exc):
        for t in it:
            got.append(t)  # noqa: PERF402 - cần giữ phần đã nhận khi luồng ném lỗi
    return got


def _fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------- 3.1 lỗi phân loại + echo stream ----------


def test_error_categories_are_translation_errors():
    for cls, cat in [(RefusalError, "refusal"), (TruncatedError, "truncated"),
                     (ProviderError, "provider_error"), (ProviderConfigError, "config")]:
        assert issubclass(cls, TranslationError) and cls.category == cat
    assert RateQuotaError("x", retry_after=3).retry_after == 3
    reset = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert DailyQuotaError("x", reset_at=reset).reset_at == reset


def test_echo_streams_line_by_line_and_complete_joins():
    p = EchoProvider()
    assert isinstance(p, LLMProvider)
    assert list(p.stream(REQ)) == ["[VI] dòng 1\n", "dòng 2\n", "dòng 3"]
    res = p.complete(REQ)
    assert res.text == "[VI] dòng 1\ndòng 2\ndòng 3"
    assert (res.provider, res.model) == ("echo", "echo")


@pytest.mark.parametrize("err", [
    RefusalError("r"), TruncatedError("t"), RateQuotaError("q", 1.0),
    DailyQuotaError("d"), ProviderError("p"),
])
def test_echo_simulates_each_error_before_stream(err):
    p = EchoProvider(errors=[err, None])
    with pytest.raises(type(err)):
        p.stream(REQ)
    assert p.complete(REQ).text.startswith("[VI]")  # lần gọi kế tiếp thành công


def test_echo_midstream_and_end_errors():
    got = _drain(EchoProvider(midstream_error=ProviderError("đứt")).stream(REQ), ProviderError)
    assert got == ["[VI] dòng 1\n"]
    got = _drain(EchoProvider(end_error=TruncatedError("cắt")).stream(REQ), TruncatedError)
    assert len(got) == 3


# ---------- 3.2 Gemini ----------


class _FakeModels:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def generate_content_stream(self, model, contents, config):
        self.calls.append((model, contents, config))
        if isinstance(self.result, Exception):
            raise self.result
        return iter(self.result)


def _gemini(result) -> tuple[GeminiProvider, _FakeModels]:
    models = _FakeModels(result)
    return GeminiProvider(api_key="unused", client=SimpleNamespace(models=models)), models


def _chunks_from_fixture(name: str):
    out = []
    for c in _fixture(name):
        reason = c["finish_reason"].rsplit(".", 1)[-1] if c["finish_reason"] else None
        out.append(SimpleNamespace(
            text=c["text"], prompt_feedback=None,
            candidates=[SimpleNamespace(finish_reason=reason, content=None)],
        ))
    return out


def _api_error(fixture: str):
    from google.genai import errors

    d = _fixture(fixture)
    return errors.APIError(d["code"], d["details"])


def test_gemini_streams_text_from_fixture():
    p, models = _gemini(_chunks_from_fixture("gemini_stream/ok_three_sections.json"))
    req = CompletionRequest(system="hướng dẫn", user="原文", model="gemini-3.5-flash-lite")
    text = "".join(p.stream(req))
    assert text.startswith("<<TITLE>>") and "<<BODY>>" in text and "<<NAMES>>" in text
    model, contents, config = models.calls[0]
    assert (model, contents) == ("gemini-3.5-flash-lite", "原文")
    assert config.system_instruction == "hướng dẫn"
    assert config.thinking_config.thinking_level.name.lower() == "low"


def test_gemini_default_model():
    p, models = _gemini(_chunks_from_fixture("gemini_stream/ok_three_sections.json"))
    p.complete(CompletionRequest(system="", user="x"))
    assert models.calls[0][0] == "gemini-3.5-flash"


def test_gemini_max_tokens_is_truncated_after_text():
    p, _ = _gemini(_chunks_from_fixture("gemini_stream/max_tokens.json"))
    got = _drain(p.stream(REQ), TruncatedError)
    assert "".join(got)  # phần text trước đó vẫn được phát


def test_gemini_safety_finish_is_refusal():
    chunk = SimpleNamespace(text="", prompt_feedback=None,
                            candidates=[SimpleNamespace(finish_reason="SAFETY", content=None)])
    p, _ = _gemini([chunk])
    with pytest.raises(RefusalError):
        list(p.stream(REQ))


def test_gemini_prompt_blocked_is_refusal():
    chunk = SimpleNamespace(text="", candidates=[],
                            prompt_feedback=SimpleNamespace(block_reason="PROHIBITED_CONTENT"))
    p, _ = _gemini([chunk])
    with pytest.raises(RefusalError, match="PROHIBITED_CONTENT"):
        list(p.stream(REQ))


def test_gemini_daily_quota_from_real_429_fixture():
    # Fixture thật có cả PerDay, PerMinute và RetryInfo → phải là quota NGÀY.
    p, _ = _gemini(_api_error("gemini_errors/daily_quota_429.json"))
    with pytest.raises(DailyQuotaError) as ei:
        list(p.stream(REQ))
    reset = ei.value.reset_at
    assert reset is not None and reset > datetime.now(timezone.utc)


def test_gemini_rate_quota_uses_retry_info():
    # Chưa tái hiện được 429 chỉ-theo-phút; dựng từ fixture thật, bỏ các violation PerDay.
    d = _fixture("gemini_errors/daily_quota_429.json")
    details = d["details"]["error"]["details"]
    for item in details:
        if item["@type"].endswith("QuotaFailure"):
            item["violations"] = [v for v in item["violations"] if "PerDay" not in v["quotaId"]]
        if item["@type"].endswith("RetryInfo"):
            item["retryDelay"] = "17s"
    err = classify_api_error(429, "RESOURCE_EXHAUSTED", d["message"], d["details"])
    assert isinstance(err, RateQuotaError) and err.retry_after == 17.0


def test_gemini_unclassifiable_429_defaults_to_rate():
    err = classify_api_error(429, "RESOURCE_EXHAUSTED", "busy", {"error": {}})
    assert isinstance(err, RateQuotaError) and err.retry_after is None


def test_gemini_retired_model_is_provider_error():
    p, _ = _gemini(_api_error("gemini_errors/model_retired_404.json"))
    with pytest.raises(ProviderError, match="NT_CHAIN") as ei:
        list(p.stream(REQ))
    assert not isinstance(ei.value, (RateQuotaError, DailyQuotaError))


def test_gemini_network_error_is_provider_error():
    p, _ = _gemini(httpx.ReadTimeout("timed out"))
    with pytest.raises(ProviderError, match="ReadTimeout"):
        list(p.stream(REQ))


def test_gemini_error_during_iteration_is_classified():
    def gen():
        yield SimpleNamespace(text="phần đầu", prompt_feedback=None, candidates=[])
        raise httpx.RemoteProtocolError("peer closed")

    p, _ = _gemini(gen())
    assert _drain(p.stream(REQ), ProviderError) == ["phần đầu"]


def test_next_pacific_midnight():
    # 2026-11-09 18:00 UTC = 10:00 PST → reset 2026-11-10 00:00 PST = 08:00 UTC
    now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
    assert next_pacific_midnight(now) == datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    # mùa hè (PDT, UTC-7)
    now = datetime(2026, 7, 1, 6, 59, tzinfo=timezone.utc)  # 23:59 PDT 30/6
    assert next_pacific_midnight(now) == datetime(2026, 7, 1, 7, 0, tzinfo=timezone.utc)


# ---------- 3.3 anthropic / openai_compat với client giả ----------


def _resp(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {},
                          request=httpx.Request("POST", "https://example.invalid"))


class _FakeAnthropicStream:
    def __init__(self, texts, stop_reason="end_turn", error=None):
        self.text_stream = iter(texts)
        self._stop, self._error = stop_reason, error

    def __enter__(self):
        if self._error:
            raise self._error
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return SimpleNamespace(stop_reason=self._stop, model="claude-x",
                               usage=SimpleNamespace(input_tokens=5, output_tokens=7))


def _anthropic(stream: _FakeAnthropicStream):
    pytest.importorskip("anthropic")
    from novel_translator.providers.anthropic_provider import AnthropicProvider

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(
        stream=lambda **kw: stream)))
    return AnthropicProvider(client=client)


def test_anthropic_stream_and_complete():
    p = _anthropic(_FakeAnthropicStream(["Xin ", "chào"]))
    assert list(p.stream(REQ)) == ["Xin ", "chào"]
    p = _anthropic(_FakeAnthropicStream(["Xin ", "chào"]))
    res = p.complete(REQ)
    assert (res.text, res.model, res.output_tokens) == ("Xin chào", "claude-x", 7)


@pytest.mark.parametrize("stop,exc", [("refusal", RefusalError), ("max_tokens", TruncatedError)])
def test_anthropic_stop_reasons(stop, exc):
    with pytest.raises(exc):
        list(_anthropic(_FakeAnthropicStream(["a"], stop_reason=stop)).stream(REQ))


def test_anthropic_rate_limit_and_other_errors():
    anthropic = pytest.importorskip("anthropic")
    rl = anthropic.RateLimitError("slow down", response=_resp(429, {"retry-after": "7"}), body=None)
    with pytest.raises(RateQuotaError) as ei:
        list(_anthropic(_FakeAnthropicStream([], error=rl)).stream(REQ))
    assert ei.value.retry_after == 7.0
    bad = anthropic.BadRequestError("bad", response=_resp(400), body=None)
    with pytest.raises(ProviderError):
        list(_anthropic(_FakeAnthropicStream([], error=bad)).stream(REQ))


def _oa_chunk(content=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=content), finish_reason=finish)])


def _openai(result):
    pytest.importorskip("openai")
    from novel_translator.providers.openai_compat import OpenAICompatProvider

    def create(**kw):
        assert kw["stream"] is True
        if isinstance(result, Exception):
            raise result
        return iter(result)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAICompatProvider(name="ollama", client=client)


def test_openai_stream_and_finish_reasons():
    p = _openai([_oa_chunk("Xin "), _oa_chunk("chào"), _oa_chunk(None, "stop")])
    assert p.complete(REQ).text == "Xin chào"
    with pytest.raises(TruncatedError):
        list(_openai([_oa_chunk("a"), _oa_chunk(None, "length")]).stream(REQ))
    with pytest.raises(RefusalError):
        list(_openai([_oa_chunk(None, "content_filter")]).stream(REQ))


def test_openai_error_classification():
    openai = pytest.importorskip("openai")
    rl = openai.RateLimitError("slow", response=_resp(429, {"retry-after": "3"}), body=None)
    with pytest.raises(RateQuotaError) as ei:
        _openai(rl).stream(REQ)
    assert ei.value.retry_after == 3.0
    quota = openai.RateLimitError("no quota", response=_resp(429),
                                  body={"code": "insufficient_quota"})
    with pytest.raises(DailyQuotaError):
        _openai(quota).stream(REQ)
    with pytest.raises(ProviderError):
        _openai(openai.APIConnectionError(request=httpx.Request("POST", "http://x"))).stream(REQ)


# ---------- 3.4 đăng ký + cấu hình ----------


def test_gemini_registered():
    assert "gemini" in available_providers()


def test_missing_api_key_names_variable(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match="GEMINI_API_KEY"):
        create_provider("gemini", Settings(_env_file=None))


def test_api_key_never_in_settings_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AQ.super-secret-value")
    s = Settings(_env_file=None)
    assert "super-secret-value" not in repr(s) and "super-secret-value" not in str(s)
    assert isinstance(create_provider("gemini", s), GeminiProvider)


def test_default_chain(monkeypatch):
    monkeypatch.delenv("NT_CHAIN", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    s = Settings(_env_file=None)
    assert s.chain == DEFAULT_CHAIN
    assert s.chain_steps() == [ChainStep("gemini", "gemini-3.5-flash"),
                               ChainStep("gemini", "gemini-3.5-flash-lite")]


def test_parse_chain_errors():
    assert parse_chain(" a:m1 , b:m2 ") == [ChainStep("a", "m1"), ChainStep("b", "m2")]
    for bad in ("", "gemini", "gemini:", ":m"):
        with pytest.raises(ValueError, match="NT_CHAIN"):
            parse_chain(bad)
