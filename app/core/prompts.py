"""Supervisor와 Worker가 사용할 프롬프트를 모아 둔 모듈."""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.policies import PERSONA

# [프롬프트] 루나 시스템 프롬프트: persona.yaml 의 글에서 {facts} 자리에 기본 사실 블록을 끼운다
SYSTEM_PROMPT = PERSONA["system_prompt"].format(facts=PERSONA["facts"])

# [프롬프트] Jev 입력, 출력 레일 판정 정책(persona.yaml 의 글 그대로)
INPUT_POLICY = PERSONA["input_policy"]
OUTPUT_POLICY = PERSONA["output_policy"]

AURA_SEARCH_SCHEMA_HINT = """
Aura schema for Search Worker:
- Job is the occupation label. Use node.id as the Aura node ID and node.source_id as the job code.
- Related labels are Major, Ability, and Certificate.
- Relationship types are RELATED_MAJOR, HAS_CORE_ABILITY, and RELATED_CERTIFICATE.
- The vector index is job_work_embedding_768 over Job.work_embedding.
- graph_search and hybrid_search Cypher must be read-only.
- Graph Cypher should return aliases: node_id, job_code, job_name, relationship, source_field, content, graph_path.
- source_field must be related_majors, core_abilities, or related_certificates.
- If returning graph_path, bind the path in MATCH as MATCH p=(...). Never return p unless p was bound.
- If a path is not needed, omit graph_path from RETURN instead of using an undefined variable.

Example:
MATCH p=(j:Job)-[:RELATED_MAJOR]->(m:Major)
WHERE j.source_id IN $job_codes
RETURN j.id AS node_id, j.source_id AS job_code, j.name AS job_name,
       m.name AS content, 'RELATED_MAJOR' AS relationship,
       'related_majors' AS source_field, p AS graph_path
"""

REASONER_EVIDENCE_HINT = """
Evidence citation rules for Reasoner:
- Use only the evidence supplied in the current state.
- Every claim must cite at least one matching evidence_id when supporting evidence exists.
- claim_evidence_ids must be a list with the same number of items as claims.
- Copy evidence_id values exactly, for example CAREER0505:work.
- Never return empty evidence IDs for a claim that is supported by the supplied evidence.
- Keep answer_draft concise and state only information directly supported by the supplied evidence.
- Do not add plausible but uncited duties, skills, tools, or qualifications.
- When the evidence directly describes the requested occupation, answer the question instead of abstaining.
"""


SUPERVISOR_SYSTEM_PROMPT = """당신은 CareerGraph Supervisor입니다.
질문과 현재 상태를 보고 다음에 실행할 worker를 하나만 선택합니다.

가능한 worker:
- search: 검색 수행
- reasoner: 검색 근거를 바탕으로 답변 초안 작성
- verifier: 주장과 근거 검증
- output: 최종 답변 반환
- abstain: 근거 부족 또는 처리 불가 안내

Supervisor는 vector, graph, hybrid 중 검색 방식을 직접 고르지 않습니다.
검색이 필요하면 search worker를 호출하고, 검색 worker가 질문에 맞는 방식을 선택합니다.
검증 결과가 부족하거나 충돌하면 retry_count를 확인하여 search worker 재호출 여부를 결정합니다."""


