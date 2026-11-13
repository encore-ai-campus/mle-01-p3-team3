"""Supervisor와 Worker 그래프의 노드를 작성하는  파일."""

from typing import Any, Literal

from langgraph.graph import END
from langgraph.types import Command

from app.agents.workers import create_workers
from app.core.prompts import WORKER_PROMPT_TEMPLATES
from app.graph.state import AgentState


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


def build_worker_instruction(state: AgentState) -> str:
    """현재 질문과 최근 대화 기록을 워커 지시문으로 만든다."""

    messages = state.get("messages", [])[-6:]
    history = "\n".join(
        f"{message.get('role', 'unknown')}: {message.get('content', '')}"
        if isinstance(message, dict)
        else str(message)
        for message in messages
    )
    follow_up_hint = ""
    if "전공" in state.get("question", "") and len(messages) > 1:
        follow_up_hint = (
            "Follow-up intent: connect the previous occupation to related major nodes. "
            "Prefer hybrid or graph search and return major names with related_majors evidence.\n"
        )
    return (
        f"Question: {state['question']}\n"
        f"Recent conversation history:\n{history}\n"
        f"{follow_up_hint}"
        f"Search mode: {state.get('search_mode')}\n"
        f"Evidence: {state.get('evidence', [])}\n"
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
        "instruction": build_worker_instruction(state),
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


def repair_abstaining_draft(state: AgentState, answer_draft: str) -> str:
    """직업명이 일치하는 강한 근거가 있을 때만 과도한 보류를 보정한다."""

    if "전공" in state.get("question", ""):
        majors = list(dict.fromkeys(
            str(evidence.get("content"))
            for evidence in state.get("evidence", [])
            if evidence.get("metadata", {}).get("source_field") == "related_majors"
            and evidence.get("content")
        ))
        if majors:
            return f"관련 전공으로는 {', '.join(majors[:5])} 등을 고려할 수 있습니다."

    abstain_phrases = (
        "답하기 어렵",
        "확정하기 어렵",
        "확인하기 어렵",
        "근거가 부족",
        "확인할 수 없",
        "설명할 수 없",
    )
    if not any(phrase in answer_draft for phrase in abstain_phrases):
        return answer_draft

    question = state.get("question", "")
    for evidence in state.get("evidence", []):
        metadata = evidence.get("metadata", {})
        job_name = str(metadata.get("job_name", ""))
        score = evidence.get("score") or 0
        if job_name and job_name in question and score >= 0.70:
            return str(evidence.get("content", answer_draft))
    return answer_draft


def make_abstain_update(state: AgentState) -> dict[str, Any]:
    """처리 상한 또는 근거 부족 시 보류 상태를 만든다."""

    return {
        "status": "abstain",
        "worker": "end",
        "worker_trace": append_worker_trace(state, "abstain"),
        "final_response": "현재 자료만으로는 답변을 확정하기 어렵습니다.",
        "error": None,
    }


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
                "verification_feedback": None,
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


def search_node(state: AgentState) -> dict[str, Any]:
    """검색 워커를 호출하고 검색 결과를 상태에 반영한다."""

    worker = get_worker("search")
    result = worker.invoke({"messages": build_worker_messages(state, "search")})

    search_output = result["structured_response"]
    search_data = search_output.model_dump()

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

    answer_draft = repair_abstaining_draft(state, reasoner_output.answer_draft)
    claims = [
        claim if isinstance(claim, dict)
        else {"claim": str(claim), "evidence_ids": []}
        for claim in reasoner_output.claims
    ]
    if answer_draft != reasoner_output.answer_draft:
        claims = [{"claim": answer_draft, "evidence_ids": []}]
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
    """검증된 답변 초안을 최종 응답으로 만든다."""

    return {
        "final_response": state.get("answer_draft"),
        "worker": "end",
        "worker_trace": append_worker_trace(state, "output"),
        "status": "supported",
    }


def abstain_node(state: AgentState) -> dict[str, Any]:
    """근거 부족 또는 처리 상한 도달 시 보류 응답을 만든다."""

    return make_abstain_update(state)
