# CareerGraph 통합 평가 보고서 (CRAG · RAGAS · 가드레일 · Langfuse)

> 작성일 2026-11-16 · 코드 기준 커밋 `4f68cbc` (CRAG 병합 이후) · 에이전트 모델 `gpt-6-luna`, 판정 모델 `jev-1.13.0`, RAGAS 평가 모델 `gpt-4.1-mini`
>
> 원본 결과: RAGAS [output/eval/ragas_20261116_crag/](../output/eval/ragas_20261116_crag/) (`summary.json`, `aggregate.json`, `agent_results.jsonl`, `ragas_scores.jsonl`) · 가드레일 [eval/guardrails/results/](../eval/guardrails/results/)

## 1. 요약

| 항목 | 결과 |
|---|---|
| 단위·통합 테스트 | **54개 모두 통과** (CRAG 단위 테스트, 그래프·가드 연결, 서비스 오류 구분, Langfuse, 정규식 검증기 포함) |
| CRAG 동작 확인 | 실제 질문 5건에서 설계대로 동작. 재작성 한 번으로 근거가 충분해지는 사례와, 없는 항목을 밝히는 부분 답변 사례를 확인 |
| RAGAS (138문항) | Faithfulness **0.961** · Answer Relevancy 0.638 · Context Precision 0.788 · Context Recall **0.936**. 실행 오류 0건 |
| 가드레일 입력 | 273건 **273건 정답** (정상 질문 오탐 0, 놓친 공격 0, 규칙 일치율 1.00) |
| 가드레일 출력 | 17건 **17건 정답** (규칙 일치율 1.00) |
| Langfuse 트레이싱 | 노드·OpenAI 호출·검색 도구·Jev 가드레일 판정이 질문 한 턴 단위로 기록됨 (스크린샷 5장) |

주의할 점
- **Multi-hop의 Context Precision이 0.517 → 0.445로 내려갔다.** CRAG 재작성으로 근거가 늘며 불필요한 근거가 섞였을 가능성이 있다(4.3).
- **근거부족 18문항 중 14문항이 `abstain`이 아니라 `partial`로 끝난다.** 채점 규칙은 이 카테고리의 기대 결과를 `abstain`으로 정의한다(4.4).
- **일반 문항 EVAL007("전문의사는 현장에서 어떤 일을 하나요?")이 보류됐다.** 두 번 검색해도 근거 판정이 `incorrect`였다(4.5).

## 2. 평가 환경

| 항목 | 내용 |
|---|---|
| 평가 대상 | 실제 그래프(`build_app`) 전체. 입력 레일 → 프로필 → 검색 → CRAG 평가·재작성 → 추론 → 검증 → 출력 레일 |
| RAGAS 데이터 | [eval/evaluation_draft.json](../eval/evaluation_draft.json) 228문항 중 `expected_guardrail_action == allow`인 168문항. 근거충돌_가상 30문항은 합성 문서 주입이 필요해 제외(실행 건너뜀) → **채점 대상 138문항** |
| 회원 | 모든 문항 U001 선택, 문항마다 독립 단일 턴 |
| 평가 스크립트 | [scripts/run_ragas_eval.py](../scripts/run_ragas_eval.py) `--rag-only --concurrency 4` |
| 비교 기준 | 동료가 CRAG 이전 코드로 낸 보고서 [output/eval/ragas_20261116_rag_only/report.md](../output/eval/ragas_20261116_rag_only/report.md)의 기본 138문항 |
| 연봉 문항 | 평가셋과 가드레일 사례에서 모두 제외된 상태 |

> 실행 중 같은 평가가 두 번 동시에 시작돼 하나를 중단했다. 결과 파일에는 문항마다 기록이 중복돼 있어, 집계는 문항 id 기준 첫 기록만 썼다(168건 모두 한 번씩).

## 3. CRAG 동작 확인

### 3.1 구현 요약 ([app/graph/crag.py](../app/graph/crag.py), [nodes.py](../app/graph/nodes.py) supervisor)

```
search → grade → supervisor
   correct            → reasoner (답변)
   ambiguous/incorrect → rewrite → search(이전 근거와 합침) → grade   (최대 1회)
   재작성 뒤에도 일부 근거가 남음 → reasoner (status=partial, 확인된 부분만 답변)
   근거 없음 → abstain
```

- `grade`가 근거 중 쓸 것만 남기고 `correct / ambiguous / incorrect`, 부족한 정보(`missing_info`)를 낸다.
- `rewrite`는 부족한 정보를 찾는 검색어만 새로 만들고 원질문은 바꾸지 않는다.
- 검증(verifier)이 insufficient를 내면 같은 재작성 경로로 재검색한다(`MAX_RETRIES`).
- 서비스 오류가 있으면 `grade`는 평가 모델을 부르지 않고 Supervisor가 오류 안내로 끝낸다.

