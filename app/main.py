"""Supervisor-Worker CareerGraph를 실행하는 간단한 CLI."""

import argparse
import asyncio
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import CHECKPOINT_PATH
from app.core.schemas import ChatContext
from app.graph.builder import build_app
from app.graph.state import empty_turn
from app.guards.rails import build_rails

def parse_args() -> argparse.Namespace:
    """CLI 인자를 읽는다."""

    parser = argparse.ArgumentParser(description="CareerGraph Agent CLI")
    parser.add_argument("--user", default=None, help="사용자 ID")
    parser.add_argument("--thread", default=None, help="대화 thread ID")
    return parser.parse_args()


def make_input(question: str) -> dict:
    """사용자 질문을 AgentState 입력 형태로 만든다."""

    state = empty_turn()
    # messages는 checkpointer의 기존 대화에 add_messages로 누적한다.
    # 나머지 필드는 empty_turn() 값으로 이번 질문을 새로 시작한다.
    state["question"] = question
    state["messages"] = [
        {
            "role": "user",
            "content": question,
        }
    ]
    return state


async def run_chat(user_id: str | None, thread_id: str) -> None:
    """질문을 받아 Supervisor-Worker 그래프를 반복 실행한다."""

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    context = ChatContext(retriever=None, user_id=user_id)
    config = {"configurable": {"thread_id": thread_id}}

    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        checkpointer = AsyncSqliteSaver(connection)
        app = build_app(checkpointer=checkpointer)

        print(f"CareerGraph Agent 시작: user={user_id}, thread={thread_id}")
        print("종료하려면 exit를 입력하세요.")

        while True:
            question = input("\n사용자: ").strip()
            if question.lower() == "exit":
                break
            if not question:
                continue

            result = await app.ainvoke(
                make_input(question),
                config=config,
                context=context,
            )

            print("에이전트:", result.get("final_response"))
            print("상태:", result.get("status"))
            print("검색 방식:", result.get("search_mode"))
            print("워커 흐름:", " → ".join(result.get("worker_trace", [])))


def main() -> None:
    """CLI 실행 진입점."""

    args = parse_args()
    thread_id = args.thread or str(uuid4())
    asyncio.run(run_chat(args.user, thread_id))


if __name__ == "__main__":
    main()
