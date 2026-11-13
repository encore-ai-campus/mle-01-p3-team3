"""Streamlit 화면이 CareerGraph 그래프를 부르는 층(무거운 import 는 여기서만 한다).

Streamlit 은 사용자가 입력할 때마다 스크립트를 처음부터 다시 실행한다.
그래프, 레일, Jev 클라이언트는 비동기 객체를 품고 있어 매번 asyncio.run 으로 새 루프를 만들면
"attached to a different loop" 오류가 날 수 있다. 그래서 백그라운드 스레드에 이벤트 루프 하나를 띄워 두고,
그래프 실행은 모두 그 루프에 맡긴다. 화면 쪽은 큐로 진행 상황을 받아 그린다.
"""
from __future__ import annotations

import asyncio
import queue
import sys
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from app.core.schemas import ChatContext  # noqa: E402
from app.graph.builder import build_app  # noqa: E402
from app.guards.rails import build_rails  # noqa: E402
from app.main import make_input  # noqa: E402

STREAM_TIMEOUT_SECONDS = 300


class AgentRunner:
    """그래프·레일·이벤트 루프를 한 번만 만들어 여러 대화가 함께 쓴다."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self._thread.start()
        self.rails = build_rails()
        # Streamlit Cloud 는 컨테이너가 다시 뜨면 파일이 사라지므로 대화 기억은 메모리에 둔다.
        self.app = build_app(checkpointer=InMemorySaver())

    def stream(
        self,
        question: str,
        thread_id: str,
        user_id: str | None,
    ) -> Iterator[tuple[str, Any]]:
        """("step", 노드 이름) 을 차례로 내보내고, 마지막에 ("final", 최종 State) 를 내보낸다.

        실행 중 예외가 나면 ("error", 예외) 를 내보낸다.
        """

        events: queue.Queue = queue.Queue()
        context = ChatContext(rails=self.rails, retriever=None, user_id=user_id)
        config = {"configurable": {"thread_id": thread_id}}

        async def produce() -> None:
            final_state: dict[str, Any] = {}
            try:
                async for mode, chunk in self.app.astream(
                    make_input(question),
                    config=config,
                    context=context,
                    stream_mode=["updates", "values"],
                ):
                    if mode == "updates":
                        for node_name in chunk:
                            events.put(("step", node_name))
                    else:
                        final_state = chunk
                events.put(("final", final_state))
            except Exception as exc:  # noqa: BLE001 - 화면에 오류 종류만 알린다
                events.put(("error", exc))
            finally:
                events.put(("done", None))

        asyncio.run_coroutine_threadsafe(produce(), self.loop)

        while True:
            kind, payload = events.get(timeout=STREAM_TIMEOUT_SECONDS)
            if kind == "done":
                return
            yield kind, payload
