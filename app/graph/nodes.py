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

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from app.core.schemas import ChatContext
from app.guards.rails import check_input, check_output

WORKERS: dict[str, object] | None = None
MAX_RETRIES = 1
MAX_STEPS = 10

# 입력이 차단됐을 때 사용자에게 보여줄 고정 문구
INPUT_BLOCKED_REPLY = (
    "요청하신 내용은 도와드릴 수 없어요. "
    "직업이나 진로에 관해 질문해 주세요."
)

# 입력 내용이 수정되어 원래 질문을 그대로 실행할 수 없을 때
INPUT_MODIFIED_REPLY = (
    "질문을 그대로 처리하기 어려워요. "
    "내용을 바꿔 다시 질문해 주세요."
)

# 출력이 차단되거나 수정됐을 때
OUTPUT_BLOCKED_REPLY = (
    "답변을 안전하게 확인하지 못해 보내지 않았어요. "
    "질문을 바꿔 다시 시도해 주세요."
)

# 검사 객체가 없거나 검사가 실패했을 때
GUARD_ERROR_REPLY = (
    "지금은 요청을 안전하게 처리할 수 없어요. "
    "잠시 후 다시 시도해 주세요."
)


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


# 워커(LLM)에 넘기는 회원 커리어 필드. 이메일·전화번호·주소·이름은 넘기지 않는다.
PROFILE_CAREER_FIELDS = (
    "current_job",
    "current_major",
    "current_certificate",
    "target_job",
    "target_major",
    "target_certificate",
)


def profile_career_lines(state: AgentState) -> str:
    """profile_node 가 SQLite 에서 읽은 본인 커리어만 "- 필드: 값" 줄로 만든다. 없으면 빈 문자열."""

    profile = state.get("user_profile") or {}
    return "\n".join(
        f"- {field}: {profile[field]}"
        for field in PROFILE_CAREER_FIELDS
        if profile.get(field)
    )


