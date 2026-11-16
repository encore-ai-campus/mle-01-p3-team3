"""Langfuse 트레이싱: 질문 한 턴의 그래프 실행(노드, LLM 호출)과 가드레일 판정(Jev)을 한 트레이스로 남긴다.

LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL(또는 LANGFUSE_HOST)이 .env 나 환경 변수에 있으면 켜지고,
없으면 모든 함수가 아무 일도 하지 않는다(앱은 트레이싱 없이 그대로 돈다).

- trace_turn(): 턴 하나를 루트 관찰로 열고 LangChain 콜백(노드·LLM 호출)을 돌려준다. session = 대화 ID, user = 선택한 회원 ID
- traced(): 가드레일 판정 같은 함수를 하위 관찰로 남기는 데코레이터
- 개인정보 보호: 기록되는 모든 입력·출력은 주민번호·전화·이메일·주소를 가린 뒤 전송한다(mask_pii)
"""
from __future__ import annotations

import functools
import inspect
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from app.core.config import settings

logger = logging.getLogger(__name__)


class _OtelDisabledNotice(logging.Filter):
    """Langfuse 가 환경 변수 OTEL_SDK_DISABLED 를 보고 내는 경고를 숨긴다. 전용 TracerProvider 를 써서 실제로는 기록되므로 오해만 부른다."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "OTEL_SDK_DISABLED" not in record.getMessage()


logging.getLogger("langfuse").addFilter(_OtelDisabledNotice())

_client = None
_client_failed = False


def tracing_enabled() -> bool:
    """Langfuse 키 두 개가 모두 있으면 True."""
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def mask_trace_data(data: Any, **_: Any) -> Any:
    """Langfuse 로 보내는 모든 값에서 개인정보를 가린다(문자열이면 그대로, dict·list 는 안을 재귀로)."""
    from app.guards.validators import mask_pii

    if isinstance(data, str):
        return mask_pii(data)
    if isinstance(data, dict):
        return {key: mask_trace_data(value) for key, value in data.items()}
    if isinstance(data, (list, tuple)):
        return [mask_trace_data(value) for value in data]
    return data


def get_langfuse():
    """Langfuse 클라이언트를 한 번만 만들어 돌려준다. 꺼져 있거나 만들기에 실패하면 None."""
    global _client, _client_failed
    if _client is not None or _client_failed or not tracing_enabled():
        return _client
    try:
        import os

        from langfuse import Langfuse
        from opentelemetry.sdk.trace import TracerProvider

        # config.py 는 Guardrails AI 가 외부로 추적을 보내지 않게 OTEL_SDK_DISABLED 를 켜 둔다. 그 값이 켜져 있으면
        # OpenTelemetry 가 모든 추적을 버리므로 Langfuse 도 기록하지 못한다. 그래서 Langfuse 전용 TracerProvider 를 그 값을
        # 잠시 뺀 채로 만들어 넘긴다. 전역 설정은 그대로라 Guardrails AI 의 외부 추적은 계속 꺼져 있다.
        disabled = os.environ.pop("OTEL_SDK_DISABLED", None)
        try:
            provider = TracerProvider()
        finally:
            if disabled is not None:
                os.environ["OTEL_SDK_DISABLED"] = disabled

        _client = Langfuse(
            tracer_provider=provider,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key.get_secret_value(),
            base_url=settings.langfuse_base_url,
            mask=mask_trace_data,
            environment=settings.langfuse_environment,
        )
    except Exception as exc:  # noqa: BLE001 - 트레이싱 실패가 앱을 멈추면 안 된다
        _client_failed = True
        logger.warning("Langfuse 를 켜지 못했습니다(트레이싱 없이 계속): %s", type(exc).__name__)
    return _client


@dataclass
class TurnTrace:
    """trace_turn 이 돌려주는 값. callbacks 를 그래프 config 에 넣고, 끝나면 set_output 으로 최종 답을 남긴다."""

    callbacks: list = field(default_factory=list)
    _span: Any = None

    def set_output(self, output: Any, **metadata: Any) -> None:
        if self._span is None:
            return
        try:
            self._span.update(output=output, metadata=metadata or None)
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def trace_turn(question: str, thread_id: str, user_id: str | None) -> Iterator[TurnTrace]:
    """질문 한 턴을 Langfuse 트레이스 하나로 묶는다. 꺼져 있으면 빈 TurnTrace 를 돌려준다."""
    client = get_langfuse()
    if client is None:
        yield TurnTrace()
        return

    try:
        from langfuse import propagate_attributes
        from langfuse.langchain import CallbackHandler

        span_cm = client.start_as_current_observation(
            name="careergraph-turn", as_type="agent", input=question,
        )
        attrs_cm = propagate_attributes(
            session_id=thread_id,
            user_id=user_id or "guest",
            tags=["careergraph"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Langfuse 트레이스를 시작하지 못했습니다: %s", type(exc).__name__)
        yield TurnTrace()
        return

    with span_cm as span, attrs_cm:
        yield TurnTrace(callbacks=[CallbackHandler()], _span=span)


def flush_traces() -> None:
    """남은 트레이스를 전송한다. 짧게 끝나는 CLI 나 턴이 끝난 뒤에 부른다."""
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # noqa: BLE001
        pass


def traced(name: str, as_type: str = "span", capture_input: bool = True) -> Callable:
    """함수 호출(입력, 출력, 시간)을 현재 트레이스의 하위 관찰로 남기는 데코레이터. 트레이싱이 꺼져 있으면 그대로 실행한다."""

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any):
                if get_langfuse() is None:
                    return await func(*args, **kwargs)
                from langfuse import observe

                return await observe(name=name, as_type=as_type, capture_input=capture_input)(func)(*args, **kwargs)

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any):
            if get_langfuse() is None:
                return func(*args, **kwargs)
            from langfuse import observe

            return observe(name=name, as_type=as_type, capture_input=capture_input)(func)(*args, **kwargs)

        return sync_wrapper

    return decorator