### 3.2 실제 질문 5건

| 질문 | 경로 | 판정 | 결과 |
|---|---|---|---|
| 간호사가 되려면 어떤 학과를 가야 해? | search → grade → reasoner | correct, 재작성 0 | "간호학과에 진학하면 됩니다" (supported) |
| 식품가공과와 연결된 식품공학기술자와 바텐더의 핵심능력과 관련 자격을 비교해줘. | search → grade → **rewrite → search → grade** → reasoner | 1차 ambiguous("식품가공과와 두 직업의 연결 관계") → 2차 correct | 두 직업의 능력·자격을 근거와 함께 비교 (supported) |
| 전기공학기술자와 통신장비기사에서 함께 확인되는 관련 자격을… | search → grade → reasoner | correct | 공통 자격 4개를 출처와 함께 답변 (supported) |
| 자동차정비원으로 취업할 수 있는 특정 회사의 합격 컷을 알려주세요. | …rewrite → search → grade → reasoner | ambiguous("특정 회사의 합격 컷") ×2 | 업무는 답하고 "합격 컷은 근거에서 확인되지 않는다"고 밝힘 (partial) |
| 일기예보관의 업무와 관련 학과, 그리고 이 직업의 평균 근속연수를 알려줘 | …rewrite → search → grade → reasoner | ambiguous("평균 근속연수") ×2 | 업무·관련 학과는 답하고 근속연수는 확인 불가로 밝힘 (partial) |

CRAG의 의도대로, 충분한 질문은 한 번에 답하고 부족한 질문은 재검색을 시도하며 끝내 없는 항목은 없다고 밝힌다. 단위 테스트(`tests/test_crag.py`)도 근거 평가, 근거 병합, 후보 밖 ID 처리, Supervisor 분기를 확인한다.

## 4. RAGAS 결과 (CRAG 적용 후, 138문항)

### 4.1 카테고리별 (괄호는 유효 표본 수)

| 카테고리 | 문항 | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
|---|---:|---|---|---|---|
| 일반 | 30 | 0.994 (29) | 0.787 (30) | 1.000 (29) | 1.000 (29) |
| Multi-hop | 30 | 0.958 (30) | 0.718 (30) | 0.445 (30) | 0.867 (30) |
| 관계비교 | 30 | 0.916 (30) | 0.596 (30) | 0.883 (30) | 0.917 (30) |
| 근거부족 | 18 | 0.948 (14) | 0.159 (18) | 0.429 (14) | 0.964 (14) |
| 안전_정상허용 | 30 | 0.985 (30) | 0.736 (30) | 1.000 (30) | 0.950 (30) |
| **전체** | **138** | **0.961** (133) | **0.638** (138) | **0.788** (133) | **0.936** (133) |

### 4.2 CRAG 전후 비교 (이전 = 동료 보고서의 기본 138문항, 유효 표본 수는 서로 다름)

| 지표 | 이전 | 이후 | 변화 |
|---|---:|---:|---|
| Faithfulness | 0.955 | 0.961 | +0.006 |
| Answer Relevancy | 0.618 | 0.638 | +0.020 |
| Context Precision | 0.785 | 0.788 | +0.003 |
| Context Recall | 0.848 | 0.936 | **+0.088** |

| 카테고리 | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
|---|---|---|---|---|
| 일반 | 0.980 → 0.994 | 0.833 → 0.787 | 1.000 → 1.000 | 0.967 → 1.000 |
| Multi-hop | 0.956 → 0.958 | 0.715 → 0.718 | **0.517 → 0.445** | 0.767 → 0.867 |
| 관계비교 | 0.903 → 0.916 | 0.557 → 0.596 | 0.852 → 0.883 | 0.750 → 0.917 |
| 근거부족 | 0.949 → 0.948 | 0.035 → 0.159 | 0.456 → 0.429 | 1.000 → 0.964 |
| 안전_정상허용 | 0.984 → 0.985 | 0.714 → 0.736 | 0.967 → 1.000 | 0.817 → 0.950 |

- **가장 큰 개선은 Context Recall(0.848 → 0.936)이다.** 근거가 부족하면 재작성·재검색으로 보충하는 CRAG의 효과와 맞는다. 관계비교는 0.750 → 0.917, 안전_정상허용은 0.817 → 0.950이다.
- 비교는 같은 평가셋이지만 한 번씩의 실행이고 LLM 판정이라 ±0.02 안팎은 흔들림 범위로 봐야 한다. 이전 보고서에는 고난도 30문항이 따로 있었고 이번에는 평가셋 파일에 없어 비교에서 제외했다.

### 4.3 Multi-hop Context Precision 하락 (0.517 → 0.445)

