"""스키마 층: 그래프를 실행할 때 노드에 넘기는 실행 값(ChatContext)의 모양을 정한다.

판정 객체와 검색기는 State 에 넣지 않는다. State 는 체크포인터가 턴마다 저장하는 대화 기록이고,
판정 객체처럼 저장할 수 없는 큰 객체는 실행할 때 context=ChatContext(...) 로 따로 넘긴다.
"""
# [CareerGraph 수정 필요] ChatContext의 사용자 ID·Chroma 검색기 구조를 Neo4j·근거 계약으로 교체한다.
from dataclasses import dataclass,field
from typing import Any, Literal
from pydantic import BaseModel

SearchMode = Literal["vector", "graph", "hybrid"]

@dataclass
class SearchRequest:
    question: str
    mode : SearchMode
    top_k: int=5


@dataclass
class Evidence:
    evidence_id : str
    content:str
    source:str | None= None
    score:float | None=None
    graph_path:list[str] = field(default_factory=list)
    metadata:dict[str,Any] = field(default_factory=dict)

@dataclass
class SearchResult:
    mode: SearchMode
    evidences: list[Evidence] = field(default_factory=list)
    error: str |None=None




@dataclass
class ChatContext:
    """노드가 runtime.context 로 읽는 실행 값 묶음."""
    rails: Any
    retriever: Any
    user_id: str | None=None    # 로그인한 사용자 id. 로그인하지 않았으면 None 이다



class SearchWorkerResult(BaseModel):
    search_mode: Literal["vector", "graph", "hybrid"]
    search_result: str
    evidence: list[Evidence]
    graph_paths: list[list[str]]


class ReasonerResult(BaseModel):
    """Reasoner Worker가 반환하여 AgentState에 저장할 결과."""

    answer_draft: str
    # 모델이 주장 문자열 또는 구조화된 dict를 반환하는 경우를 모두 허용한다.
    claims: list[Any]
    claim_evidence_ids: list[list[str]]


class VerificationResult(BaseModel):
    """Verifier Worker가 반환하여 AgentState에 저장할 결과."""

    status: Literal["supported", "insufficient", "conflict", "error"]
    feedback: str
    retry_required: bool





if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.schemas
    # 실제 검색기 대신 이름 글자를 넣어 모양만 확인한다
    sample = ChatContext(
        retriever="neo4j-aura-searcher",
        user_id="U0001",
    )
    print(sample)
