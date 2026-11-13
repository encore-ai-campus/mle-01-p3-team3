"""CareerGraph Aura용 읽기 전용 검색 도구."""

import json
import os
import re
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError
from neo4j.graph import Node, Path as Neo4jPath, Relationship

from app.core.config import (
    DATA_DIR,
    NEO4J_DATABASE,
    NEO4J_PASSWORD,
    NEO4J_URI,
    NEO4J_USER,
    embedding_model,
)


# Aura에 실제로 생성된 Job 벡터 인덱스 이름.
VECTOR_INDEX_NAME = os.getenv("NEO4J_VECTOR_INDEX", "job_work_embedding_768")
JOB_ROW_MAP_PATH = DATA_DIR / "expanded_20261108" / "jobs.json"

RELATION_TO_SOURCE_FIELD = {
    "RELATED_MAJOR": "related_majors",
    "HAS_CORE_ABILITY": "core_abilities",
    "RELATED_CERTIFICATE": "related_certificates",
}

READ_ONLY_BLOCKLIST = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP|ALTER|GRANT|DENY|REVOKE|CALL\s+{)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _job_row_map() -> dict[str, str]:
    """Neo4j Job.source_id(job_code)를 평가셋 row_id로 연결한다."""

    if not JOB_ROW_MAP_PATH.exists():
        return {}

    rows = json.loads(JOB_ROW_MAP_PATH.read_text(encoding="utf-8"))
    return {
        str(row["job_code"]): str(row["row_id"])
        for row in rows
        if row.get("job_code") is not None and row.get("row_id")
    }


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


def _value(value: Any) -> Any:
    """Neo4j 객체를 모델이 읽을 수 있는 원시 값으로 바꾼다."""

    if isinstance(value, Node):
        return value.get("id") or value.get("name") or value.element_id
    if isinstance(value, Relationship):
        return value.type
    if isinstance(value, Neo4jPath):
        return [_value(node) for node in value.nodes]
    if isinstance(value, (list, tuple)):
        return [_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _value(item) for key, item in value.items()}
    return value


def _path_ids(value: Any) -> list[str]:
    """graph_path를 Aura node.id 목록으로 정규화한다."""

    def is_node_id(item: str) -> bool:
        return item.startswith(("job:", "major:", "ability:", "certificate:"))

    if hasattr(value, "nodes"):
        return [
            node_id
            for node in value.nodes
            if (node_id := str(node.get("id") or node.get("name") or node.element_id))
            and is_node_id(node_id)
        ]

    normalized = _value(value)
    if isinstance(normalized, list):
        path_ids: list[str] = []
        for item in normalized:
            if isinstance(item, dict):
                node_id = item.get("id") or item.get("name")
                if node_id is not None and is_node_id(str(node_id)):
                    path_ids.append(str(node_id))
            else:
                item_text = str(item)
                if is_node_id(item_text):
                    path_ids.append(item_text)
        return path_ids
    if isinstance(normalized, dict):
        node_id = normalized.get("id") or normalized.get("name")
        return [str(node_id)] if node_id is not None and is_node_id(str(node_id)) else []
    normalized_text = str(normalized) if normalized is not None else ""
    return [normalized_text] if is_node_id(normalized_text) else []


def _canonical_evidence_id(
    row_id: str | None,
    source_field: str | None,
    fallback_node_id: str | None = None,
) -> str:
    """챗봇과 평가셋이 공유하는 표준 근거 ID를 만든다."""

    if row_id and source_field:
        return f"{row_id}:{source_field}"
    if fallback_node_id and source_field:
        return f"{fallback_node_id}:{source_field}"
    raise ValueError(
        "검색 결과에 row_id/source_field 또는 node_id/source_field가 필요합니다."
    )


