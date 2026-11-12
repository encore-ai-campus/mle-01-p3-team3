"""
실행: uv run -m app.main --user U0001              (새 대화)
      uv run -m app.main --user U0001 --thread ID  (앞 대화 이어 하기)
턴마다 루나의 답과 레일 기록 한 줄(막은 흐름, 경로, 뺀 문서)을 찍는다. exit 를 입력하면 끝난다.
"""
import argparse
import asyncio
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from careeragent.app.core.config import CHECKPOINT_PATH
from careeragent.app.graph.builder import build_app
from app.graph.chat import build_chat_context, send_message, summarize_turn


# [보조 함수] 레일 기록 한 줄
def trace_line(summary: dict) -> str:
    """턴 요약에서 경로, 막은 흐름과 규칙, 검색 문서, 뺀 문서를 한 줄로 돌려준다."""
    parts = ["경로 " + summary["route"]]
    if summary["blocked_by"] != "":
        parts.append(f"막음 {summary['blocked_by']} ({summary['rule_id']})")
    if summary["output_status"] == "modified":
        parts.append("출력 가림")
    if len(summary["retrieved_ids"]) > 0:
        parts.append("검색 " + ", ".join(summary["retrieved_ids"]))
    if len(summary["removed_doc_ids"]) > 0:
        parts.append("뺀 문서 " + ", ".join(summary["removed_doc_ids"]))
    return " | ".join(parts)


# [보조 함수] 명령줄 인자
def parse_args() -> argparse.Namespace:
    """--user(로그인한 사용자)와 --thread(이어 할 대화 ID) 인자를 읽어 돌려준다."""
    parser = argparse.ArgumentParser(description="챗봇 CLI")
    parser.add_argument("--user", default=None, help="로그인한 사용자 id. 없으면 로그인하지 않은 사용자")
    parser.add_argument("--thread", default=None, help="이어 할 대화 ID. 없으면 새 대화")
    return parser.parse_args()


# [실행 함수] 터미널 대화 반복
async def chat(user_id: str | None, thread_id: str) -> None:
    """한 대화 ID로 사용자 메시지를 받아 답을 찍는 일을 exit까지 되풀이한다."""
    context = build_chat_context(user_id)

    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))

        saved = await app.aget_state({"configurable": {"thread_id": thread_id}})
        if "messages" in saved.values:
            print(f"저장된 메시지 {len(saved.values['messages'])}개에 이어서 대화합니다.")

        while True:
            text = input("\n사용자> ").strip()
            if text == "exit":
                break
            if text == "":
                continue

            state = await send_message(app, thread_id, text, context)
            summary = summarize_turn(state)
            print("커리>", summary["answer"])
            print("  [레일]", trace_line(summary))


if __name__ == "__main__":
    args = parse_args()
    thread = args.thread or str(uuid4())
    print("로그인한 사용자:", args.user, "/ 대화 ID:", thread)
    print("끝내려면 exit 를 입력하세요.")
    asyncio.run(chat(args.user, thread))

    resume_command = f"uv run -m app.main --thread {thread}"
    if args.user is not None:
        resume_command = f"uv run -m app.main --user {args.user} --thread {thread}"
    print("\n이어서 하려면:", resume_command)
