"""CRAG(Corrective RAG) 노드: 검색 근거 평가(grade)와 검색어 재작성(rewrite).

흐름: search → grade → supervisor
- correct: 근거가 충분하면 reasoner로 간다.
- ambiguous/incorrect: 재작성 여유가 있으면 rewrite → search(이전 근거와 합침) → grade 로 다시 평가한다.
- 한도를 다 쓰면 남은 근거로 부분 답변(partial)을 만들고, 근거가 없으면 abstain 한다.
라우팅 규칙은 supervisor_node 가 가진다. 이 모듈의 노드는 State 갱신값만 반환한다.
"""

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.core.prompts import CRAG_GRADE_PROMPT, CRAG_REWRITE_PROMPT
from app.graph.state import AgentState

logger = logging.getLogger(__name__)

# 검색어 재작성 한도. 재작성 뒤에도 부족하면 남은 근거로 부분 답변한다.
MAX_REWRITES = 1
# 평가 모델에 넘기는 근거 본문 길이 상한(업무 설명이 긴 근거의 토큰을 줄인다)
GRADE_CONTENT_LIMIT = 500
PROFILE_SOURCE = "sqlite_profile"


class RetrievalReview(BaseModel):
    """근거 평가 모델의 구조화 출력."""

    useful_ids: list[str] = Field(description="요청 항목 중 하나에라도 도움이 되는 근거 ID. 대괄호 제외. 없으면 빈 목록")
    sufficient: bool = Field(description="선택한 근거를 합쳐 질문의 모든 요청 항목을 직접 확인할 수 있는지")
    missing_info: str = Field(description="아직 확인하지 못한 요청 항목. 충분하면 빈 문자열")


def is_profile_evidence(item: dict[str, Any]) -> bool:
    """SQLite 본인 프로필 근거인지 확인한다. 프로필 근거는 평가로 버리지 않는다."""

    return item.get("source") == PROFILE_SOURCE


def evidence_key(item: dict[str, Any]) -> str:
    """근거를 구분하는 키. evidence_id가 없으면 출처와 본문으로 구분한다."""

    return str(item.get("evidence_id") or f"{item.get('source')}:{item.get('content')}")