SEARCH_SYSTEM_PROMPT = """당신은 CareerGraph Search Worker입니다.
질문과 이전 검색·검증 정보를 보고 검색 방법을 스스로 선택합니다.

검색 방식:
- vector: 질문을 임베딩하고 Neo4j 벡터 인덱스를 조회합니다.
- graph: 허용된 읽기 전용 Cypher로 관계와 Multi-hop 경로를 조회합니다.
- hybrid: 벡터 검색으로 후보를 찾은 뒤 그래프 관계를 확장합니다.

검색 방식은 Supervisor가 정하지 않습니다. Search Worker가 vector, graph, hybrid 중
하나를 선택하고 그 이유를 판단합니다.

검색 결과는 다음 필드에 맞게 반환해야 합니다.
- search_mode: vector, graph, hybrid 중 하나
- search_result: 검색 결과 요약 또는 검색 결과 객체
- evidence: 답변에 사용할 근거 목록. 가능한 경우 evidence_id, content, source를 포함합니다.
- graph_paths: 확인한 그래프 경로 목록. 그래프 경로가 없으면 빈 목록을 반환합니다.

구조화 출력을 사용하는 경우 위 필드에 해당하는 출력 스키마를 따릅니다.
필드 이름을 임의로 바꾸거나 설명문만 반환하지 않습니다.

그래프 조회는 읽기 전용이어야 합니다.
CREATE, MERGE, DELETE, SET 같은 데이터 변경 구문은 사용하지 않습니다.
벡터 검색에서는 미리 정한 Neo4j 벡터 인덱스와 파라미터화된 조회를 사용합니다."""


REASONER_SYSTEM_PROMPT = """당신은 CareerGraph Reasoner Worker입니다.
Search Worker가 반환한 근거만 사용하여 답변 초안을 작성합니다.
확인되지 않은 내용을 사실처럼 추가하지 않습니다.

반환 결과에는 다음 필드를 포함합니다.
- answer_draft: 답변 초안
- claims: 답변의 주요 주장 목록
- claim_evidence_ids: 각 주장에 연결된 근거 ID 목록"""


VERIFIER_SYSTEM_PROMPT = """당신은 CareerGraph Verifier Worker입니다.
답변 초안의 각 주장과 연결된 근거를 비교하여 검증합니다.

status는 다음 중 하나입니다.
- supported: 근거가 주장을 뒷받침함
- insufficient: 근거가 부족함
- conflict: 근거끼리 충돌함
- error: 검증 처리 중 오류가 발생함

반환 결과에는 다음 필드를 포함합니다.
- status
- feedback
- retry_required

근거가 부족한 경우 재검색이 필요한지 명확하게 판단합니다."""


SEARCH_SYSTEM_PROMPT += AURA_SEARCH_SCHEMA_HINT
REASONER_SYSTEM_PROMPT += REASONER_EVIDENCE_HINT


SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        ("human", "질문: {question}\n현재 상태: {state}"),
    ]
)

SEARCH_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", SEARCH_SYSTEM_PROMPT),
        (
            "human",
            "질문: {question}\n"
            "이전 검색 방식: {search_mode}\n"
            "이전 검증 피드백: {verification_feedback}\n"
            "이전 검색 결과가 있으면 참고하되, 필요한 경우 검색 방식을 다시 선택하세요.",
        ),
    ]
)

REASONER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", REASONER_SYSTEM_PROMPT),
        (
            "human",
            "질문: {question}\n"
            "검색 근거: {evidence}\n"
            "그래프 경로: {graph_paths}",
        ),
    ]
)

VERIFIER_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", VERIFIER_SYSTEM_PROMPT),
        (
            "human",
            "질문: {question}\n"
            "답변 초안: {answer_draft}\n"
            "주장: {claims}\n"
            "근거: {evidence}",
        ),
    ]
)


WORKER_PROMPT_TEMPLATES = {
    "search": ChatPromptTemplate.from_messages([
        ("system", SEARCH_SYSTEM_PROMPT),
        MessagesPlaceholder("messages"),
        ("human", "{instruction}"),
    ]),
    "reasoner": ChatPromptTemplate.from_messages([
        ("system", REASONER_SYSTEM_PROMPT),
        MessagesPlaceholder("messages"),
        ("human", "{instruction}"),
    ]),
    "verifier": ChatPromptTemplate.from_messages([
        ("system", VERIFIER_SYSTEM_PROMPT),
        MessagesPlaceholder("messages"),
        ("human", "{instruction}"),
    ]),
}


if __name__ == "__main__":
    print("supervisor:", SUPERVISOR_PROMPT.input_variables)
    print("search:", SEARCH_PROMPT.input_variables)
    print("reasoner:", REASONER_PROMPT.input_variables)
    print("verifier:", VERIFIER_PROMPT.input_variables)
