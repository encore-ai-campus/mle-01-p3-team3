"""검색 방식별(벡터 단독 / 그래프 / 하이브리드) 검색 근거 비교와 질문별 검색 경로 테스트.

같은 평가 질문으로 세 방식을 강제로 실행해 정답 근거(eval/evaluation_draft.json 의 evidence)를 얼마나 찾는지 잰다.
- vector : vector_search 도구만 직접 호출한다(질문을 그대로 임베딩). 그래프 단계 없음 = 벡터 단독 기준선
- graph / hybrid : Jev 분류를 해당 방식으로 고정하고 실제 검색 워커(run_jev_search, GPT 가 도구 인자를 작성)를 실행한다
- system : 라우터가 직접 고른 방식 + CRAG 평가·재작성을 거친 실제 그래프의 최종 근거(RAGAS 실행 결과 agent_results.jsonl)

지표(질문 하나당, 대상 직업의 정답 근거 ID 기준)
- job_recall      : 정답 직업(row_id)이 검색 근거에 하나라도 나온 직업의 비율
- evidence_recall : 정답 근거 ID(예: CAREER0131:core_abilities) 중 검색된 비율
- hit_all         : 정답 근거를 모두 찾은 질문 비율

실행(프로젝트 루트): python scripts/compare_search_modes.py [--ragas-dir output/eval/ragas_20261116_crag]
결과: eval/search_modes/ 아래 comparison.json, comparison_rows.csv, route_test.csv (경로 테스트표는 RAGAS 가 채점한 138문항 전체)
OpenAI 를 질문당 최대 2회 부른다(검색 인자 작성). Jev 분류 호출은 고정하므로 없다.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.graph import nodes  # noqa: E402
from app.main import make_input  # noqa: E402
from app.router import jev_router  # noqa: E402
from app.tools.search import _vector_search  # noqa: E402

CATEGORIES = ("일반", "Multi-hop", "관계비교")
OUT = ROOT / "eval" / "search_modes"


def expected_ids(case: dict) -> set[str]:
    return {item["evidence_id"] for item in case.get("evidence", [])}


def expected_jobs(case: dict) -> set[str]:
    return {item["row_id"] for item in case.get("expected_entities", {}).get("jobs", [])}


def found_ids(evidence: list[dict]) -> set[str]:
    return {str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")}


def job_of(evidence_id: str) -> str:
    return evidence_id.split(":", 1)[0]


def score(case: dict, evidence: list[dict]) -> dict:
    want, got = expected_ids(case), found_ids(evidence)
    jobs = expected_jobs(case)
    found_jobs = {job_of(i) for i in got}
    return {
        "n_evidence": len(evidence),
        "job_recall": len(jobs & found_jobs) / len(jobs) if jobs else None,
        "evidence_recall": len(want & got) / len(want) if want else None,
        "hit_all": bool(want) and want <= got,
    }


async def run_forced(mode: str, case: dict) -> tuple[list[dict], str]:
    """Jev 분류를 mode 로 고정하고 실제 검색 워커를 실행한다. (근거, 오류) 를 돌려준다."""
    state = {**make_input(case["question"]), "user_profile": {}, "worker_trace": [], "retry_count": 0}

    async def fixed(_state):
        return mode

    original = jev_router.classify_search
    jev_router.classify_search = fixed
    try:
        messages = nodes.build_worker_messages(state, "search")
        data = await jev_router.run_jev_search(state=state, worker_messages=messages)
        return data.get("evidence", []), ""
    except Exception as exc:  # noqa: BLE001 - 실패도 결과로 남긴다
        return [], type(exc).__name__
    finally:
        jev_router.classify_search = original


async def main(args) -> None:
    all_cases = json.loads((ROOT / "eval" / "evaluation_draft.json").read_text(encoding="utf-8"))
    cases = [c for c in all_cases if c["category"] in CATEGORIES]
    ragas = {}
    path = ROOT / args.ragas_dir / "agent_results.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            ragas.setdefault(row["id"], row)

    sem = asyncio.Semaphore(args.concurrency)
    rows: list[dict] = []

    async def one(case: dict, mode: str):
        async with sem:
            error = ""
            if mode == "vector":
                try:
                    evidence = await asyncio.to_thread(_vector_search, case["question"], 5)
                except Exception as exc:  # noqa: BLE001
                    evidence, error = [], type(exc).__name__
            elif mode == "system":
                row = ragas.get(case["id"])
                if not row or row.get("status") is None:
                    return
                evidence = row.get("evidence") or []
            else:
                evidence, error = await run_forced(mode, case)
        rows.append({"id": case["id"], "category": case["category"], "mode": mode, "error": error,
                     **score(case, evidence)})

    OUT.mkdir(parents=True, exist_ok=True)
    if not args.route_only:
        await asyncio.gather(*(one(c, m) for c in cases for m in ("vector", "graph", "hybrid", "system")))
        rows.sort(key=lambda r: (r["category"], r["id"], r["mode"]))
        with (OUT / "comparison_rows.csv").open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    summary: dict = defaultdict(dict)
    for category in () if args.route_only else CATEGORIES:
        for mode in ("vector", "graph", "hybrid", "system"):
            part = [r for r in rows if r["category"] == category and r["mode"] == mode]
            if not part:
                continue
            def avg(key):
                values = [r[key] for r in part if r[key] is not None]
                return round(sum(values) / len(values), 3) if values else None
            summary[category][mode] = {
                "n": len(part), "errors": sum(bool(r["error"]) for r in part),
                "job_recall": avg("job_recall"), "evidence_recall": avg("evidence_recall"),
                "hit_all": round(sum(r["hit_all"] for r in part) / len(part), 3),
                "mean_evidence": round(sum(r["n_evidence"] for r in part) / len(part), 1),
            }
    if not args.route_only:
        (OUT / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 질문별 검색 경로 테스트: 기대 경로 vs 실제 경로(라우터 선택, fallback, CRAG 재작성)
    route_rows = []
    for case in all_cases:
        row = ragas.get(case["id"])
        if not row or row.get("status") is None:
            continue
        history = row.get("search_history") or []
        route_rows.append({
            "id": case["id"], "category": case["category"], "question": case["question"],
            "expected_mode": case.get("expected_search_mode"), "actual_mode": row.get("search_mode"),
            "match": case.get("expected_search_mode") == row.get("search_mode"),
            "rewrites": row.get("rewrite_count") or 0, "decision": row.get("retrieval_decision"),
            "grade_modes": ">".join(str(h.get("search_mode")) for h in history),
            "final_status": row.get("status"),
        })
    with (OUT / "route_test.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(route_rows[0]))
        writer.writeheader()
        writer.writerows(route_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(Counter((r["expected_mode"], r["actual_mode"]) for r in route_rows))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ragas-dir", default="output/eval/ragas_20261116_crag")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--route-only", action="store_true", help="강제 실행 없이 RAGAS 결과로 검색 경로 테스트표만 다시 만든다")
    asyncio.run(main(parser.parse_args()))