- Multi-hop 30문항 중 8문항이 재작성을 거쳤고(재검색 포함 2문항), 재작성 때 이전 근거와 새 근거를 합친다. 합친 근거 중 질문과 무관한 것이 늘면 Precision이 내려간다.
- 같은 문항에서 Recall은 0.767 → 0.867로 올랐다. 즉 "더 많이 찾고, 그중 일부는 불필요"한 방향의 트레이드오프로 보인다. 원인으로 확정하지는 않았다.
- 확인 방법: Langfuse에서 해당 트레이스의 `grade` 입력(후보 근거)과 `kept_ids`, `rewrite` 출력(새 검색어)을 비교한다.

### 4.4 근거부족 18문항: partial vs abstain

| 최종 상태 | 건수 |
|---|---:|
| partial (확인된 부분만 답변) | 14 |
| abstain (보류) | 4 |

- 14건은 직업 업무 같은 확인 가능한 내용을 답하고 "합격 컷·취업률은 근거에서 확인되지 않는다"고 밝힌다(3.2의 자동차정비원 사례). 정보를 지어내지는 않는다(Faithfulness 0.948).
- 다만 채점 규칙([eval/CareerGraph_평가셋_채점규칙.md](../eval/CareerGraph_평가셋_채점규칙.md))은 이 카테고리의 기대 `outcome`을 `abstain`으로 둔다. 이 비교 지표(outcome 정확 일치)는 RAGAS 스크립트가 계산하지 않으므로, 팀이 "부분 답변 + 확인 불가 명시"를 정답으로 인정할지 정해야 한다.
- Answer Relevancy가 0.035 → 0.159로 올랐다. 보류 문구만 내던 이전보다 질문에 관련된 내용을 답하기 때문이다.

### 4.5 낮은 점수와 의심 사례

| 문항 | 카테고리 | Faithfulness | 비고 |
|---|---|---:|---|
| EVAL050 섬유공학과 → 섬유공학기술자·캐드원 능력·자격 | Multi-hop | 0.00 | CRAG 판정 correct, 답변이 근거에서 벗어났을 가능성 |
| EVAL072 학습지방문교사·디지털 포렌식 수사관 공통 핵심능력 | 관계비교 | 0.50 | correct 판정 |
| EVAL073 통신공학 기술자 및 연구원·방송장비설치수리원 공통 자격 | 관계비교 | 0.50 | correct 판정 |
| EVAL061, 066, 074, 083, 098 | 관계비교 등 | 0.67 | ambiguous 판정 3건 포함 |

- EVAL050, 072, 073은 grade가 `correct`라고 판정했는데 답변 충실도가 낮다. **grade의 "충분" 판정과 실제 답변 품질이 어긋나는 사례**로, Langfuse에서 `reasoner` 입력 근거와 답변을 대조해 볼 가치가 있다.
- **일반 EVAL007("전문의사는 현장에서 어떤 일을 하나요?")이 보류됐다.** 두 번 검색 모두 후보 5개가 `incorrect`(쓸 근거 0)로 판정돼 "현재 자료만으로는 답변을 확정하기 어렵습니다"로 끝났다. 해당 직업명이 데이터에 없는 표현일 수 있다. 이전 보고서에서는 일반 30건이 모두 live였으므로 CRAG 도입 이후의 변화인지 확인이 필요하다.

### 4.6 CRAG 경로 통계와 지연

| 카테고리 | 재작성 0회 | 재작성 1회 | 최종 판정 |
|---|---:|---:|---|
| 일반 | 29 | 1 | correct 29, incorrect 1 |
| Multi-hop | 22 | 8 | correct 30 |
| 관계비교 | 17 | 13 | correct 25, ambiguous 5 |
| 근거부족 | 0 | 18 | ambiguous 14, incorrect 4 |
| 안전_정상허용 | 30 | 0 | correct 30 |

- 전체 138문항 중 40문항(29%)이 재작성을 거쳤다. 근거부족은 전부 재작성한다.
- 평균 지연 **12.1초**, 중앙 13.2초, p90 19.8초, 최대 28.6초. 근거부족은 재작성 때문에 평균 20.1초로 가장 길다.
- 실행 오류, 타임아웃, 출력 가드 오류는 **0건**이다.
- 전체 상태: supported 114, partial 19, abstain 5.

## 5. 가드레일 통합 평가

실행: `python eval/guardrails/run_guardrail_eval.py`. 평가셋 228문항 + 추가 시나리오 45건(입력), 손으로 만든 17건(출력). 연봉 관련 사례는 제외.

| 구분 | 사례 | 정답 | 오탐 | 누락 | 규칙 일치율 | 지연 중앙/p90 |
|---|---:|---:|---:|---:|---:|---|
| 입력 | 273 | **273** | 0 | 0 | 1.00 | 0.60초 / 0.82초 |
| 출력 | 17 | **17** | 0 | 0 | 1.00 | 0.36초 / 0.71초 |

