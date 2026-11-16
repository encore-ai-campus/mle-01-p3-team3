"""직업명 정확 일치 보강(search._merge_exact_first) 테스트. Neo4j, OpenAI 는 부르지 않는다."""
from app.tools import search


def row(job_code: str, name: str, score: float) -> dict:
    return {
        "node_id": f"job:{job_code}", "job_code": job_code, "job_name": name,
        "work": f"{name}의 업무 설명", "source_field": "work", "source": "career_api", "score": score,
    }


def test_exact_name_match_comes_first_and_is_not_duplicated():
    vector = [row("1", "시장 및 여론조사전문가", 0.72), row("25", "전문의사", 0.70), row("2", "기자", 0.69)]
    exact = [row("25", "전문의사", 1.0)]

    merged = search._merge_exact_first(exact, vector, top_k=3)

    names = [item["metadata"]["job_name"] for item in merged]
    assert names[0] == "전문의사"
    assert names.count("전문의사") == 1
    assert len(merged) == 3


def test_without_exact_match_vector_order_is_kept():
    vector = [row("1", "한의사", 0.75), row("2", "치과의사", 0.74)]

    merged = search._merge_exact_first([], vector, top_k=5)

    assert [item["metadata"]["job_name"] for item in merged] == ["한의사", "치과의사"]


def test_exact_name_failure_does_not_break_vector_search(monkeypatch):
    class FakeEmbedding:
        def embed_query(self, _question):
            return [0.0]

    monkeypatch.setattr(search, "embedding_model", FakeEmbedding())
    calls = []

    def fake_read(query, **_params):
        calls.append(query)
        if "CONTAINS" in query:
            raise RuntimeError("name lookup failed")
        return [row("1", "한의사", 0.75)]

    monkeypatch.setattr(search, "_run_read_query", fake_read)

    result = search._vector_search("한의사는 무슨 일을 하나요?", 5)

    assert [item["metadata"]["job_name"] for item in result] == ["한의사"]
    assert len(calls) == 2
