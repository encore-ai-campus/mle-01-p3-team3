"""Supervisor와 Worker 그래프의 노드를 작성하는 연습 파일."""

from typing import Any, Literal

from langgraph.graph import END
from langgraph.types import Command

from careeragent.app.agents.workers import create_workers
from careeragent.app.graph.state import AgentState


WORKERS: dict[str, object] | None = None
MAX_RETRIES = 1
MAX_STEPS = 10


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


def build_worker_instruction(state: AgentState) -> str:
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


def make_abstain_update(state: AgentState) -> dict[str, Any]:
    """처리 상한 또는 근거 부족 시 보류 상태를 만든다."""

    return {
        "status": "abstain",
        "worker": "end",
        "final_response": "현재 자료만으로는 답변을 확정하기 어렵습니다.",
        "error": None,
    }


def supervisor_node(
    state: AgentState,
) -> Command[Literal["search", "reasoner", "verifier", "output", "abstain", END]]:
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
    verification_status = verification.status if verification is not None else None

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
    result = worker.invoke({
        "messages": [
            {
                "role": "user",
                "content": build_worker_instruction(state),
            }
        ]
    })

    search_output = result["structured_response"]

    return {
        "search_mode": search_output.search_mode,
        "search_result": search_output,
        "evidence": search_output.evidence,
        "graph_paths": search_output.graph_paths,
        "graph_visit_count": state.get("graph_visit_count", 0) + 1,
        "status": "running",
    }


def reasoner_node(state: AgentState) -> dict[str, Any]:
    """추론 워커를 호출하고 답변 초안을 상태에 반영한다."""

    worker = get_worker("reasoner")
    result = worker.invoke({
        "messages": [
            {
                "role": "user",
                "content": build_worker_instruction(state),
            }
        ]
    })

    reasoner_output = result["structured_response"]

    return {
        "answer_draft": reasoner_output.answer_draft,
        "claims": reasoner_output.claims,
        "claim_evidence_ids": reasoner_output.claim_evidence_ids,
        "status": "running",
    }


def verifier_node(state: AgentState) -> dict[str, Any]:
    """검증 워커를 호출하고 검증 결과를 상태에 반영한다."""

    worker = get_worker("verifier")
    result = worker.invoke({
        "messages": [
            {
                "role": "user",
                "content": build_worker_instruction(state),
            }
        ]
    })

    verification_output = result["structured_response"]

    return {
        "verification_result": verification_output,
        "verification_feedback": verification_output.feedback,
        "retry_required": verification_output.retry_required,
        "status": verification_output.status,
    }


def output_node(state: AgentState) -> dict[str, Any]:
    """검증된 답변 초안을 최종 응답으로 만든다."""

    return {
        "final_response": state.get("answer_draft"),
        "worker": "end",
        "status": "supported",
    }


def abstain_node(state: AgentState) -> dict[str, Any]:
    """근거 부족 또는 처리 상한 도달 시 보류 응답을 만든다."""

    return make_abstain_update(state)
