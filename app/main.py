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
    parser.add_argument(
        "--debug",
        action="store_true",
        help="가드레일 판정, 회원 프로필 조회, 검색 근거까지 출력한다",
    )
    return parser.parse_args()


def print_debug(result: dict) -> None:
    """한 턴의 가드레일·프로필·검색 결과를 사람이 읽기 쉽게 출력한다."""

    print("  ┌─ [입력 가드]", result.get("input_guard_status"),
          "| 규칙:", result.get("input_guard_rule"),
          "| 오류:", result.get("input_guard_error"))

    profile = result.get("user_profile") or {}
    print("  ├─ [프로필 필요]", result.get("profile_required"),
          "| 조회함:", result.get("profile_loaded"))
    if profile:
        print("  │    현재:", profile.get("current_job"), "/", profile.get("current_major"),
              "/", profile.get("current_certificate"))
        print("  │    목표:", profile.get("target_job"), "/", profile.get("target_major"),
              "/", profile.get("target_certificate"))

    evidence = result.get("evidence") or []
    print("  ├─ [검색]", result.get("search_mode"), "| 근거", len(evidence), "개",
          "| 재검색:", result.get("retry_count"))
    for item in evidence[:5]:
        content = str(item.get("content") or "").replace("\n", " ")
        print(f"  │    {item.get('evidence_id')}: {content[:60]}")
    if len(evidence) > 5:
        print(f"  │    … 외 {len(evidence) - 5}개")

    verification = result.get("verification_result") or {}
    print("  ├─ [검증]", verification.get("status"), "|", verification.get("feedback"))
    print("  └─ [출력 가드]", result.get("output_guard_status"),
          "| 규칙:", result.get("output_guard_rule"),
          "| 오류:", result.get("output_guard_error"))


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


async def run_chat(user_id: str | None, thread_id: str, debug: bool = False) -> None:
    """질문을 받아 Supervisor-Worker 그래프를 반복 실행한다."""

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 입력·출력 가드 노드가 runtime.context.rails 로 판정 객체를 읽는다.
    context = ChatContext(rails=build_rails(), retriever=None, user_id=user_id)
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
            if debug:
                print_debug(result)


def main() -> None:
    """CLI 실행 진입점."""

    args = parse_args()
    thread_id = args.thread or str(uuid4())
    asyncio.run(run_chat(args.user, thread_id, debug=args.debug))


if __name__ == "__main__":
    main()
