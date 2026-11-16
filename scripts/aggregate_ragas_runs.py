"""같은 코드로 반복 실행한 RAGAS 결과(scripts/run_ragas_eval.py 출력 폴더 여러 개)의 평균과 표준편차를 낸다.

사용: python scripts/aggregate_ragas_runs.py output/eval/ragas_repeat_1 output/eval/ragas_repeat_2 ... [--out eval/ragas_repeats.json]
- 지표별·카테고리별: 실행마다 평균을 낸 뒤 그 값들의 평균과 표준편차(표본, n-1)를 보고한다
- 문항별 안정성: 실행 간 최종 상태가 달라진 문항 수, 항상 같은 상태였던 문항 수
"""
import argparse
import collections
import json
import math
import statistics as st
from pathlib import Path

METRICS = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")
ROOT = Path(__file__).resolve().parents[1]


def load(folder: Path):
    agent, scores = {}, {}
    for line in (folder / "agent_results.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        agent.setdefault(row["id"], row)
    for line in (folder / "ragas_scores.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        scores.setdefault(row["id"], row)
    return agent, scores


def mean_of(values):
    values = [v for v in values if isinstance(v, (int, float)) and math.isfinite(v)]
    return (sum(values) / len(values)) if values else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folders", nargs="+")
    parser.add_argument("--out", default="eval/ragas_repeats.json")
    args = parser.parse_args()
    runs = [load(ROOT / folder) for folder in args.folders]
    graded = [i for i, r in runs[0][0].items() if r.get("status") is not None]
    categories = sorted({runs[0][0][i]["category"] for i in graded}, key=lambda c: ["일반", "Multi-hop", "관계비교", "근거부족", "안전_정상허용"].index(c) if c in ["일반", "Multi-hop", "관계비교", "근거부족", "안전_정상허용"] else 9)

    result = {"runs": args.folders, "n_questions": len(graded), "groups": {}}
    for category in [None, *categories]:
        ids = [i for i in graded if category is None or runs[0][0][i]["category"] == category]
        group = {"n": len(ids)}
        for metric in METRICS:
            per_run = [mean_of([sc.get(i, {}).get("metrics", {}).get(metric) for i in ids]) for _, sc in runs]
            per_run = [v for v in per_run if v is not None]
            group[metric] = {
                "per_run": [round(v, 3) for v in per_run],
                "mean": round(st.mean(per_run), 3),
                "sd": round(st.stdev(per_run), 3) if len(per_run) > 1 else None,
            }
        statuses = [collections.Counter(ag[i]["status"] for i in ids) for ag, _ in runs]
        group["status_per_run"] = [dict(c) for c in statuses]
        result["groups"][category or "전체"] = group

    flips = []
    for i in graded:
        seen = [ag[i].get("status") for ag, _ in runs]
        if len(set(seen)) > 1:
            flips.append({"id": i, "category": runs[0][0][i]["category"], "statuses": seen})
    result["status_flips"] = flips
    result["status_stable"] = len(graded) - len(flips)
    latencies = [[ag[i]["elapsed_seconds"] for i in graded if "elapsed_seconds" in ag[i]] for ag, _ in runs]
    result["latency_mean_s"] = [round(st.mean(x), 1) for x in latencies]
    # 문항별 Faithfulness 편차: 실행마다 크게 달라지는 문항
    unstable = []
    for i in graded:
        values = [sc.get(i, {}).get("metrics", {}).get("faithfulness") for _, sc in runs]
        values = [v for v in values if isinstance(v, (int, float))]
        if len(values) > 1 and max(values) - min(values) >= 0.3:
            unstable.append({"id": i, "category": runs[0][0][i]["category"], "faithfulness": [round(v, 2) for v in values]})
    result["faithfulness_unstable"] = unstable
    out = ROOT / args.out
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