def build_profile_block(state: AgentState) -> str:
    """본인 커리어를 워커 지시문 블록으로 만든다. 없으면 빈 문자열."""

    lines = profile_career_lines(state)
    if not lines:
        return ""
    return (
        "Member career profile (selected member's saved data from the DB; "
        "use these values for 'my current/target job, major, certificate' "
        "instead of guessing from the conversation):\n"
        f"{lines}\n"
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
        f"{build_profile_block(state)}"
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


def reply_messages(text: str) -> list[AIMessage]:
    """사용자에게 보낸 최종 문장을 다음 턴 대화 기록에 남길 메시지로 만든다."""

    return [AIMessage(content=text)]


def stop_at_input_guard(
    state: AgentState,
    guard_status: str,
    rule_id: str | None,
    guard_error: str | None,
    reply: str,
    status: str,
) -> Command:
    """입력 검사에서 턴을 끝낸다. 안내 문장은 대화 기록에도 남긴다."""

    return Command(
        goto=END,
        update={
            "input_guard_status": guard_status,
            "input_guard_rule": rule_id,
            "input_guard_error": guard_error,
            "final_response": reply,
            "messages": reply_messages(reply),
            "status": status,
            "worker_trace": append_worker_trace(state, "input_guard"),
        },
    )


async def input_guard_node(
    state: AgentState,
    runtime: Runtime[ChatContext],
) -> Command[Literal["profile_check", "__end__"]]:
    """사용자 질문을 검사하고 통과한 경우에만 Graph RAG(profile_check)로 보낸다."""

    rails = runtime.context.rails
    question = state.get("question", "").strip()
    messages = state.get("messages", [])

    # 검사 객체, 질문 또는 메시지가 없으면 통과시키지 않는다.
    if rails is None or not question or not messages:
        return stop_at_input_guard(
            state, "error", None, "missing_input_or_rails", GUARD_ERROR_REPLY, "error",
        )

    # check_input()은 LangChain HumanMessage를 기대한다.
    # 마지막 메시지가 이번 질문과 동일한지 확인한다.
    last_message = messages[-1]
    if (
        getattr(last_message, "type", None) != "human"
        or getattr(last_message, "text", None) != question
    ):
        return stop_at_input_guard(
            state, "error", None, "invalid_input_message", GUARD_ERROR_REPLY, "error",
        )

    try:
        # 회원 접근 레일(member access input)이 비교할 수 있게 선택한 회원 ID를 함께 넘긴다.
        verdict = await check_input(
            rails=rails,
            messages=messages,
            selected_user_id=runtime.context.user_id,
        )
    except Exception:
        # 예외 원문에 민감한 내용이 섞일 수 있으므로 상태에는 오류 유형만 남긴다.
        return stop_at_input_guard(
            state, "error", None, "rail_execution_error", GUARD_ERROR_REPLY, "error",
        )

    guard_status = verdict.get("status")
    rule_id = verdict.get("rule_id") or None

    # rails.py는 규칙 표시가 없는 차단을 RAIL-ERROR로 바꾼다.
    # 실제 원인이 모호할 수 있으므로 오류로 처리한다.
    if rule_id == "RAIL-ERROR":
        return stop_at_input_guard(
            state, "error", rule_id, "unclassified_rail_error", GUARD_ERROR_REPLY, "error",
        )

    if guard_status == "passed":
        # 입력 검사를 통과한 질문만 Graph RAG 흐름(profile_check)으로 들어간다.
        return Command(
            goto="profile_check",
            update={
                "input_guard_status": "passed",
                "input_guard_rule": None,
                "input_guard_error": None,
                "worker_trace": append_worker_trace(state, "input_guard"),
            },
        )

    # AgentState.status에 "blocked"가 없으므로 에이전트 상태와 가드레일 상태를 분리한다.
    if guard_status == "blocked":
        return stop_at_input_guard(
            state, "blocked", rule_id, None, INPUT_BLOCKED_REPLY, "abstain",
        )

    if guard_status == "modified":
        return stop_at_input_guard(
            state, "modified", rule_id, None, INPUT_MODIFIED_REPLY, "abstain",
        )

    # 예상하지 못한 상태도 통과시키지 않는다.
    return stop_at_input_guard(
        state, "error", rule_id, "unknown_rail_status", GUARD_ERROR_REPLY, "error",
    )

def build_guard_documents(state: AgentState) -> str:
    """검색 근거와 조회한 본인 커리어를 출력 검사(사실 대조)에 전달할 문자열로 만든다."""

    documents = []

    # 답변이 DB 에서 읽은 본인 커리어(예: 목표 직업)를 말하면 사실 대조가 그 근거도 봐야 한다.
    career_lines = profile_career_lines(state)
    if career_lines:
        documents.append(f"[member_profile]\n{career_lines}")

    for evidence in state.get("evidence", []):
        evidence_id = evidence.get("evidence_id")
        content = evidence.get("content")

        if not content:
            continue

        if evidence_id:
            documents.append(f"[{evidence_id}]\n{content}")
        else:
            documents.append(str(content))

    return "\n\n".join(documents)


def finish_output_guard(
    state: AgentState,
    guard_status: str,
    rule_id: str | None,
    guard_error: str | None,
    reply: str,
    status: str | None,
) -> dict[str, Any]:
    """출력 검사 결과로 최종 응답을 정하고 대화 기록에 남긴다. status가 None이면 기존 상태를 둔다."""

    update = {
        "output_guard_status": guard_status,
        "output_guard_rule": rule_id,
        "output_guard_error": guard_error,
        "final_response": reply,
        "messages": reply_messages(reply),
        "worker_trace": append_worker_trace(state, "output_guard"),
    }
    if status is not None:
        update["status"] = status
    return update


async def output_guard_node(
    state: AgentState,
    runtime: Runtime[ChatContext],
) -> dict[str, Any]:
    """답변 후보를 출력 검사하고 통과한 문장만 최종 응답으로 만든다."""

    rails = runtime.context.rails
    candidate = (state.get("answer_draft") or "").strip()

    if rails is None or not candidate:
        return finish_output_guard(
            state, "error", None, "missing_output_or_rails", GUARD_ERROR_REPLY, "error",
        )

    # check_output()은 LangChain 메시지 목록을 받는다.
    # 검사할 답변을 AIMessage로 명시적으로 붙인다.
    # 이 목록은 검사에만 전달하며, 검사 전 초안을 state["messages"]에 추가하지 않는다.
    guard_messages = [
        *state.get("messages", []),
        AIMessage(content=candidate),
    ]

    documents_text = build_guard_documents(state)

    try:
        verdict = await check_output(
            rails=rails,
            messages=guard_messages,
            documents_text=documents_text,
        )
    except Exception:
        return finish_output_guard(
            state, "error", None, "rail_execution_error", GUARD_ERROR_REPLY, "error",
        )

    guard_status = verdict.get("status")
    rule_id = verdict.get("rule_id") or None

    if rule_id == "RAIL-ERROR":
        return finish_output_guard(
            state, "error", rule_id, "unclassified_rail_error", GUARD_ERROR_REPLY, "error",
        )

    if guard_status == "passed":
        # supported 또는 abstain 등 기존 상태는 그대로 둔다.
        return finish_output_guard(state, "passed", None, None, candidate, None)

    if guard_status in {"blocked", "modified"}:
        return finish_output_guard(
            state, guard_status, rule_id, None, OUTPUT_BLOCKED_REPLY, "abstain",
        )

    return finish_output_guard(
        state, "error", rule_id, "unknown_rail_status", GUARD_ERROR_REPLY, "error",
    )


def output_node(state: AgentState) -> dict[str, Any]:
    """검증된 답변 후보를 출력 가드레일로 넘긴다."""

    return {
        "worker": "end",
        "worker_trace": append_worker_trace(
            state,
            "output",
        ),
        # answer_draft는 기존 상태에 유지된다.
        # final_response는 output_guard_node가 설정한다.
    }

def abstain_node(state: AgentState) -> dict[str, Any]:
    """근거 부족 안내를 출력 가드레일에 넘긴다."""

    return {
        "answer_draft": "현재 자료만으로는 답변을 확정하기 어렵습니다.",
        "final_response": None,
        "status": "abstain",
        "worker": "end",
        "error": None,
        "worker_trace": append_worker_trace(
            state,
            "abstain",
        ),
    }