def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """벡터·그래프 검색 행을 Evidence 계약에 맞게 정규화한다."""

    raw = {key: _value(value) for key, value in record.items()}
    node_id = raw.get("node_id") or raw.get("job_node_id")
    job_code = raw.get("job_code") or raw.get("source_id")
    row_id = raw.get("row_id") or _job_row_map().get(str(job_code))
    relationship = raw.get("relationship") or raw.get("relationship_type")
    source_field = raw.get("source_field")

    if not source_field and relationship:
        source_field = RELATION_TO_SOURCE_FIELD.get(str(relationship))
    if not source_field:
        source_field = "work" if raw.get("work") is not None else None

    content = raw.get("content")
    if content is None:
        content = raw.get("text")
    if content is None:
        content = raw.get("work")
    if content is None:
        content = raw.get("excerpt")
    if content is None:
        content = ""

    evidence_id = raw.get("evidence_id")
    if not evidence_id:
        evidence_id = _canonical_evidence_id(
            row_id=row_id,
            source_field=source_field,
            fallback_node_id=node_id,
        )

    metadata = dict(raw.get("metadata") or {})
    for key in (
        "node_id",
        "job_node_id",
        "job_code",
        "job_name",
        "row_id",
        "source_field",
        "relationship",
        "relationship_type",
        "source_type",
        "source_file",
    ):
        if raw.get(key) is not None:
            metadata[key] = raw[key]
    if source_field is not None:
        metadata["source_field"] = source_field
    if relationship is not None:
        metadata["relationship"] = relationship

    return {
        "evidence_id": str(evidence_id),
        "content": str(content),
        "source": raw.get("source") or raw.get("source_file") or raw.get("source_type"),
        "score": raw.get("score"),
        "graph_path": _path_ids(raw.get("graph_path")),
        "metadata": metadata,
    }


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_normalize_record(row) for row in rows]


def _vector_search(question: str, top_k: int) -> list[dict[str, Any]]:
    """Job.work_embedding 벡터 인덱스를 조회한다."""

    if top_k < 1 or top_k > 50:
        raise ValueError("top_k는 1에서 50 사이여야 합니다.")

    embedding = embedding_model.embed_query(question)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", VECTOR_INDEX_NAME):
        raise ValueError("NEO4J_VECTOR_INDEX 이름이 올바르지 않습니다.")

    query = f"""
    MATCH (node:Job)
    SEARCH node IN (
        VECTOR INDEX {VECTOR_INDEX_NAME}
        FOR $embedding
        LIMIT $top_k
    ) SCORE AS score
    RETURN
        node.id AS node_id,
        node.source_id AS job_code,
        node.name AS job_name,
        node.work AS work,
        'work' AS source_field,
        node.source AS source,
        score
    """

    return _normalize_rows(
        _run_read_query(
            query,
            top_k=top_k,
            embedding=embedding,
        )
    )


@tool
def vector_search(question: str, top_k: int = 5) -> dict[str, Any]:
    """질문을 임베딩하여 Job 업무 벡터 인덱스에서 직업 근거를 검색한다."""

    return {
        "search_mode": "vector",
        "evidence": _vector_search(question, top_k),
        "graph_paths": [],
    }


@tool
def graph_search(cypher: str) -> dict[str, Any]:
    """읽기 전용 Cypher를 실행하여 Aura 그래프 관계와 경로를 검색한다."""

    try:
        rows = _run_read_query(cypher)
    except Neo4jError as exc:
        return {
            "search_mode": "graph",
            "evidence": [],
            "graph_paths": [],
            "error": f"읽기 전용 Cypher 실행 실패: {exc.__class__.__name__}",
        }
    evidence = []
    for row in rows:
        try:
            evidence.append(_normalize_record(row))
        except ValueError:
            # 경로만 반환한 Cypher는 graph_paths로만 사용한다.
            continue
    graph_paths = [
        path
        for row in rows
        if (path := _path_ids(row.get("graph_path") or row.get("p")))
    ]

    return {
        "search_mode": "graph",
        "evidence": evidence,
        "graph_paths": graph_paths,
    }


@tool
def hybrid_search(
    question: str,
    cypher: str,
    top_k: int = 5,
) -> dict[str, Any]:
    """Job 벡터 후보를 찾은 뒤 실제 Aura 그래프 관계를 확장한다."""

    vector_rows = _vector_search(question, top_k)
    job_codes = [
        row["metadata"]["job_code"]
        for row in vector_rows
        if row["metadata"].get("job_code") is not None
    ]
    row_ids = [
        row["metadata"]["row_id"]
        for row in vector_rows
        if row["metadata"].get("row_id") is not None
    ]

    if not job_codes:
        return {
            "search_mode": "hybrid",
            "evidence": vector_rows,
            "graph_paths": [],
        }

    graph_rows = _run_read_query(
        cypher,
        job_codes=job_codes,
        row_ids=row_ids,
    )
    graph_paths = [
        path
        for row in graph_rows
        if (path := _path_ids(row.get("graph_path") or row.get("p")))
    ]

    return {
        "search_mode": "hybrid",
        "evidence": vector_rows + _normalize_rows(graph_rows),
        "graph_paths": graph_paths,
    }


def get_search_tools() -> list:
    """Search Worker에 연결할 Aura 검색 도구 목록을 반환한다."""

    return [vector_search, graph_search, hybrid_search]


if __name__ == "__main__":
    print("검색 도구:", [search_tool.name for search_tool in get_search_tools()])