- 입력 차단·안내 87건: `jev policy input` 49건, `topic input`(위기 3, 범위 밖 34) 37건, `member access input` 1건.
- 위기 신호는 상담 안내(CRI-01/02), 범위 밖 질문은 범위 안내(SCOPE-01)로 검색 없이 끝난다.
- 출력 차단 12건은 모두 `jev policy output`에서 막았고, 본인 주소가 섞인 답변(O-S04)은 정규식 층이 `[주소]`로 가렸다.
- 자세한 사례별 표와 개선 내역은 [Guardrails 적용 명세서](CareerGraph_Guardrails_적용명세서.md)에 있다.

**CRAG와 가드레일의 관계:** 가드레일 평가는 레일 판정만 따로 돌린다. 그래프 전체 평가(RAGAS)에서는 168문항의 입력 가드 기대 결과(`guard_expectation_met`)가 모두 충족됐고(정상 질문 통과 100%), 출력 가드 오류도 0건이다.

## 6. Langfuse 트레이싱 스크린샷

질문 "식품가공과와 연결된 식품공학기술자와 바텐더의 핵심능력과 관련 자격을 비교해줘."(CRAG 재작성 경로)의 트레이스다. 세션 = 대화 ID, 사용자 = `guest`, 태그 `careergraph`. 계정 이름 영역은 가렸다.

| 화면 | 설명 |
|---|---|
| ![대시보드](images/langfuse_01_dashboard.jpg) | **대시보드:** 이 프로젝트 트레이스 357건, 모델 사용량·비용 |
| ![트레이스 트리](images/langfuse_02_trace_tree.jpg) | **트레이스 트리:** `careergraph-turn` 아래 `input_guard → profile_check → search → …`, 각 단계 소요 시간(총 21.9초, 약 10k 토큰, $0.001) |
| ![그래프 보기](images/langfuse_03_graph_crag_loop.jpg) | **그래프 보기:** `search → grade → supervisor → rewrite → search`의 CRAG 재검색 루프가 그대로 보임 (`search 2/2`, `grade 2/2`) |
| ![타임라인](images/langfuse_04_timeline.jpg) | **타임라인:** 노드별 실행 시간. 재검색으로 늘어난 구간 확인 |
| ![가드레일 판정](images/langfuse_05_guardrail_jev.jpg) | **가드레일 판정:** `jev-policy-judgement` 입력(정책 문구)과 출력(`probability` 0.06) |

활용법과 권장 질문은 README의 트레이싱 절을 참고한다. 트레이스에 기록되는 질문·답변은 주민번호·전화·이메일·주소를 가린 뒤 전송된다.

## 7. 남은 과제

| 순위 | 항목 | 제안 |
|---|---|---|
| 1 | 근거부족 문항의 기대 결과(abstain)와 실제(partial 14건) 불일치 | 팀에서 기준 결정. "부분 답변 + 확인 불가 명시"를 정답으로 인정하거나, 채점 규칙에 `partial`을 추가 |
| 2 | grade가 correct로 판정했는데 충실도가 낮은 사례(EVAL050, 072, 073) | Langfuse에서 `grade`와 `reasoner` 입력을 대조, grade 프롬프트의 "충분" 기준 보강 검토 |
| 3 | Multi-hop Context Precision 하락 | 재작성 후 근거 병합 시 `useful_ids` 재선별 또는 이전 근거 유지 규칙 검토 |
| 4 | EVAL007(전문의사) 보류 | 데이터의 직업명(`의사` 등)과 질문 표현 차이 확인, 직업명 정규화 검토 |
| 5 | 고난도 30문항이 평가셋 파일에 없음 | 파일을 저장소에 추가해야 이전 보고서와 같은 조건으로 비교 가능 |
| 6 | 근거충돌_가상 30문항 미평가 | 합성 문서 주입 방식(`synthetic_fixture`)을 구현해 평가 |
| 7 | grade 호출 실패 시 근거를 그대로 통과(fail-open) | 의도된 동작이지만 Langfuse에서 `CRAG grade failed` 경고를 모니터링 |

## 8. 재현

```bash
python -m pytest -q tests                                   # 54개
python scripts/run_ragas_eval.py --rag-only --concurrency 4 --output output/eval/<새 폴더>
python eval/guardrails/run_guardrail_eval.py                # 약 30초
```

- RAGAS는 에이전트 실행과 채점에 OpenAI·Jev API를 쓰며 수십 분이 걸린다. 같은 `--output` 폴더로 동시에 두 번 실행하지 않는다(결과가 중복 기록된다).
- Langfuse 키가 `.env`에 있으면 위 실행 모두 트레이스로 남는다.
