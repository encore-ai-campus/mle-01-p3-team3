"""현재 에이전트의 독립 단일턴 실행과 RAGAS 0.4 평가. 원본 데이터/DB는 수정하지 않는다."""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import logging
import math
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.core.schemas import ChatContext
from app.graph.builder import build_app
from app.guards.rails import build_rails
from app.main import make_input


def korean_answer_relevancy(llm, embeddings):
    """한국어 질문·답변을 영어 역질문으로 바꾸지 않고 평가한다."""
    from ragas.metrics.collections import AnswerRelevancy

    metric = AnswerRelevancy(llm=llm, embeddings=embeddings)
    metric.prompt.instruction += (
        "\nThe user input and response are Korean. Generate the reverse question in Korean, "
        "preserving Korean occupation, major, ability, and certificate names. "
        "Judge relevance against the original Korean user input."
    )
    return metric


def dump(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_cases():
    cases = []
    for filename in ("evaluation_draft.json", "evaluation_hard.json"):
        path = ROOT / "eval" / filename
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding="utf-8")):
            cases.append({**item, "dataset": filename})
    return cases


def mean(values):
    values = [v for v in values if isinstance(v, (float, int)) and math.isfinite(v)]
    return sum(values) / len(values) if values else None


async def main(args):
    logging.basicConfig(level=logging.ERROR)
    out = ROOT / args.output
    out.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    if args.basic_only:
        cases = [case for case in cases if case["dataset"] == "evaluation_draft.json"]
    if args.hard_only:
        cases = [case for case in cases if case["dataset"] == "evaluation_hard.json"]
    if args.rag_only:
        cases = [case for case in cases if case.get("expected_guardrail_action") == "allow"]
    if args.limit:
        cases = cases[:args.limit]
    by_id = {case["id"]: case for case in cases}
    source_hash = hashlib.sha256(b"".join(
        p.read_bytes() for p in sorted((ROOT / "app").rglob("*.py"))
    )).hexdigest()
    fingerprints = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [ROOT / "eval/evaluation_draft.json", ROOT / "eval/evaluation_hard.json"]
        if p.exists()
    }
    manifest = {
        "application_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "application_sha256": source_hash,
        "dataset_sha256": fingerprints,
        "agent_model": settings.openai_chat_model,
        "jev_model": settings.typesafe_model,
        "evaluator_model": settings.openai_eval_model,
        "ragas_version": "0.4.3", "user_id": "U001",
        "isolated_turns": True, "guardrails_enabled": True,
        "synthetic_fixture_injection": False,
        "concurrency": args.concurrency,
    }
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
        raise RuntimeError("Existing output uses a different configuration; choose another --output")
    dump(manifest_path, manifest)
    records = {}
    record_path = out / "agent_results.jsonl"
    if record_path.exists():
        for line in record_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            records[row["id"]] = row
    graph = build_app()
    context = ChatContext(rails=build_rails(), retriever=None, user_id="U001")
    sem = asyncio.Semaphore(args.concurrency)

    async def run_case(case):
        if case["id"] in records:
            return
        async with sem:
            start = time.perf_counter()
            row = {"id": case["id"], "dataset": case["dataset"], "category": case["category"],
                   "question": case["question"], "reference": case["reference_answer"]}
            if case.get("synthetic_fixture"):
                row.update(skipped="requires_synthetic_fixture_injection")
            else:
                try:
                    result = await asyncio.wait_for(graph.ainvoke(
                        make_input(case["question"]), context=context,
                        config={"recursion_limit": 50},
                    ), timeout=args.timeout)
                    for field in ("final_response", "status", "search_mode", "worker_trace", "evidence",
                                  "graph_paths", "retry_count", "verification_result", "claim_evidence_ids",
                                  "input_guard_status", "input_guard_rule", "input_guard_error",
                                  "output_guard_status", "output_guard_rule", "output_guard_error", "error",
                                  "retrieval_decision", "rewrite_count", "search_history"):
                        row[field] = result.get(field)
                    expected_guard = case.get("expected_guardrail_action")
                    row["guard_expectation_met"] = (
                        row["input_guard_status"] == "blocked" if expected_guard in {"block", "redirect"}
                        else row["input_guard_status"] == "passed"
                    )
                    row["mode_match"] = row["search_mode"] == case.get("expected_search_mode")
                except Exception as exc:
                    # API 예외 원문 대신 오류 유형만 저장한다.
                    row["execution_error"] = type(exc).__name__
            row["elapsed_seconds"] = round(time.perf_counter() - start, 3)
            records[row["id"]] = row
            with record_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            print(f"agent {len(records)}/{len(cases)} {row['id']} status={row.get('status', row.get('skipped', row.get('execution_error')))}", flush=True)

    # First case is a live connectivity check; no mock nodes are installed.
    pending = [case for case in cases if case["id"] not in records]
    if pending:
        await run_case(pending[0])
        probe = records[pending[0]["id"]]
        if probe.get("execution_error") or probe.get("input_guard_error"):
            print("Live probe failed; stopping further agent calls.", flush=True)
        else:
            await asyncio.gather(*(run_case(case) for case in pending[1:]))

    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.embeddings.base import embedding_factory
    from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall

    score_path = out / "ragas_scores.jsonl"
    scores = {}
    if score_path.exists():
        scores = {row["id"]: row for row in map(json.loads, score_path.read_text(encoding="utf-8").splitlines())}
    client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value(), timeout=60, max_retries=1)
    llm = llm_factory(settings.openai_eval_model, client=client)
    embeddings = embedding_factory("openai", model="text-embedding-3-small", client=client)

    async def score(row):
        if row["id"] in scores:
            return
        async with sem:
            item = {"id": row["id"], "metrics": {}, "metric_errors": {}}
            case = by_id[row["id"]]
            if row.get("skipped") or row.get("execution_error"):
                item["not_scored"] = row.get("skipped", row.get("execution_error"))
            elif case.get("expected_guardrail_action") != "allow":
                item["not_scored"] = "guardrail_case_not_RAG_quality"
            else:
                # 실제 워커는 ID·본문·직업명 등 메타데이터를 함께 읽는다.
                contexts = [json.dumps(e, ensure_ascii=False, default=str)
                            for e in row.get("evidence") or [] if e.get("content")]
                response = str(row.get("final_response") or "")
                common = {"user_input": row["question"]}
                metrics = {
                    "answer_relevancy": (korean_answer_relevancy(llm, embeddings), {**common, "response": response}),
                    "faithfulness": (Faithfulness(llm=llm), {**common, "response": response, "retrieved_contexts": contexts}),
                    "context_precision": (ContextPrecision(llm=llm), {**common, "reference": row["reference"], "retrieved_contexts": contexts}),
                    "context_recall": (ContextRecall(llm=llm), {**common, "reference": row["reference"], "retrieved_contexts": contexts}),
                }
                for name, (metric, kwargs) in metrics.items():
                    if name != "answer_relevancy" and not contexts:
                        item["metric_errors"][name] = "no_retrieved_contexts"
                        continue
                    try:
                        value = float((await asyncio.wait_for(metric.ascore(**kwargs), timeout=180)).value)
                        if not math.isfinite(value):
                            item["metric_errors"][name] = "non_finite"
                        else:
                            item["metrics"][name] = value
                    except Exception as exc:
                        item["metric_errors"][name] = type(exc).__name__
            scores[item["id"]] = item
            with score_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            print(f"ragas {len(scores)}/{len(records)} {row['id']} scored={len(item['metrics'])}", flush=True)

    try:
        await asyncio.gather(*(score(row) for key, row in records.items() if key in by_id))
    finally:
        await client.close()
    report = {"manifest": manifest, "generated_utc": datetime.now(timezone.utc).isoformat(), "groups": {}}
    groups = defaultdict(list)
    for row in records.values():
        if row["id"] in by_id:
            groups[row["category"]].append(row)
    names = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    for category, rows in groups.items():
        group = {"n": len(rows), "status": dict(Counter(r.get("status", r.get("skipped", r.get("execution_error"))) for r in rows)),
                 "latency_mean_s": mean([r["elapsed_seconds"] for r in rows]),
                 "guard_expectation_rate": mean([r["guard_expectation_met"] for r in rows if "guard_expectation_met" in r]),
                 "metrics": {}}
        for name in names:
            values = [scores.get(r["id"], {}).get("metrics", {}).get(name) for r in rows]
            group["metrics"][name] = {"mean": mean(values), "valid_n": sum(v is not None for v in values)}
        report["groups"][category] = group
    report["requested_n"] = len(cases)
    report["recorded_n"] = sum(r["id"] in by_id for r in records.values())
    dump(out / "summary.json", report)
    print("REPORT " + str(out / "summary.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", default="output/eval/ragas_20261115")
    parser.add_argument("--basic-only", action="store_true")
    parser.add_argument("--hard-only", action="store_true")
    parser.add_argument("--rag-only", action="store_true")
    asyncio.run(main(parser.parse_args()))
