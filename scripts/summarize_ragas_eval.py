"""Summarize a completed CareerGraph RAGAS run without API calls."""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("faithfulness", "answer_relevancy", "answer_relevancy_ko", "context_precision", "context_recall")


def read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def read_jsonl(path: Path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fmt(metric):
    return f"{metric['mean']:.3f} (n={metric['n']})" if metric.get("mean") is not None else "N/A"


def error_count(group):
    execution = set(group.get("execution_errors", []))
    output = set(group.get("output_guard_error_ids", []))
    if output:
        return len(execution | output)
    # Older analysis files stored only the output-guard count, not its IDs.
    # Add those errors while avoiding double-counting IDs already in execution.
    return len(execution) + max(0, group.get("output_guard_counts", {}).get("error", 0) - len(output))


def write_report(folder, records, scores, cases, stats, baseline_path):
    """Write a complete report from the measured run; no folder-name branching."""

    current = stats["basic"]
    baseline_data = read_json(baseline_path, {})
    baseline = baseline_data.get("basic")

    def metric(group, name):
        values = group.get("metrics", {})
        if name == "answer_relevancy":
            korean = values.get("answer_relevancy_ko")
            if korean and korean.get("mean") is not None:
                return korean
        return values.get(name) or {"mean": None, "n": 0}

    def change(before, after, label):
        if before is None or after is None:
            return f"- {label}: 비교 불가 (N/A)"
        if after > before + 0.005:
            state = "개선"
        elif after < before - 0.005:
            state = "하락"
        else:
            state = "유사"
        return f"- {label}: {state} ({before:.3f} -> {after:.3f})"

    manifest = read_json(folder / "manifest.json", {})
    lines = [
        "CareerGraph RAGAS 평가 보고서", "", f"실행 폴더: {folder.name}",
        "실행 설정", json.dumps(manifest, ensure_ascii=False, indent=2), "",
        "평가 기준 및 주의사항",
        "- 근거충돌_가상 30문항은 실행 대상에서 제외했습니다.",
        "- 고난도 30문항은 탐색용 초안이며 정식 점수와 분리했습니다.",
        "- 근거부족 문항은 올바르게 보류해도 Answer Relevancy가 낮게 측정될 수 있습니다.",
        "- 근거가 없는 문항의 RAGAS 점수는 0이 아니라 N/A로 처리했습니다.", "",
    ]
    if baseline:
        lines += [
            "초기 실행 대비 현재 실행",
            change(baseline.get("job_recall", {}).get("mean"), current.get("job_recall", {}).get("mean"), "Job Recall"),
            change(metric(baseline, "context_recall").get("mean"), metric(current, "context_recall").get("mean"), "Context Recall"),
            change(metric(baseline, "context_precision").get("mean"), metric(current, "context_precision").get("mean"), "Context Precision"),
            change(metric(baseline, "faithfulness").get("mean"), metric(current, "faithfulness").get("mean"), "Faithfulness"),
            change(metric(baseline, "answer_relevancy").get("mean"), metric(current, "answer_relevancy").get("mean"), "Answer Relevancy(실행별 기준)"),
            f"- 고난도 실행·출력 가드 오류: {error_count(baseline_data.get('hard_draft', {}))} -> {error_count(stats['hard_draft'])}",
            f"- 기본 문항 빈 근거: {len(baseline.get('no_retrieved_context_ids', []))} -> {len(current.get('no_retrieved_context_ids', []))}",
            f"- 기본 문항 잘못된 근거 ID: {len(baseline.get('invalid_citations', []))} -> {len(current.get('invalid_citations', []))}", "",
            "비교 해석",
            change(metric(baseline, "context_recall").get("mean"), metric(current, "context_recall").get("mean"), "검색 근거 재현율"),
            change(metric(baseline, "context_precision").get("mean"), metric(current, "context_precision").get("mean"), "검색 근거 정밀도"),
            change(metric(baseline, "faithfulness").get("mean"), metric(current, "faithfulness").get("mean"), "답변 충실도"),
            "- 관련성은 answer_relevancy_ko가 있으면 우선 사용하고, 없으면 answer_relevancy를 사용했습니다.", "",
        ]
    lines += [
        "현재 실행 점검",
        f"- 실행 오류: {current['execution_errors']}",
        f"- 출력 가드 오류: {current['output_guard_error_ids']}",
        f"- 빈 근거: {current['no_retrieved_context_ids']}",
        f"- 잘못된 근거 ID: {current['invalid_citations']}", "",
        "카테고리별 결과",
        "| 카테고리 | 실행/전체 | 충실도 | 관련성(실행별 기준) | 정밀도 | 재현율 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for category, group in stats["by_category"].items():
        lines.append("| " + " | ".join([
            category, f"{group['live_n']}/{group['dataset_n']}",
            fmt(metric(group, "faithfulness")), fmt(metric(group, "answer_relevancy")),
            fmt(metric(group, "context_precision")), fmt(metric(group, "context_recall")),
        ]) + " |")
        lines.append(f"  상태: {group['state_counts']} | 입력 가드: {group['input_guard_counts']} | 출력 가드: {group['output_guard_counts']}")

    answer_tasks = stats["basic_answer_tasks"]
    lines += [
        "", "일반 답변 120문항 요약",
        f"- 충실도: {fmt(metric(answer_tasks, 'faithfulness'))}",
        f"- 관련성: {fmt(metric(answer_tasks, 'answer_relevancy'))}",
        f"- 정밀도: {fmt(metric(answer_tasks, 'context_precision'))}",
        f"- 재현율: {fmt(metric(answer_tasks, 'context_recall'))}",
        "", "점수가 낮은 사례",
    ]
    scored = [
        (scores[row["id"]]["metrics"].get("faithfulness"), row)
        for row in records
        if row["id"] in scores and scores[row["id"]].get("metrics", {}).get("faithfulness") is not None and row["id"] in cases
    ]
    for score, row in sorted(scored, key=lambda item: item[0])[:12]:
        lines.append(f"- {row['id']} | {row.get('category', '')} | Faithfulness={score:.3f} | {row.get('question', '')}")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(output, baseline):
    folder = ROOT / output
    records = read_jsonl(folder / "agent_results.jsonl")
    if not records:
        raise SystemExit("agent_results.jsonl이 없어 새 RAGAS 보고서를 생성할 수 없습니다.")
    score_path = next((folder / name for name in ("ragas_scores_final.jsonl", "ragas_scores_with_metadata.jsonl", "ragas_scores.jsonl") if (folder / name).exists()), folder / "ragas_scores.jsonl")
    scores = {row["id"]: row for row in read_jsonl(score_path)}
    for item in read_json(folder / "korean_relevancy_calibration.json", {}).get("results", []):
        if "korean_question_answer_relevancy" in item:
            scores.setdefault(item["id"], {"metrics": {}})["metrics"]["answer_relevancy_ko"] = item["korean_question_answer_relevancy"]

    cases = {}
    for name in ("evaluation_draft.json", "evaluation_hard.json"):
        cases.update({row["id"]: row for row in read_json(ROOT / "eval" / name, [])})
    row_to_code = {row["row_id"]: str(row["job_code"]) for row in read_json(ROOT / "data/expanded_20261108/jobs.json", [])}

    def aggregate(rows):
        live = [row for row in rows if not row.get("skipped")]
        ok = [row for row in live if not row.get("execution_error") and row.get("status") != "error"]
        metrics = {}
        for metric_name in METRICS:
            values = [scores.get(row["id"], {}).get("metrics", {}).get(metric_name) for row in ok]
            values = [value for value in values if value is not None]
            metrics[metric_name] = {"mean": mean(values) if values else None, "n": len(values)}
        recalls, invalid = [], []
        for row in ok:
            case = cases[row["id"]]
            found = set()
            for evidence in row.get("evidence") or []:
                metadata = evidence.get("metadata") or {}
                if metadata.get("job_code") is not None:
                    found.add(str(metadata["job_code"]))
                evidence_row_id = str(evidence.get("evidence_id", "")).split(":")[0]
                if evidence_row_id in row_to_code:
                    found.add(row_to_code[evidence_row_id])
            expected = set(map(str, case.get("expected_job_codes", [])))
            if expected and not row["id"].startswith("HARD"):
                recalls.append(len(found & expected) / len(expected))
            available = {evidence.get("evidence_id") for evidence in row.get("evidence") or []}
            cited = {eid for group in row.get("claim_evidence_ids") or [] for eid in group}
            if cited - available:
                invalid.append({"id": row["id"], "invalid_ids": sorted(cited - available)})
        mode_rows = [row for row in ok if cases.get(row["id"], {}).get("expected_search_mode")]
        guard_rows = [row for row in ok if "guard_expectation_met" in row]
        return {
            "dataset_n": len(rows), "live_n": len(live), "skipped_n": len(rows) - len(live),
            "execution_errors": [row["id"] for row in live if row.get("execution_error")],
            "output_guard_error_ids": [row["id"] for row in live if row.get("output_guard_status") == "error"],
            "state_counts": dict(Counter(row.get("status") for row in ok)),
            "input_guard_counts": dict(Counter(row.get("input_guard_status") for row in ok)),
            "output_guard_counts": dict(Counter(row.get("output_guard_status") for row in ok)),
            "mode_match": {"hits": sum(bool(row.get("mode_match")) for row in mode_rows), "n": len(mode_rows)},
            "guard_expectation": {"hits": sum(bool(row["guard_expectation_met"]) for row in guard_rows), "n": len(guard_rows)},
            "job_recall": {"mean": mean(recalls) if recalls else None, "n": len(recalls)},
            "invalid_citations": invalid,
            "no_retrieved_context_ids": [row["id"] for row in ok if cases.get(row["id"], {}).get("expected_guardrail_action") == "allow" and not row.get("evidence")],
            "median_latency_s": median(row["elapsed_seconds"] for row in live) if live else None,
            "metrics": metrics,
            "metric_errors": dict(Counter(value for row in rows for value in scores.get(row["id"], {}).get("metric_errors", {}).values())),
        }

    grouped = defaultdict(list)
    for row in records:
        grouped[row["category"]].append(row)
    stats = {
        "basic": aggregate([row for row in records if not row["id"].startswith("HARD")]),
        "basic_answer_tasks": aggregate([row for row in records if not row["id"].startswith("HARD") and cases.get(row["id"], {}).get("expected_outcome") == "answer" and cases.get(row["id"], {}).get("expected_guardrail_action") == "allow"]),
        "hard_draft": aggregate([row for row in records if row["id"].startswith("HARD")]),
        "by_category": {category: aggregate(rows) for category, rows in grouped.items()},
    }
    (folder / "analysis.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    baseline_path = ROOT / baseline
    if baseline_path.is_dir():
        baseline_path = baseline_path / "analysis.json"
    write_report(folder, records, scores, cases, stats, baseline_path)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="output/eval/ragas_20261115_fallback")
    parser.add_argument("--baseline", default="output/eval/ragas_20261115_full")
    args = parser.parse_args()
    main(args.output, args.baseline)


