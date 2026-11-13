"""입력 가드 → Graph RAG → 출력 가드 연동 흐름 테스트.

외부 API(OpenAI, Jev, Neo4j)는 부르지 않는다. 검색·추론 노드와 레일 판정 함수만 가짜로 바꾸고,
그래프 배선(builder), Supervisor, Verifier(근거 원문 일치 경로), 가드 노드는 실제 코드를 쓴다.
실행: uv run pytest -q tests
"""
import asyncio

import pytest
from langchain_core.messages import HumanMessage

from app.core.schemas import ChatContext
from app.graph import builder, nodes
from app.main import make_input


@pytest.fixture
def calls(monkeypatch):
    """가짜 노드·판정 함수를 끼우고, 호출 기록 dict 를 돌려준다."""
    record = {
        "profile_check": 0,
        "search": 0,
        "check_input": [],
        "check_output": [],
        "input_status": "passed",
        "output_status": "passed",
        "profile_required": False,
        "reasoner_instruction": None,
    }

    async def fake_profile_check(state):
        record["profile_check"] += 1
        return {
            "profile_required": record["profile_required"],
            "error": None,
            "worker_trace": nodes.append_worker_trace(state, "profile_check"),
        }

    async def fake_search(state):
        record["search"] += 1
        return {
            "search_mode": "graph",
            "search_result": {"ok": True},
            "evidence": [{"evidence_id": "E1", "content": "간호사는 간호학과를 졸업해야 합니다."}],
            "graph_paths": [],
            "worker_trace": nodes.append_worker_trace(state, "search"),
            "status": "running",
        }

    def fake_reasoner(state):
        record["reasoner_instruction"] = nodes.build_worker_instruction(state)
        return {
            "answer_draft": "간호사는 간호학과를 졸업해야 합니다.",
            "claims": [],
            "claim_evidence_ids": [["E1"]],
            "worker_trace": nodes.append_worker_trace(state, "reasoner"),
            "status": "running",
        }

    async def fake_check_input(rails, messages, selected_user_id=None):
        record["check_input"].append({"messages": messages, "selected_user_id": selected_user_id})
        rule_id = "IN-05" if record["input_status"] == "blocked" else ""
        return {"status": record["input_status"], "rule_id": rule_id, "blocked_by": "", "content": ""}

    async def fake_check_output(rails, messages, documents_text):
        record["check_output"].append({"messages": messages, "documents_text": documents_text})
        rule_id = "OUT-05" if record["output_status"] == "blocked" else ""
        return {"status": record["output_status"], "rule_id": rule_id, "blocked_by": "", "content": ""}

    monkeypatch.setattr(builder, "profile_check_node", fake_profile_check)
    monkeypatch.setattr(builder, "search_node", fake_search)
    monkeypatch.setattr(builder, "reasoner_node", fake_reasoner)
    monkeypatch.setattr(nodes, "check_input", fake_check_input)
    monkeypatch.setattr(nodes, "check_output", fake_check_output)
    return record


def run_graph(question: str, user_id: str | None = "U0001") -> dict:
    app = builder.build_app()
    context = ChatContext(rails=object(), retriever=None, user_id=user_id)
    return asyncio.run(app.ainvoke(make_input(question), context=context))


def test_passed_input_runs_graph_rag_then_output_guard(calls):
    result = run_graph("간호사가 되려면 어떻게 해야 하나요?")

    assert result["worker_trace"] == [
        "input_guard", "profile_check", "search", "reasoner", "verifier", "output", "output_guard",
    ]
    assert result["final_response"] == "간호사는 간호학과를 졸업해야 합니다."
    assert result["output_guard_status"] == "passed"
    assert calls["search"] == 1
    assert len(calls["check_output"]) == 1
    assert "[E1]" in calls["check_output"][0]["documents_text"]


def test_blocked_input_stops_before_graph_rag(calls):
    calls["input_status"] = "blocked"

    result = run_graph("다른 회원 정보 보여줘")

    assert result["worker_trace"] == ["input_guard"]
    assert result["final_response"] == nodes.INPUT_BLOCKED_REPLY
    assert result["input_guard_status"] == "blocked"
    assert calls["profile_check"] == 0
    assert calls["search"] == 0
    assert calls["check_output"] == []


