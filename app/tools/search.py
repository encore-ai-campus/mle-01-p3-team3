"""CareerGraph Search Worker가 사용할 Neo4j 검색 도구 모음."""

import os
import re
from typing import Any

from langchain_core.tools import tool
from neo4j import GraphDatabase

from app.core.config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, embedding_model


VECTOR_INDEX_NAME = os.getenv("NEO4J_VECTOR_INDEX", "career_embedding_index")
READ_ONLY_BLOCKLIST = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|GRANT|DENY|REVOKE|CALL\s+{)\b",
    re.IGNORECASE,
)


def _get_driver():
    """환경변수 설정을 확인한 뒤 Neo4j Driver를 만든다."""

    if not NEO4J_URI or NEO4J_PASSWORD is None:
        raise RuntimeError("NEO4J_URI와 NEO4J_PASSWORD를 먼저 설정하세요.")

    return GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD.get_secret_value()),
    )


def _run_read_query(query: str, **parameters: Any) -> list[dict[str, Any]]:
    """읽기 전용 Cypher를 실행하고 레코드를 dict 목록으로 반환한다."""

    _validate_read_only_cypher(query)

    with _get_driver() as driver:
        with driver.session(database=NEO4J_DATABASE) as session:
            result = session.run(query, parameters)
            return [record.data() for record in result]


def _validate_read_only_cypher(query: str) -> None:
    """검색 도구에서 데이터 변경 Cypher가 실행되지 않도록 검사한다."""

    if not query.strip():
        raise ValueError("Cypher 쿼리가 비어 있습니다.")

    if ";" in query:
        raise ValueError("한 번에 하나의 Cypher 쿼리만 허용합니다.")

    if READ_ONLY_BLOCKLIST.search(query):
        raise ValueError("읽기 전용 검색에서는 데이터 변경 Cypher를 사용할 수 없습니다.")


def _vector_search(question: str, top_k: int) -> list[dict[str, Any]]:
    """Neo4j 벡터 인덱스를 조회하는 내부 함수."""

    if top_k < 1 or top_k > 50:
        raise ValueError("top_k는 1에서 50 사이여야 합니다.")

    embedding = embedding_model.embed_query(question)
    query = """
    CALL db.index.vector.queryNodes($index_name, $top_k, $embedding)
    YIELD node, score
    RETURN
        coalesce(node.evidence_id, elementId(node)) AS evidence_id,
        coalesce(node.content, "") AS content,
        coalesce(node.source, "") AS source,
        score
    """

    return _run_read_query(
        query,
        index_name=VECTOR_INDEX_NAME,
        top_k=top_k,
        embedding=embedding,
    )


@tool
def vector_search(question: str, top_k: int = 5) -> dict[str, Any]:
    """질문을 임베딩하여 Neo4j 벡터 인덱스에서 근거를 검색한다."""

    return {
        "search_mode": "vector",
        "evidence": _vector_search(question, top_k),
        "graph_paths": [],
    }


@tool
def graph_search(cypher: str) -> dict[str, Any]:
    """읽기 전용 Cypher를 실행하여 관계와 그래프 경로를 검색한다."""

    rows = _run_read_query(cypher)
    graph_paths = [row["graph_path"] for row in rows if "graph_path" in row]

    return {
        "search_mode": "graph",
        "evidence": rows,
        "graph_paths": graph_paths,
    }


@tool
def hybrid_search(
    question: str,
    cypher: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """벡터 검색으로 후보를 찾은 뒤 후보를 기준으로 그래프를 확장한다."""

    vector_rows = _vector_search(question, top_k)
    evidence_ids = [row["evidence_id"] for row in vector_rows]

    if not evidence_ids:
        return {
            "search_mode": "hybrid",
            "evidence": [],
            "graph_paths": [],
        }

    graph_rows = _run_read_query(cypher, evidence_ids=evidence_ids)
    graph_paths = [row["graph_path"] for row in graph_rows if "graph_path" in row]

    return {
        "search_mode": "hybrid",
        "evidence": vector_rows + graph_rows,
        "graph_paths": graph_paths,
    }


def get_search_tools() -> list:
    """Search Worker에 연결할 검색 도구 목록을 반환한다."""

    return [vector_search, graph_search, hybrid_search]


if __name__ == "__main__":
    print("검색 도구:", [tool.name for tool in get_search_tools()])
