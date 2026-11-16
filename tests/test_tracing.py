"""Langfuse 트레이싱 설정 테스트 (Langfuse 서버에는 접속하지 않는다)."""
import asyncio

from app.core import tracing


def test_tracing_is_noop_without_keys(monkeypatch):
    monkeypatch.setattr(tracing.settings, "langfuse_public_key", None)
    monkeypatch.setattr(tracing.settings, "langfuse_secret_key", None)
    monkeypatch.setattr(tracing, "_client", None)

    assert tracing.tracing_enabled() is False
    assert tracing.get_langfuse() is None
    with tracing.trace_turn("질문", "thread-1", "U001") as trace:
        assert trace.callbacks == []
        trace.set_output("답")  # 꺼져 있어도 오류 없이 지나간다
    tracing.flush_traces()


def test_traced_runs_function_unchanged_when_disabled(monkeypatch):
    monkeypatch.setattr(tracing.settings, "langfuse_public_key", None)
    monkeypatch.setattr(tracing, "_client", None)

    @tracing.traced("async-fn", as_type="guardrail")
    async def double(value):
        return value * 2

    @tracing.traced("sync-fn")
    def triple(value):
        return value * 3

    assert asyncio.run(double(2)) == 4
    assert triple(2) == 6


def test_mask_removes_personal_data_recursively():
    data = {
        "question": "제 번호는 010-1234-5678 이고 메일은 a@b.com 이에요",
        "history": ["주소는 서울특별시 마포구 월드컵로 45 입니다"],
        "n": 3,
    }

    masked = tracing.mask_trace_data(data)

    assert "010-1234-5678" not in masked["question"] and "a@b.com" not in masked["question"]
    assert "[전화번호]" in masked["question"] and "[이메일]" in masked["question"]
    assert masked["history"] == ["주소는 [주소] 입니다"]
    assert masked["n"] == 3
