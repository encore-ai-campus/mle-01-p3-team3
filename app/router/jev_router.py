"""Jev 검색 방식 분류와 기존 검색 도구 연결."""

import asyncio
import json
import logging
import os
import re
from functools import lru_cache
from typing import cast

from dotenv import dotenv_values
from langchain_core.messages import SystemMessage
from langchain_typesafe import Choice, TypeSafeClassifier

from app.core.config import PROJECT_DIR, llm, settings
from app.core.prompts import SEARCH_SYSTEM_PROMPT
from app.core.schemas import SearchMode, SearchWorkerResult
from app.tools.search import get_search_tools


ROUTE_CRITERIA = {
    "vector": (
        "업무 내용으로 직업을 탐색하거나 "
        "특정 직업의 업무 설명만 요청한다."
    ),
    "graph": (
        "직업·학과·능력·자격이 명시되어 있고 "
        "관계 또는 경로만 요청한다. "
        "앞 대화에 대상이 있어도 포함한다."
    ),
    "hybrid": (
        "업무 설명으로 직업을 찾고 그 후보의 관계를 요청하거나 "
        "업무 설명과 관계 정보를 함께 요청한다."
    ),
}

ROUTE_PROMPT = SEARCH_SYSTEM_PROMPT + """
[독립 분류 실험의 출력 범위]
도구 실행·검색·근거 생성·Cypher 작성은 하지 않는다.
위 검색 결과 반환 지시 대신 이번 출력 스키마에 따라
검색 방식 하나만 반환한다.
질문과 최근 대화를 함께 참고한다. 공통 선택 정책:
""" + json.dumps(ROUTE_CRITERIA, ensure_ascii=False)

TOOL_NAMES = {
    "vector": "vector_search",
    "graph": "graph_search",
    "hybrid": "hybrid_search",
}

logger = logging.getLogger(__name__)

ROUTE_TIMEOUT_SECONDS = 15


class SearchRoutingError(RuntimeError):
    """검색 방식 판정 또는 검색 실행 준비 실패."""

#.env 파일의 SEARCH_ROUTER_BACKEND=jev면 jev 분류를 사용하고,
# llm이면 기존 LLM 분류를 사용

def search_router_backend() -> str:
    """환경변수 또는 프로젝트 .env에서 사용할 방식을 읽는다."""
    env = dotenv_values(PROJECT_DIR / ".env")
    backend = (
        os.getenv("SEARCH_ROUTER_BACKEND")
        or env.get("SEARCH_ROUTER_BACKEND")
        or "jev"
    ).strip().lower()

    if backend not in {"jev", "llm"}:
        raise ValueError(
            "SEARCH_ROUTER_BACKEND는 jev 또는 llm이어야 합니다."
        )
    return backend


def recent_conversation(state: dict) -> list[dict]:
    """현재 프로젝트의 dict/BaseMessage 대화 형식을 모두 지원."""
    history = []

    for message in state.get("messages", [])[-6:]:
        if isinstance(message, dict):
            role = message.get("role", "")
            content = message.get("content", "")
        else:
            role = getattr(message, "type", "")
            content = getattr(message, "content", "")

        role = {
            "human": "user",
            "ai": "assistant",
        }.get(role, role)

        if role not in {"user", "assistant"}:
            continue

        if not isinstance(content, str):
            content = json.dumps(
                content, ensure_ascii=False, default=str
            )

        history.append({"role": role, "content": content})

    return history


