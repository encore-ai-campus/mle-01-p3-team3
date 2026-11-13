"""Supervisor와 Worker 그래프의 노드를 작성하는  파일."""

from typing import Any, Literal

from langgraph.graph import END
from langgraph.types import Command

from app.agents.workers import create_workers
from app.core.prompts import WORKER_PROMPT_TEMPLATES
from app.graph.state import AgentState
from langgraph.runtime import Runtime
from app.core.schemas import ChatContext
from app.tools.profile import load_own_career, career_context, CAREER_FIELDS


WORKERS: dict[str, object] | None = None
MAX_RETRIES = 1
MAX_STEPS = 10


def append_worker_trace(state: AgentState, worker_name: str) -> list[str]:
    """현재 노드 이름을 실행 흐름에 추가한다."""

    return [*state.get("worker_trace", []), worker_name]


def get_workers() -> dict[str, object]:
    """create_agent로 만든 워커를 최초 한 번만 준비한다."""

    global WORKERS
    if WORKERS is None:
        WORKERS = create_workers()
    return WORKERS


def get_worker(worker_name: str) -> object:
    """이름으로 워커 하나를 찾아 반환한다."""

    workers = get_workers()
    if worker_name not in workers:
        raise ValueError(f"존재하지 않는 worker입니다: {worker_name}")
    return workers[worker_name]


def _legacy_build_worker_instruction(state: AgentState) -> str:
    """현재 상태를 워커에게 전달할 지시문으로 만든다."""

    return (
        f"질문: {state['question']}\n"
        f"검색 방식: {state.get('search_mode')}\n"
        f"검색 근거: {state.get('evidence', [])}\n"
        f"그래프 경로: {state.get('graph_paths', [])}\n"
        f"답변 초안: {state.get('answer_draft')}\n"
        f"주장: {state.get('claims', [])}\n"
        f"검증 피드백: {state.get('verification_feedback')}"
    )


def build_worker_instruction(state: AgentState, worker_name: str | None = None) -> str:
    """현재 질문과 최근 대화 기록을 워커 지시문으로 만든다."""

    messages = state.get("messages", [])[-6:]
    history = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        if isinstance(message, dict)
        else str(message)
        for message in messages
    )
    profile = state.get("user_profile", {})
    evidence = state.get("evidence", [])
    if worker_name == "search":
        profile = career_context(profile)
        evidence = [item for item in evidence if
                    item.get("source") != "sqlite_profile"
                    or item.get("metadata", {}).get("source_field") in CAREER_FIELDS]
    return (
        f"Question: {state['question']}\n"
        f"User profile: {profile}\n"
        "개인화 질문의 '내 현재 커리어'는 current_job/current_major/current_certificate를, "
        "'내 목표 커리어'는 target_job/target_major/target_certificate를 의미합니다. "
        "관련 직업 검색은 이 실제 직업·전공·자격을 대상으로 하며 '내정보'를 직업명으로 검색하지 마세요. "
        "목표 자격을 이미 보유한 자격으로 해석하지 마세요. 프로필도 제공된 근거 ID에 맞춰 인용하세요.\n"
        f"Recent conversation history:\n{history}\n"
        f"Search mode: {state.get('search_mode')}\n"
        f"Evidence: {evidence}\n"
        f"Graph paths: {state.get('graph_paths', [])}\n"
        f"Answer draft: {state.get('answer_draft')}\n"
        f"Claims: {state.get('claims', [])}\n"
        f"Claim evidence IDs: {state.get('claim_evidence_ids', [])}\n"
        f"Verification feedback: {state.get('verification_feedback')}"
    )


def build_worker_messages(state: AgentState, worker_name: str) -> list:
    """MessagesPlaceholder에 최근 대화를 넣은 워커 입력을 만든다."""

    prompt = WORKER_PROMPT_TEMPLATES[worker_name]
    rendered_messages = prompt.invoke({
        "messages": state.get("messages", [])[-6:],
        "instruction": build_worker_instruction(state, worker_name),
    }).messages
    # create_agent가 system_prompt를 별도로 넣으므로 placeholder가 만든
    # 중복 SystemMessage는 제거하고 대화 메시지만 전달한다.
    return rendered_messages[1:]


