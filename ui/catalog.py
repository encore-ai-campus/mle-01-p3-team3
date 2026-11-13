"""화면에서 바로 쓰는 가벼운 값과 함수(그래프·레일을 불러오지 않는다).

회원 목록과 커리어 카드는 SQLite 만 읽으므로, 무거운 엔진(backend.py)이 준비되기 전에도 화면을 그릴 수 있다.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.tools.profile import CAREER_FIELDS, load_own_career  # noqa: E402

DEMO_DB_PATH = PROJECT_DIR / "data" / "careergraph_demo.db"

# 화면에 보여 줄 노드 이름과 설명. supervisor 는 경로를 고르기만 하므로 빼고 그린다.
STEP_LABELS: dict[str, tuple[str, str]] = {
    "input_guard": ("🛡️", "질문 안전 검사"),
    "profile_check": ("🧭", "회원 정보가 필요한지 판단"),
    "profile": ("🗂️", "내 커리어 불러오기"),
    "search": ("🕸️", "커리어 그래프 검색"),
    "reasoner": ("✍️", "답변 작성"),
    "verifier": ("🔎", "근거와 대조"),
    "output": ("📦", "답변 정리"),
    "abstain": ("🤔", "답변 보류"),
    "output_guard": ("🛡️", "답변 안전 검사"),
}

GUARD_LABELS = {
    "passed": "✅ 통과",
    "blocked": "⛔ 차단",
    "modified": "✏️ 수정",
    "error": "⚠️ 오류",
}

VERIFY_LABELS = {
    "supported": "✅ 근거 일치",
    "insufficient": "🤔 근거 부족",
    "conflict": "⚠️ 근거 충돌",
    "error": "⚠️ 오류",
}

SEARCH_LABELS = {
    "vector": "업무 설명 검색",
    "graph": "관계 그래프 검색",
    "hybrid": "설명 + 그래프",
}


def list_demo_members() -> list[dict[str, str]]:
    """시연용 가상 회원 목록(id, 표시 이름)을 돌려준다."""

    uri = DEMO_DB_PATH.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        rows = connection.execute(
            "SELECT user_id, display_name FROM users ORDER BY user_id"
        ).fetchall()
    return [{"user_id": user_id, "display_name": name} for user_id, name in rows]


def load_member_career(user_id: str | None) -> dict[str, str]:
    """사이드바 카드에 보여 줄 현재·목표 커리어만 돌려준다(연락처·주소는 넣지 않는다)."""

    profile = load_own_career(user_id)
    return {key: profile[key] for key in CAREER_FIELDS if profile.get(key)}


def summarize_turn(state: dict[str, Any]) -> dict[str, Any]:
    """한 턴의 최종 State 에서 화면이 쓰는 값만 꺼낸다."""

    evidence = [
        {
            "근거 ID": item.get("evidence_id"),
            "내용": str(item.get("content") or ""),
            "출처": "회원 DB" if item.get("source") == "sqlite_profile" else "커리어 그래프",
        }
        for item in state.get("evidence") or []
        # 회원 DB 근거는 커리어 필드만 보여 준다(연락처·주소는 화면에 띄우지 않는다).
        if item.get("source") != "sqlite_profile"
        or (item.get("metadata") or {}).get("source_field") in CAREER_FIELDS
    ]
    verification = state.get("verification_result") or {}
    return {
        "answer": state.get("final_response") or "",
        "status": state.get("status"),
        "trace": [name for name in state.get("worker_trace", []) if name in STEP_LABELS],
        "input_guard": state.get("input_guard_status"),
        "input_rule": state.get("input_guard_rule"),
        "output_guard": state.get("output_guard_status"),
        "output_rule": state.get("output_guard_rule"),
        "profile_used": bool(state.get("profile_loaded")),
        "search_mode": state.get("search_mode"),
        "retry_count": state.get("retry_count", 0),
        "verification": verification.get("status"),
        "evidence": evidence,
    }
