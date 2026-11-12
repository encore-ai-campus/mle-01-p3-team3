"""CareerGraph의 노드를 등록하고 실행 그래프를 조립하는 모듈."""

from langgraph.graph import END, START, StateGraph

from app.core.schemas import ChatContext
from app.graph.nodes import (
    abstain_node,
    output_node,
    reasoner_node,
    search_node,
    supervisor_node,
    verifier_node,
)
from app.graph.state import AgentState


def build_app(checkpointer=None, interrupt_before=None):
    """Supervisor-Worker 그래프를 컴파일한다."""

    builder = StateGraph(
        AgentState,
        context_schema=ChatContext,
    )

    # 노드 등록
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("search", search_node)
    builder.add_node("reasoner", reasoner_node)
    builder.add_node("verifier", verifier_node)
    builder.add_node("output", output_node)
    builder.add_node("abstain", abstain_node)

    # 시작점
    builder.add_edge(START, "supervisor")

    # Supervisor의 Command(goto)가 다음 워커를 선택한다.
    # 각 워커는 작업이 끝나면 Supervisor로 돌아온다.
    builder.add_edge("search", "supervisor")
    builder.add_edge("reasoner", "supervisor")
    builder.add_edge("verifier", "supervisor")

    # 최종 응답과 보류 응답은 그래프를 종료한다.
    builder.add_edge("output", END)
    builder.add_edge("abstain", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before,
    )