def bind_claim_evidence(
    state: AgentState,
    claims: list[dict[str, Any]],
    claim_evidence_ids: list[list[str]],
) -> list[list[str]]:
    """Reasoner가 빠뜨린 인용을 현재 검색 근거에 한해 보정한다."""

    available_ids = [
        evidence.get("evidence_id")
        for evidence in state.get("evidence", [])
        if evidence.get("evidence_id")
    ]
    bound: list[list[str]] = []
    for index, claim in enumerate(claims):
        ids = claim_evidence_ids[index] if index < len(claim_evidence_ids) else []
        if not ids and isinstance(claim, dict):
            ids = claim.get("evidence_ids", []) or []
        if not ids and available_ids:
            ids = [available_ids[0]]
        bound.append(list(dict.fromkeys(ids)))
    return bound


def make_abstain_update(state: AgentState) -> dict[str, Any]:
    """보류 응답도 대화 기록에 남긴다."""
    answer = "현재 자료만으로는 답변을 확정하기 어렵습니다."
    return {
        "status": "abstain",
        "worker": "end",
        "worker_trace": append_worker_trace(state, "abstain"),
        "final_response": answer,
        "messages": [{"role": "assistant", "content": answer}],
        "error": state.get("error"),
    }


def profile_node(state: AgentState, runtime: Runtime[ChatContext]) -> dict[str, Any]:
    """선택한 회원 ID로 개인정보와 현재·목표 커리어를 읽는다."""
    profile = load_own_career(runtime.context.user_id)
    return {
        "user_profile": profile,
        "profile_loaded": True,
        "worker_trace": append_worker_trace(state, "profile"),
    }


async def profile_check_node(state: AgentState) -> dict[str, Any]:
    """Jev 판정 결과를 State에 저장한다. 다음 노드는 조건부 엣지가 선택한다."""
    from app.router.profile_router import classify_profile_need

    trace = append_worker_trace(state, "profile_check")
    try:
        required = await classify_profile_need(state)
    except RuntimeError as exc:
        return {
            "profile_required": None,
            "error": str(exc),
            "status": "error",
            "worker_trace": trace,
        }
    return {"profile_required": required, "error": None, "worker_trace": trace}


def supervisor_node(
    state: AgentState,
) -> Command[Literal["search", "reasoner", "verifier", "output", "abstain", "__end__"]]:
    """현재 상태를 보고 다음 워커를 Supervisor가 결정한다."""

    step_count = state.get("step_count", 0)
    retry_count = state.get("retry_count", 0)

    if step_count >= MAX_STEPS:
        return Command(
            goto="abstain",
            update={
                "worker": "end",
                "status": "abstain",
                "step_count": step_count + 1,
            },
        )

    if state.get("search_result") is None:
        return Command(
            goto="search",
            update={"worker": "search", "step_count": step_count + 1},
        )

    if state.get("answer_draft") is None:
        return Command(
            goto="reasoner",
            update={"worker": "reasoner", "step_count": step_count + 1},
        )

    verification = state.get("verification_result")
    verification_status = verification.get("status") if verification is not None else None

    if verification_status is None:
        return Command(
            goto="verifier",
            update={"worker": "verifier", "step_count": step_count + 1},
        )

    if verification_status == "supported":
        return Command(
            goto="output",
            update={
                "worker": "output",
                "status": "supported",
                "step_count": step_count + 1,
            },
        )

    if verification_status in {"insufficient", "conflict"} and retry_count < MAX_RETRIES:
        return Command(
            goto="search",
            update={
                "worker": "search",
                "retry_count": retry_count + 1,
                "step_count": step_count + 1,
                # 재검색 결과로 다시 추론·검증하도록 이전 결과를 비운다.
                "search_result": None,
                "evidence": [],
                "graph_paths": [],
                "answer_draft": None,
                "claims": [],
                "claim_evidence_ids": [],
                "verification_result": None,
                "verification_feedback": state.get("verification_feedback"),
                "retry_required": False,
            },
        )

    return Command(
        goto="abstain",
        update={
            "worker": "end",
            "status": "abstain",
            "step_count": step_count + 1,
        },
    )