def merge_evidence(kept: list[dict[str, Any]], found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """이전에 선택한 근거와 새 검색 결과를 ID 기준으로 합친다. 같은 ID는 새 결과로 덮어쓴다."""

    merged = {evidence_key(item): item for item in kept}
    merged.update({evidence_key(item): item for item in found})
    return list(merged.values())


def merge_graph_paths(kept: list[list[str]], found: list[list[str]]) -> list[list[str]]:
    """그래프 경로 목록을 순서를 유지하며 중복 없이 합친다."""

    seen: dict[tuple, list[str]] = {}
    for path in [*kept, *found]:
        seen.setdefault(tuple(str(node) for node in path), path)
    return list(seen.values())


def format_evidence(evidence: list[dict[str, Any]]) -> str:
    """평가 모델에 넘길 근거 문자열을 만든다. [ID] (직업 | 필드) 본문 형식."""

    blocks = []
    for item in evidence:
        metadata = item.get("metadata") or {}
        label = " | ".join(
            str(value) for value in (metadata.get("job_name"), metadata.get("source_field")) if value
        )
        content = str(item.get("content") or "")[:GRADE_CONTENT_LIMIT]
        prefix = f"[{item.get('evidence_id')}]" + (f" ({label})" if label else "")
        blocks.append(f"{prefix}\n{content}")
    return "\n\n".join(blocks)


def get_grade_chain():
    from app.core.config import llm

    return CRAG_GRADE_PROMPT | llm.with_structured_output(RetrievalReview)


def get_rewrite_chain():
    from app.core.config import llm

    return CRAG_REWRITE_PROMPT | llm


def resolve_id(value: str, known_ids: set[str]) -> set[str]:
    """모델이 고른 ID 하나를 실제 후보 ID 집합으로 바꾼다. 후보에 없으면 빈 집합.

    모델이 'CAREER0505:work'를 'CAREER0505'처럼 콜론 앞 직업 코드만 반환하는 경우가 있어,
    그 코드로 시작하는 후보 ID를 모두 선택한 것으로 본다.
    """

    cleaned = value.strip("[] \t\r\n")
    if cleaned in known_ids:
        return {cleaned}
    return {known for known in known_ids if known.split(":", 1)[0] == cleaned}


async def grade_evidence(question: str, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str, str]:
    """근거를 평가해 (선택 근거, 판정, 부족한 정보)를 반환한다."""

    if not candidates:
        return [], "incorrect", "검색된 근거가 없습니다."

    try:
        review: RetrievalReview = await get_grade_chain().ainvoke({
            "question": question,
            "context": format_evidence(candidates),
        })
    except Exception as exc:
        # 평가가 실패하면 근거를 버리지 않고 기존 흐름(평가 없이 답변)으로 진행한다.
        logger.warning("CRAG grade failed: %s", type(exc).__name__)
        return candidates, "correct", ""

    known_ids = {str(item.get("evidence_id")) for item in candidates}
    selected_ids: set[str] = set()
    # 후보에 없는 ID가 섞이면 모델 판정을 믿을 수 없으므로 충분 판정을 막는다.
    valid_selection = True
    for value in review.useful_ids:
        matched = resolve_id(value, known_ids)
        selected_ids |= matched
        valid_selection = valid_selection and bool(matched)
    kept = [
        item for item in candidates
        if str(item.get("evidence_id")) in selected_ids or is_profile_evidence(item)
    ]

    missing_info = review.missing_info.strip()
    if not kept:
        return [], "incorrect", missing_info or "질문에 맞는 근거를 찾지 못했습니다."
    if review.sufficient and valid_selection:
        return kept, "correct", ""
    if not valid_selection:
        missing_info = "평가 결과에 후보 밖 근거 ID가 있어 충분성을 확정할 수 없습니다. " + missing_info
    return kept, "ambiguous", missing_info or "질문의 일부를 현재 근거로 확인하지 못했습니다."


async def grade_node(state: AgentState) -> dict[str, Any]:
    """[노드] 검색 근거의 관련성·충분성을 평가하고 쓸 근거만 남긴다."""

    # 검색 서비스 오류는 Supervisor가 오류 안내로 끝낸다. 남은 이전 근거로 평가 모델을 부르지 않는다.
    if state.get("error"):
        return {"worker_trace": [*state.get("worker_trace", []), "grade"]}

    candidates = state.get("evidence", [])
    kept, decision, missing_info = await grade_evidence(state["question"], candidates)

    entry = {
        "search_query": state.get("search_query") or state["question"],
        "search_mode": state.get("search_mode"),
        "candidate_ids": [item.get("evidence_id") for item in candidates],
        "kept_ids": [item.get("evidence_id") for item in kept],
        "decision": decision,
        "missing_info": missing_info,
    }
    return {
        "evidence": kept,
        "retrieval_decision": decision,
        "missing_info": missing_info,
        "search_history": [*state.get("search_history", []), entry],
        "worker_trace": [*state.get("worker_trace", []), "grade"],
    }


async def rewrite_node(state: AgentState) -> dict[str, Any]:
    """[노드] 부족한 정보를 찾도록 검색어를 다시 만든다. 원질문(question)은 바꾸지 않는다."""

    question = state["question"]
    current_query = state.get("search_query") or question
    feedback = state.get("missing_info") or state.get("verification_feedback") or ""

    try:
        response = await get_rewrite_chain().ainvoke({
            "question": question,
            "search_query": current_query,
            "feedback": feedback,
        })
        content = response.content
        if not isinstance(content, str):
            # Responses API 형식은 내용 블록 목록으로 온다.
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        query = content.strip()
    except Exception as exc:
        logger.warning("CRAG rewrite failed: %s", type(exc).__name__)
        query = ""

    return {
        "search_query": query or current_query,
        "rewrite_count": state.get("rewrite_count", 0) + 1,
        "worker": "search",
        "worker_trace": [*state.get("worker_trace", []), "rewrite"],
    }