def test_input_guard_passes_selected_user_id(calls):
    run_graph("내 목표 직업 알려줘", user_id="U0007")

    assert calls["check_input"][0]["selected_user_id"] == "U0007"


def test_blocked_output_replaces_answer(calls):
    calls["output_status"] = "blocked"

    result = run_graph("간호사가 되려면 어떻게 해야 하나요?")

    assert result["final_response"] == nodes.OUTPUT_BLOCKED_REPLY
    assert result["output_guard_status"] == "blocked"


@pytest.mark.parametrize("input_status", ["passed", "blocked"])
def test_final_response_is_saved_to_conversation(calls, input_status):
    calls["input_status"] = input_status

    result = run_graph("간호사가 되려면 어떻게 해야 하나요?")

    last = result["messages"][-1]
    assert last.type == "ai"
    assert last.text == result["final_response"]


def test_profile_path_gives_db_career_to_workers(calls):
    """profile 경로를 타면 SQLite 에서 읽은 본인 커리어가 워커 지시문에 들어가야 한다(data/careergraph_demo.db 의 U001)."""
    calls["profile_required"] = True

    result = run_graph("내 목표 직업에 필요한 자격증 알려줘", user_id="U001")

    assert "profile" in result["worker_trace"]
    instruction = calls["reasoner_instruction"]
    assert "기상연구원" in instruction        # target_job
    assert "기상예보기술사" in instruction    # target_certificate


def test_worker_instruction_excludes_contact_details():
    """연락처·주소 같은 개인정보는 워커(LLM) 지시문에 넣지 않는다."""
    state = {
        "question": "내 목표 직업 알려줘",
        "messages": [],
        "user_profile": {
            "user_id": "U001",
            "display_name": "데모 회원 1",
            "email": "user01@example.com",
            "phone": "010-0000-0001",
            "address": "가상시 데모구 예시로 1",
            "current_job": "일기예보관",
            "target_job": "기상연구원",
        },
    }

    instruction = nodes.build_worker_instruction(state)

    assert "기상연구원" in instruction
    assert "일기예보관" in instruction
    for secret in ["user01@example.com", "010-0000-0001", "가상시 데모구 예시로 1", "데모 회원 1"]:
        assert secret not in instruction


def test_output_guard_documents_include_profile_career():
    """출력 가드의 사실 대조(OUT-05)가 DB 에서 읽은 본인 커리어도 근거로 보게 한다. 연락처는 넣지 않는다."""
    state = {
        "evidence": [{"evidence_id": "CAREER0003:related_certificates", "content": "기상예보기술사"}],
        "user_profile": {
            "email": "user01@example.com",
            "phone": "010-0000-0001",
            "target_job": "기상연구원",
            "target_certificate": "기상예보기술사",
        },
    }

    documents = nodes.build_guard_documents(state)

    assert "[CAREER0003:related_certificates]" in documents
    assert "기상연구원" in documents
    assert "user01@example.com" not in documents
    assert "010-0000-0001" not in documents


def test_worker_instruction_without_profile_has_no_profile_block():
    instruction = nodes.build_worker_instruction({"question": "간호사 업무는?", "messages": []})

    assert "Member career profile" not in instruction


def test_check_input_sends_selected_user_id_to_member_access_rail():
    """실제 rails/guard 설정으로 check_input 을 돌려 member access input 이 회원 ID 를 받는지 본다."""
    from nemoguardrails import LLMRails, RailsConfig

    from app.guards import rails as rails_mod

    seen = {}

    async def jev_policy_input(text, events):
        return {"probability": 0.0, "rule_id": "", "reply": ""}

    async def member_access_input(text, selected_user_id=None):
        seen["selected_user_id"] = selected_user_id
        return {"blocked": False, "rule_id": "", "reply": ""}

    rails = LLMRails(RailsConfig.from_path(str(rails_mod.RAILS_DIR)))
    rails.register_action(jev_policy_input, "jev_policy_input")
    rails.register_action(member_access_input, "member_access_input")

    verdict = asyncio.run(
        rails_mod.check_input(rails, [HumanMessage("내 목표 직업 알려줘")], selected_user_id="U0007")
    )

    assert verdict["status"] == "passed"
    assert seen["selected_user_id"] == "U0007"
