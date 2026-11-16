"""CRAG 근거 평가·근거 병합·Supervisor 분기 단위 테스트. 외부 API는 부르지 않는다."""
import asyncio

import pytest

from app.graph import crag, nodes
from app.graph.crag import RetrievalReview, grade_evidence, merge_evidence

JOB_WORK = {"evidence_id": "C1:work", "content": "환자를 간호한다.", "source": "aura"}
JOB_CERT = {"evidence_id": "C1:related_certificates", "content": "간호사 면허", "source": "aura"}
OTHER = {"evidence_id": "C9:work", "content": "건물을 설계한다.", "source": "aura"}
PROFILE = {"evidence_id": "profile:U1:target_job", "content": "target_job: 간호사", "source": "sqlite_profile"}


class FakeChain:
    def __init__(self, result):
        self.result = result

    async def ainvoke(self, _):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def grade_with(monkeypatch, result, candidates):
    monkeypatch.setattr(crag, "get_grade_chain", lambda: FakeChain(result))
    return asyncio.run(grade_evidence("간호사 업무와 자격", candidates))


def test_merge_evidence_keeps_previous_and_dedupes():
    merged = merge_evidence([JOB_WORK], [JOB_WORK, JOB_CERT])
    assert [item["evidence_id"] for item in merged] == ["C1:work", "C1:related_certificates"]


def test_grade_keeps_useful_and_profile_evidence(monkeypatch):
    review = RetrievalReview(useful_ids=["[C1:work]", "C1:related_certificates"], sufficient=True, missing_info="")
    kept, decision, missing = grade_with(monkeypatch, review, [JOB_WORK, JOB_CERT, OTHER, PROFILE])

    assert decision == "correct"
    assert missing == ""
    assert [item["evidence_id"] for item in kept] == ["C1:work", "C1:related_certificates", PROFILE["evidence_id"]]


def test_grade_unknown_id_blocks_sufficient(monkeypatch):
    review = RetrievalReview(useful_ids=["C1:work", "MADE-UP"], sufficient=True, missing_info="")
    kept, decision, missing = grade_with(monkeypatch, review, [JOB_WORK, OTHER])

    assert decision == "ambiguous"
    assert [item["evidence_id"] for item in kept] == ["C1:work"]
    assert "후보 밖" in missing


def test_grade_nothing_useful_is_incorrect(monkeypatch):
    review = RetrievalReview(useful_ids=[], sufficient=False, missing_info="간호사 자격")
    kept, decision, missing = grade_with(monkeypatch, review, [OTHER])

    assert (kept, decision, missing) == ([], "incorrect", "간호사 자격")


def test_grade_failure_keeps_all_evidence(monkeypatch):
    kept, decision, _ = grade_with(monkeypatch, RuntimeError("api down"), [JOB_WORK, OTHER])
    assert decision == "correct"
    assert kept == [JOB_WORK, OTHER]


def test_grade_without_candidates_skips_model(monkeypatch):
    monkeypatch.setattr(crag, "get_grade_chain", lambda: pytest.fail("모델을 부르면 안 됩니다"))
    assert asyncio.run(grade_evidence("질문", [])) == ([], "incorrect", "검색된 근거가 없습니다.")


def supervise(**state):
    base = {"question": "q", "search_result": {"ok": True}, "answer_draft": None, "evidence": []}
    return nodes.supervisor_node({**base, **state})


@pytest.mark.parametrize("state, goto, status", [
    ({"retrieval_decision": "correct"}, "reasoner", None),
    ({}, "reasoner", None),  # grade를 거치지 않은 상태는 기존처럼 답변
    ({"retrieval_decision": "ambiguous", "rewrite_count": 0}, "rewrite", None),
    ({"retrieval_decision": "ambiguous", "rewrite_count": 1, "evidence": [JOB_WORK]}, "reasoner", "partial"),
    ({"retrieval_decision": "incorrect", "rewrite_count": 1}, "abstain", "abstain"),
    ({"retrieval_decision": "incorrect", "rewrite_count": 1, "evidence": [PROFILE]}, "abstain", "abstain"),
])
def test_supervisor_routes_by_grade(state, goto, status):
    command = supervise(**state)
    assert command.goto == goto
    assert command.update.get("status") == status


def test_verifier_retry_rewrites_without_clearing_evidence():
    command = supervise(
        answer_draft="초안", evidence=[JOB_WORK], retrieval_decision="correct",
        verification_result={"status": "insufficient"}, verification_feedback="자격 근거 부족",
    )
    assert command.goto == "rewrite"
    assert "evidence" not in command.update
    assert command.update["missing_info"] == "자격 근거 부족"
    assert command.update["answer_draft"] is None


def test_verified_answer_after_partial_grade_is_partial():
    command = supervise(
        answer_draft="초안", retrieval_decision="ambiguous", verification_result={"status": "supported"},
    )
    assert command.goto == "output"
    assert command.update["status"] == "partial"


def test_grade_accepts_job_code_without_field(monkeypatch):
    # 실제 모델이 'C1:work' 대신 'C1'만 반환한 사례
    review = RetrievalReview(useful_ids=["C1"], sufficient=False, missing_info="간호사 자격")
    kept, decision, _ = grade_with(monkeypatch, review, [JOB_WORK, JOB_CERT, OTHER])

    assert decision == "ambiguous"
    assert {item["evidence_id"] for item in kept} == {"C1:work", "C1:related_certificates"}
