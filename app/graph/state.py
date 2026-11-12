"""그래프 층: 노드가 읽고 고치는 대화 State 의 모양을 정한다.

messages 는 체크포인터가 대화 ID(thread_id)마다 저장해 다음 턴에 그대로 이어진다.
나머지 칸은 이번 턴의 값이다. input_rail 노드가 턴을 시작할 때 모두 비운다.
"""
# [CareerGraph 수정 필요] 루나 대화 State를 질문·근거·그래프 경로·검증 상태 중심으로 재설계한다.
from typing import Annotated, TypedDict,Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from careeragent.app.core.schemas import Evidence, SearchWorkerResult, VerificationResult


class AgentState(TypedDict):
    messages: list
    question: str

    # 슈퍼바이저가 정하는 다음 워커
    worker: Literal['search','reasoner','verifier','output','end']

    # search 워커가 사용하는 검색 방식
    search_mode: Literal['vector','graph','hybrid'] | None
    search_result: SearchWorkerResult | None
    evidence: list[Evidence]
    graph_paths: list[list[str]]
    graph_visit_count: int

    # Reasoner 워커 결과
    answer_draft: str | None
    claims:list[dict]
    claim_evidence_ids:list[list[str]]

    # verifier 워커 결과
    verification_result : VerificationResult | None
    verification_feedback: str | None
    retry_required:bool
    
    # 재검색·실행 제어
    retry_count: int
    step_count: int

    # 종료 결과
    status: Literal[
        "running",
        "supported",
        "insufficient",
        "abstain",
        "error",
    ]
    final_response: str | None
    error: str | None


    

# [보조 함수] 이번 턴 칸 비우기
def empty_turn() -> dict:
    """이번 턴의 칸을 모두 빈 값으로 채운 dict 를 돌려준다(messages 는 넣지 않는다)."""
    return {
        "messages": [],
        "question": "",
        "worker": "search",
        "search_mode": None,
        "search_result": None,
        "evidence": [],
        "graph_paths": [],
        "graph_visit_count": 0,
        "answer_draft": None,
        "claims": [],
        "claim_evidence_ids": [],
        "verification_result": None,
        "verification_feedback": None,
        "retry_required": False,
        "retry_count": 0,
        "step_count": 0,
        "status": "running",
        "final_response": None,
        "error": None,
    }


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.state
    print("State 칸:", list(AgentState.__annotations__))
    print("턴 시작 값:", empty_turn())