async def classify_search(state: dict) -> SearchMode:
    """질문과 최근 대화를 Jev에 전달해 검색 방식만 결정."""
    question = str(state.get("question") or "").strip()
    if not question:
        raise SearchRoutingError("검색할 질문이 비어 있습니다.")

    payload = {
        "question": question,
        "recent_conversation": recent_conversation(state),
        "previous_search_mode": state.get("search_mode"),
        "verification_feedback": state.get("verification_feedback"),
    }

    classifier = TypeSafeClassifier(
        model=settings.typesafe_model,
        api_key=settings.typesafe_api_key.get_secret_value(),
        timeout=ROUTE_TIMEOUT_SECONDS,
    )

    try:
        decision = await asyncio.wait_for(
            classifier.ainvoke({
                "state": payload,
                "questions": {
                    "route": Choice(
                        instructions=ROUTE_PROMPT,
                        criteria=ROUTE_CRITERIA,
                    )
                },
            }),
            timeout=ROUTE_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        # API 오류를 임의로 vector/graph로 바꾸지 않는다.
        raise SearchRoutingError(
            f"Jev 검색 분류 실패: {type(exc).__name__}"
        ) from None
    finally:
        if classifier.async_client is not None:
            await classifier.async_client.aclose()
        if classifier.client is not None:
            classifier.client.close()

    answer = decision.choices.get("route")
    if answer is None or answer.choice not in ROUTE_CRITERIA:
        raise SearchRoutingError(
            "Jev가 유효한 검색 방식을 반환하지 않았습니다."
        )

    return cast(SearchMode, answer.choice)


@lru_cache(maxsize=3)
def selected_tool_and_planner(mode: SearchMode):
    """선택된 도구 하나만 GPT에 제공하여 인자만 작성하게 한다."""
    tool_map = {
        tool.name: tool
        for tool in get_search_tools()
    }
    tool = tool_map[TOOL_NAMES[mode]]

    planner = llm.bind_tools(
        [tool],
        tool_choice=tool.name,
        parallel_tool_calls=False,
    )
    return tool, planner


@lru_cache(maxsize=1)
def canonical_job_patterns():
    """적재 원본의 직업명으로 공백 차이만 허용하는 패턴을 만든다."""
    path = PROJECT_DIR / "data/expanded_20261108/jobs.json"
    rows = json.loads(path.read_text(encoding="utf-8-sig"))
    entries = []
    for row in rows:
        name = str(row.get("job_name") or "").strip()
        code = row.get("job_code")
        # 전공은 실제 직업명이기도 하지만 학과 질문의 일반 용어와 겹쳐 자동 식별에서 제외한다.
        if not name or code is None or name == "전공":
            continue
        compact = "".join(name.split())
        pattern = re.compile(
            r"(?<!\w)" + r"\s*".join(re.escape(c) for c in compact)
            + r"(?=$|[\s,.!?]|(?:의|은|는|이|가|을|를|와|과|으로|로|에게|에|도)(?:\s|$))",
            re.IGNORECASE,
        )
        entries.append((pattern, {"job_name": name, "job_code": str(code), "node_id": "job:" + str(code)}))
    return entries


def canonical_job_hints(question: str) -> list[dict]:
    """현재 질문에 명시된 직업만 찾는다. 유사 직업을 추측하지 않는다."""
    matches = []
    for pattern, job in canonical_job_patterns():
        for match in pattern.finditer(question):
            matches.append((match.start(), match.end(), job))
    # 더 긴 정식 직업명이 있으면 그 안에 포함된 짧은 직업명은 제외한다.
    selected = []
    for start, end, job in matches:
        if any(a <= start and end <= b and (a < start or end < b) for a, b, _ in matches):
            continue
        if job not in selected:
            selected.append(job)
    return selected


async def run_jev_search(
    state: dict,
    worker_messages: list,
) -> dict:
    """Jev 분류 → 인자 준비 → 기존 검색 실행 → 기존 형식 반환."""
    mode = await classify_search(state)
    tool, planner = selected_tool_and_planner(mode)

    job_hints = canonical_job_hints(str(state.get("question") or ""))
    instruction = SEARCH_SYSTEM_PROMPT + f"""

[원본 데이터에서 확인한 직업 표기]
{json.dumps(job_hints, ensure_ascii=False)}
위 항목은 질문에 명시된 직업명과 공백 차이만 허용해 대조한 결과다.
해당 직업을 조회할 때 사용자 입력의 이름 대신 위 node_id로 Job을 식별한다.
조회 시작점 식별에 사용하고, 다른 직업을 찾는 질문의 최종 결과를 이 ID로 제한하지 않는다.
일치 항목이 없다고 비슷한 이름의 직업을 임의로 대신 사용하지 않는다.
능력·역량은 HAS_CORE_ABILITY, 자격은 RELATED_CERTIFICATE로 구분한다.
학과를 통해 다른 직업과 능력을 물으면 Major <- Job -> Ability 방향으로 조회한다.

[이번 호출의 확정 사항]
검색 방식은 이미 Jev가 {mode}로 결정했다.
검색 방식을 다시 선택하지 않는다.
반드시 {tool.name} 도구를 정확히 한 번 호출할 인자를 작성한다.
근거와 검색 결과는 직접 작성하지 않는다.
질문과 최근 대화, 검증 피드백을 참고한다.

graph_search에는 별도 파라미터 전달 인자가 없으므로
미정의 $job_codes 등의 변수를 사용하는 쿼리를 만들지 않는다.
hybrid_search에서는 기존 도구가 제공하는 $job_codes를 사용할 수 있다.
그래프 쿼리는 읽기 전용이며 기존 스키마와 반환 별칭을 지킨다.
"""

    message = await planner.ainvoke([
        SystemMessage(content=instruction),
        *worker_messages,
    ])

    calls = message.tool_calls
    if len(calls) != 1 or calls[0]["name"] != tool.name:
        raise SearchRoutingError(
            "선택된 검색 도구의 호출 인자를 준비하지 못했습니다."
        )

    # 기존 검색 도구를 그대로 실행한다.
    logger.debug("Search mode=%s tool=%s args=%s", mode, tool.name,
                 json.dumps(calls[0]["args"], ensure_ascii=False))
    raw = await tool.ainvoke(calls[0]["args"])
    if isinstance(raw, dict):
        logger.debug("Search evidence_count=%s error=%s",
                     len(raw.get("evidence", [])), raw.get("error"))

    if not isinstance(raw, dict):
        raise SearchRoutingError("검색 결과가 dict 형식이 아닙니다.")

    if raw.get("error"):
        raise SearchRoutingError(
            "검색 도구가 실행 오류를 반환했습니다."
        )

    if raw.get("search_mode") != mode:
        raise SearchRoutingError(
            "Jev 선택과 실제 검색 도구의 방식이 다릅니다."
        )

    # LLM이 근거를 다시 작성하지 않도록 도구 결과를 직접 전달.
    evidence = raw.get("evidence", [])
    graph_paths = raw.get("graph_paths", [])

    output = SearchWorkerResult.model_validate({
        "search_mode": mode,
        "search_result": (
            f"{mode} 검색: 근거 {len(evidence)}개, "
            f"그래프 경로 {len(graph_paths)}개"
        ),
        "evidence": evidence,
        "graph_paths": graph_paths,
    })

    return output.model_dump()