# 수정
async def search_node(state: AgentState) -> dict[str, Any]:
    """설정에 따라 기존 LLM 검색 또는 Jev 검색을 실행."""
    from app.router.jev_router import (
        run_jev_search,
        search_router_backend,
    )

    messages = build_worker_messages(state, "search")

    if search_router_backend() == "jev":
        search_data = await run_jev_search(
            state=state,
            worker_messages=messages,
        )
    else:
        worker = get_worker("search")
        result = await worker.ainvoke({"messages": messages})
        search_data = result["structured_response"].model_dump()

    # 실제 SQL 조회 값도 근거로 전달해 추론·검증 워커가 같은 값을 확인한다.
    profile = state.get("user_profile", {})
    profile_evidence = [
        {
            "evidence_id": f"profile:{profile['user_id']}:{key}",
            "content": f"{key}: {value}",
            "source": "sqlite_profile",
            "score": None,
            "graph_path": [],
            "metadata": {"source_field": key},
        }
        for key, value in profile.items()
        if key != "user_id" and value is not None and value != ""
    ] if profile else []
    search_data["evidence"] = [*search_data["evidence"], *profile_evidence]

    return {
        "search_mode": search_data["search_mode"],
        "search_result": search_data,
        "evidence": search_data["evidence"],
        "graph_paths": search_data["graph_paths"],
        "graph_visit_count": state.get("graph_visit_count", 0) + 1,
        "worker_trace": append_worker_trace(state, "search"),
        "status": "running",
    }


def reasoner_node(state: AgentState) -> dict[str, Any]:
    """추론 워커를 호출하고 답변 초안을 상태에 반영한다."""

    worker = get_worker("reasoner")
    result = worker.invoke({"messages": build_worker_messages(state, "reasoner")})

    reasoner_output = result["structured_response"]

    answer_draft = reasoner_output.answer_draft
    claims = [
        claim if isinstance(claim, dict)
        else {"claim": str(claim), "evidence_ids": []}
        for claim in reasoner_output.claims
    ]
    if not claims and answer_draft and state.get("evidence"):
        claims = [{"claim": answer_draft, "evidence_ids": []}]

    claim_evidence_ids = bind_claim_evidence(
        state,
        claims,
        reasoner_output.claim_evidence_ids,
    )
    claims = [
        {
            **claim,
            "evidence_ids": claim_evidence_ids[index],
        }
        for index, claim in enumerate(claims)
    ]

    return {
        "answer_draft": answer_draft,
        "claims": claims,
        "claim_evidence_ids": claim_evidence_ids,
        "worker_trace": append_worker_trace(state, "reasoner"),
        "status": "running",
    }


def is_directly_grounded(state: AgentState) -> bool:
    """답변이 검색된 근거 원문과 직접 일치하는지 확인한다."""

    answer = str(state.get("answer_draft") or "").strip()
    evidence_by_id = {
        evidence.get("evidence_id"): str(evidence.get("content") or "").strip()
        for evidence in state.get("evidence", [])
    }
    cited_ids = {
        evidence_id
        for ids in state.get("claim_evidence_ids", [])
        for evidence_id in ids
    }
    if not answer or not cited_ids or not cited_ids.issubset(evidence_by_id):
        return False
    if any(answer == evidence_by_id[evidence_id] for evidence_id in cited_ids):
        return True

    return all(
        evidence_by_id[evidence_id] and evidence_by_id[evidence_id] in answer
        for evidence_id in cited_ids
    )


def verifier_node(state: AgentState) -> dict[str, Any]:
    """검증 워커를 호출하고 검증 결과를 상태에 반영한다."""

    if is_directly_grounded(state):
        feedback = "답변이 검색 근거 원문과 일치합니다."
        return {
            "verification_result": {
                "status": "supported",
                "feedback": feedback,
                "retry_required": False,
            },
            "verification_feedback": feedback,
            "retry_required": False,
            "worker_trace": append_worker_trace(state, "verifier"),
            "status": "supported",
        }

    worker = get_worker("verifier")
    result = worker.invoke({"messages": build_worker_messages(state, "verifier")})

    verification_output = result["structured_response"]
    verification_data = verification_output.model_dump()

    return {
        "verification_result": verification_data,
        "verification_feedback": verification_data["feedback"],
        "retry_required": verification_data["retry_required"],
        "worker_trace": append_worker_trace(state, "verifier"),
        "status": verification_data["status"],
    }


def output_node(state: AgentState) -> dict[str, Any]:
    """최종 답변을 반환하고 다음 질문을 위해 대화에 기록한다."""
    answer = str(state.get("answer_draft") or "")
    return {
        "final_response": answer,
        "messages": [{"role": "assistant", "content": answer}],
        "worker": "end",
        "worker_trace": append_worker_trace(state, "output"),
        "status": "supported",
    }


def abstain_node(state: AgentState) -> dict[str, Any]:
    """근거 부족 또는 처리 상한 도달 시 보류 응답을 만든다."""

    return make_abstain_update(state)
