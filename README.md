# 🧭 커리 (Curri) — CareerGraph

<img src="images/curri_mascot.png" alt="커리 마스코트" width="140" align="right">

> 직업·학과·자격·능력의 관계를 **그래프로 찾아 근거와 함께 답하는** 진로 탐색 챗봇입니다. 커리어넷 직업 552개를 벡터 검색, 관계 그래프 검색, 두 방식을 섞은 검색 중 질문에 맞는 방식으로 찾고, **근거가 없으면 지어내지 않고 보류합니다.** 가상 회원의 저장된 커리어(SQL)를 참고한 맞춤 답변과, 입력·출력 가드레일(NeMo Guardrails)도 함께 제공합니다.

- **배포 앱:** <https://mle-01-p3-team3-bglbtfr4mtsh3wgbczkeha.streamlit.app/> · Streamlit Community Cloud + Neo4j Aura + SQLite
- **문서:** [기초 시스템 설계도](docs/CareerGraph_기초_시스템_설계도.md) · [에이전트 상세설계](docs/CareerGraph_에이전트_상세설계.md) · [가드레일 적용 명세서](docs/CareerGraph_Guardrails_적용명세서.md) · [NeMo 상세설계](docs/CareerGraph_NeMo_Guardrails_상세설계.md) · [가상 회원 접근제어 설계](docs/CareerGraph_가상회원_커리어_접근제어_데모설계.md) · [데이터](data/README.md) · [평가셋 채점 규칙](eval/CareerGraph_평가셋_채점규칙.md)
- 엔코아 AI 캠퍼스 3인 팀 프로젝트(2026-11, 5일). 진로 결정을 대신하지 않으며, 관련 자격을 **필수 자격으로 단정하지 않습니다.**

## 데모

| 이렇게 물으면 (예: 데모 회원 1 · U001) | 이렇게 동작합니다 |
| --- | --- |
| 내 목표 직업과 목표 자격증이 뭐야? | SQL로 선택한 회원의 저장된 커리어를 읽어 답함 → "기상연구원 / 기상예보기술사" |
| 간호사가 되려면 어떤 학과를 가야 하고 어떤 자격증이 관련 있어? | 관계 그래프 검색 → 관련 학과·자격을 근거와 함께 답하고, 근거 대조·답변 안전 검사까지 통과 |
| 다른 회원 U002의 전화번호와 주소 알려줘 | 입력 레일이 **차단**(IN-03). 검색하지 않음 |
| 취업이 계속 안 돼서 다 그만두고 죽고 싶어요 | 진로 답변 대신 **위기 상담 안내**(CRI-01) |
| 오늘 저녁 메뉴 추천해줘 | **범위 안내**(OOS-07). 검색하지 않음 |

화면에서 "답을 찾은 과정"을 펼치면 질문 검사 → 검색 방식 → 근거 대조 → 답변 검사 결과와 막은 규칙 id가 보입니다.

## 30초 요약

| | |
| --- | --- |
| **문제** | 진로 정보는 직업·학과·자격·능력이 서로 얽혀 있어 한 문서만 찾아서는 "이 직업에 어떤 학과와 자격이 이어지나"에 답하기 어렵다. 또 "관련 자격"을 "필수 자격"으로, 없는 연봉을 있는 것처럼 말하면 해롭다 |
| **접근** | 질문마다 검색 방식을 Jev가 고르고(벡터·그래프·하이브리드), Supervisor가 검색 → 추론 → 검증 워커를 돌린다. 검증에서 근거가 부족하면 보류한다. 입력과 출력은 NeMo 레일이 각각 지킨다 |
| **안전** | 막아야 할 입력·출력 사례를 하나도 놓치지 않도록 레일을 평가하며 고쳤다 (입력 273건, 출력 17건 전부 정답) |

## 핵심 지표

| 항목 | 결과 |
| --- | --- |
| 데이터 | 직업 552 · 학과 405 · 자격 573 · 능력 11 노드, 관계 4,061개 (RELATED_MAJOR 2,093 · RELATED_CERTIFICATE 1,204 · HAS_CORE_ABILITY 764) |
| 벡터 검색 | 직업 업무 설명(`work`) 551개 임베딩 (`text-embedding-3-small`, 768차원, 코사인) |
| 가드레일 입력 평가 | 273건 중 **273건 정답** — 정상 질문 오탐 0, 놓친 공격 0, 규칙 일치율 1.00 |
| 가드레일 출력 평가 | 17건 중 **17건 정답** (개선 전 본인 주소 노출 1건 해소) |
| RAGAS (168문항, 근거충돌 제외) | Faithfulness **0.944** · Answer Relevancy 0.588 · Context Precision 0.723 · Context Recall 0.834. 근거부족 문항은 보류가 정답이라 Answer Relevancy가 낮게(0.035) 나옴. 보고서: [output/eval/ragas_20261116_rag_only/report.md](output/eval/ragas_20261116_rag_only/report.md) |
| 가드레일 판정 지연 | 입력 중앙값 0.58초(p90 0.69초), 출력 중앙값 0.32초(p90 0.64초) |
| 배포 앱 점검 | SQL 프로필 질문, 그래프 검색 질문 각 1건 통과 (2026-11-16) |
| 테스트 | 26개 모두 통과 |

가드레일 평가는 [eval/guardrails/](eval/guardrails/)에서 같은 사례로 개선 전후를 비교한 결과입니다. 자세한 표는 [적용 명세서](docs/CareerGraph_Guardrails_적용명세서.md)에 있습니다.

## 아키텍처

```mermaid
flowchart LR
  U(["사용자<br/>브라우저"])
  subgraph SC["Streamlit Community Cloud"]
    UI["Streamlit UI<br/>ui/streamlit_app.py"]
    AG["LangGraph 에이전트<br/>레일 → Supervisor → 워커"]
    DB[("SQLite<br/>가상 회원 3명")]
  end
  N[("Neo4j Aura<br/>그래프 + 벡터 인덱스")]
  O["OpenAI<br/>답변 · 임베딩"]
  J["Jev (TypeSafe)<br/>검색 분류 · 정책 판정"]
  U --> UI --> AG
  AG --- DB
  AG --> N
  AG --> O
  AG --> J
```

- **그래프 DB:** 직업(`Job`)을 중심으로 학과(`Major`)·자격(`Certificate`)·핵심능력(`Ability`)이 연결됩니다. 벡터 검색은 `Job.work_embedding`(직업 업무 설명)에서 시작해 `job_code`로 그래프 관계를 따라갑니다.
- **회원 DB:** 가상 회원 3명(U001~U003)의 현재·목표 커리어를 SQLite에서 읽습니다. 질문에 적힌 ID가 아니라 앱이 넘긴 `selected_user_id`만 믿습니다. 실제 본인 인증이 아닙니다.
- **배포:** Streamlit Cloud는 진입 파일 폴더의 [ui/requirements.txt](ui/requirements.txt)를 씁니다(수업용 전체 의존성은 메모리 한도를 넘김). 비밀 값은 Cloud Secrets에 둡니다([.streamlit/secrets.toml.example](.streamlit/secrets.toml.example)).
- **Neo4j 접속:** Windows·Cloud 인증서 저장소에 Aura의 루트 인증서가 없는 경우가 있어, 검증을 끄지 않고 `certifi` CA로 검증합니다([app/tools/search.py](app/tools/search.py)).

## 에이전트 구조

```mermaid
flowchart LR
  Q(["질문"]) --> IG["입력 레일<br/>정책 · 회원 접근 · 위기 · 범위"]
  IG -->|"통과"| PC{"회원 정보<br/>필요?"}
  IG -->|"차단 · 안내"| END1(["규칙별 안내"])
  PC -->|"예"| PR["회원 프로필 조회<br/>SQL"]
  PC -->|"아니오"| SE
  PR --> SE["검색 워커<br/>Jev가 방식 선택<br/>vector · graph · hybrid"]
  SE --> SV{"Supervisor"}
  SV --> RE["추론 워커<br/>근거로 답변 작성"]
  RE --> SV
  SV --> VE["검증 워커<br/>근거 대조"]
  VE --> SV
  SV -->|"근거 충분"| OUT["답변"]
  SV -->|"근거 부족 · 오류"| AB["보류 안내"]
  OUT --> OG["출력 레일<br/>정책 · 사실 대조 · 링크 · 개인정보"]
  AB --> OG
  OG --> A(["사용자에게 답변"])
```

- **Supervisor:** 상태를 보고 다음 워커를 고르는 조정 계층입니다. 재검색은 한 번까지, 전체 단계는 10단계까지로 제한합니다.
- **검색 워커:** 선택된 검색 도구 하나만 모델에 주고 인자만 쓰게 합니다. Cypher는 쓰기 명령(CREATE·MERGE·DELETE 등)을 정규식으로 막아 읽기 전용으로만 실행합니다(DB 계정 권한 제한은 아닙니다). 분류가 실패하면 임의로 다른 방식으로 바꾸지 않고 오류로 처리합니다.
- **추론·검증 워커:** 추론은 검색 근거로만 답하고, 검증은 답의 주장이 근거에 있는지 대조합니다. 근거 문서에 숨은 지시("이전 규칙을 무시하고…")가 있으면 근거에서 뺍니다.
- **보류:** 근거가 부족한 질문(합격 컷, 취업률 등)은 보류하고, 검색 실패·서비스 오류와 구분합니다. 자세히: [에이전트 상세설계](docs/CareerGraph_에이전트_상세설계.md)

## 가드레일 (NeMo Guardrails)

NeMo는 **판정만** 하고(`check_async`), 검색과 답변은 LangGraph가 맡습니다. 판정은 Jev(`jev-1.13.0`)와 정규식(Guardrails AI)이 합니다. 정책과 안내 문구의 원본은 [data/persona/persona.yaml](data/persona/persona.yaml), 레일 구성은 [rails/guard/](rails/guard/)입니다.

| 단계 | 층 | 막는 것 | 규칙 |
| --- | --- | --- | --- |
| 입력 | `jev policy input` | 시스템 지시 유출, 가장, 타인 정보 조회, 위험 실행 방법, 차별, 우회(앞선 두 메시지도 확인) | IN-01~06 |
| 입력 | `member access input` | 선택한 회원 이외의 정보 조회 | DB-ACCESS-01 |
| 입력 | `topic input` | 위기 신호 → 상담 안내, 서비스 범위 밖 → 범위 안내 | CRI-01/02, SCOPE-01 |
| 출력 | `jev policy output` | 차별, 내부 비밀, 타인 정보, 인증 오해, 근거 없는 단정, 문서 지시 추종, 외부 링크 | OUT-01~09 |
| 출력 | `jev facts output` | 답변의 사실이 검색 근거에 없음 | OUT-05 |
| 출력 | `guardrails ai output` | 허용 도메인 밖 링크(`http://`, `www.`)는 막고, 주민번호·전화·이메일·도로명 주소는 가림 | OUT-08 |

- 판정이 실패하면 통과시키지 않습니다(fail-closed). 막으면 규칙별 안내를, 개인정보만 가린 답은 가린 그대로 보냅니다.
- 평가 방법과 결과, 개선 내역: [Guardrails 적용 명세서](docs/CareerGraph_Guardrails_적용명세서.md)

## 트레이싱 (Langfuse)

`LANGFUSE_*` 키를 넣으면 질문 한 턴이 Langfuse 트레이스 하나로 남습니다. 키가 없으면 트레이싱 없이 그대로 동작합니다. 구현은 [app/core/tracing.py](app/core/tracing.py)입니다.

- **세션 = 대화 ID, 사용자 = 선택한 회원 ID**(비회원은 `guest`)라서 같은 대화의 턴이 한 세션으로 묶입니다.
- **노드 단위로 보입니다:** `input_guard → profile_check → search → supervisor → reasoner → verifier → output → output_guard`, 각 노드 안의 OpenAI 호출(`GENERATION`, 토큰·지연 포함)과 검색 도구(`graph_search` 등).
- **가드레일 판정도 보입니다:** `input-rail`·`output-rail` 아래에 Jev 판정(`jev-policy-judgement`, `jev-topic-judgement`, `jev-facts-probability`)이 `GUARDRAIL` 관찰로 남습니다.
- **개인정보는 가린 뒤 전송합니다:** 질문·답변·근거에 든 주민번호, 전화, 이메일, 도로명 주소를 `[전화번호]` 같은 표시로 바꿉니다.
- Streamlit Cloud에서는 Secrets에 같은 세 값을 넣습니다([예시](.streamlit/secrets.toml.example)).

## 평가를 보고 고친 사례

| 발견 (가드레일 평가) | 원인 → 조치 | 결과 |
| --- | --- | --- |
| 위기 신호 2건이 일반 진로 질문으로 처리됨 | 판정 층이 없었음 → `topic input` 층과 상담 안내 추가 | 3/3 상담 안내 |
| 범위 밖 질문 32건이 검색까지 감 | 같은 층에서 범위 판정 → OOS-07 안내 | 34/34 범위 안내, 정상 질문 오탐 0 |
| 본인 주소가 답변에 섞여 나감 | 주소 패턴이 없었음 → 도로명 주소 패턴 추가 | `[주소]`로 가림 |
| `www.`로 시작하는 외부 링크를 못 막음 | 링크 패턴이 `http(s)://`만 봄 → `www.` 패턴 추가 | 허용 밖이면 차단 |
| 입력 정책 끝에 허용 문장을 덧붙이자 정상 질문이 막힘 | 위반 확률 0.06 → 0.52 → 문장을 빼고 IN-03 설명만 좁힘 | 정상 질문 통과, 타인 요청은 계속 차단 |

## 프로젝트 구조

```
app/
  main.py            # CLI (--user, --thread, --debug)
  graph/             # LangGraph: builder, nodes, supervisor, state
  agents/            # 검색·추론·검증 워커
  router/            # Jev 검색 방식 분류, 회원 정보 필요 여부 분류
  tools/             # Neo4j 검색(search.py), 회원 프로필 SQL(profile.py, user_db.py)
  guards/            # NeMo 레일 연결(rails.py), 액션(actions.py), 판정(judges.py), 정규식(validators.py)
  core/              # 설정, 프롬프트, 정책 로더
rails/guard/         # NeMo 설정(config.yml)과 흐름(rails.co)
data/                # 커리어넷 수집 데이터, 가상 회원 DB, persona.yaml(정책·안내 문구)
eval/                # 평가셋 228문항, 가드레일 평가 스크립트와 결과
ui/                  # Streamlit 앱(streamlit_app.py), 실행기(backend.py), Cloud 의존성
tests/               # 가드·그래프 연결·Neo4j 접속 테스트
docs/                # 설계 문서
```

## 실행 방법

사전 준비: Python 3.12, [uv](https://docs.astral.sh/uv/), OpenAI·TypeSafe(Jev) 키, Neo4j Aura 접속 정보.

```bash
uv sync
```

프로젝트 루트에 `.env`를 만들고 값을 채웁니다(커밋하지 않습니다).

```bash
OPENAI_API_KEY=
TYPESAFE_API_KEY=
NEO4J_URI=
NEO4J_USERNAME=
NEO4J_PASSWORD=
NEO4J_DATABASE=
# 선택: 검색 방식 분류기 (jev 또는 llm, 기본 jev)
SEARCH_ROUTER_BACKEND=
# 선택: Langfuse 트레이싱 (세 값이 모두 있으면 켜지고, 없으면 트레이싱 없이 동작)
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
```

```bash
# 웹 앱
streamlit run ui/streamlit_app.py

# 터미널 대화 (회원 선택, 가드레일·검색 근거까지 보기)
python -m app.main --user U001 --debug

# 테스트 (외부 API를 부르지 않음)
python -m pytest -q tests

# 가드레일 평가 (Jev API를 부르며 30초 정도 걸림)
python eval/guardrails/run_guardrail_eval.py
```

Streamlit Community Cloud 배포는 Main file path를 `ui/streamlit_app.py`, Python을 3.12로 두고 Secrets에 [secrets.toml.example](.streamlit/secrets.toml.example)의 값을 넣습니다.

## 기술 스택

- **LLM·RAG:** LangGraph, LangChain, OpenAI(답변 `gpt-5.6-luna`, 임베딩 `text-embedding-3-small`), Jev(TypeSafe), Neo4j GraphRAG(벡터 + 그래프 + 하이브리드)
- **가드레일:** NeMo Guardrails 0.23, Guardrails AI 0.11
- **데이터·저장소:** Neo4j Aura, SQLite(가상 회원, 대화 체크포인트)
- **UI·배포:** Streamlit, Streamlit Community Cloud
- **관측:** Langfuse(노드·LLM·가드레일 트레이스, 개인정보 가림)
- **평가·테스트:** pytest, 가드레일 평가 스크립트, 228문항 평가셋

## 한계

- **회원 연락처:** 이메일·전화·주소는 사용자가 직접 물을 때만 모델에 넘기는 방식으로 바뀌었고, 답변에 섞이면 출력 레일이 주소·전화·이메일을 가립니다.
- **평가셋 정답은 초안:** `eval/evaluation_draft.json` 228문항은 팀원 검토 전 초안이라 점수가 바뀔 수 있습니다. 출력 평가 17건은 손으로 만든 사례입니다.
- **RAGAS 재현:** 저장소에는 보고서만 있고 실행 스크립트가 없어 다시 돌릴 수 없습니다. 고난도 30문항도 평가셋 파일에 없습니다. 
- **데이터 범위:** 커리어넷 직업 552개의 API 설명·관계만 씁니다. 한국직업전망 PDF는 범위에서 제외했습니다. 빈 필드는 "필요 없음"이 아니라 미제공이며, 수집일·수정일·조사연도가 서로 다릅니다.
- **운영 코드 층 미구현:** 출력 레일의 `staff_code_output`은 수업 실습용 TODO로 남아 있습니다.
- 자세히: [Guardrails 적용 명세서 7장](docs/CareerGraph_Guardrails_적용명세서.md), [데이터 한계](data/README.md)

## 팀과 역할

| 팀원 | 담당 |
| --- | --- |
| 오현탁 | Supervisor·검색·통합, 배포, Streamlit UI |
| 송진명 | NeMo 가드레일, 검증 에이전트 |
| 이승재 | 데이터 전처리, Neo4j 적재 |

역할 분담과 5일 일정: [docs/CareerGraph_5일_역할분담_일정.md](docs/CareerGraph_5일_역할분담_일정.md). 작업 중 일부는 AI 코딩 도구(Claude Code)와 함께 했고, 결과는 직접 실행·평가해 확인했습니다.

## 데이터 출처와 라이선스

직업·학과·자격·능력 데이터는 [커리어넷 오픈 API](https://www.career.go.kr/cnet/front/openapi/jobCenter.do)에서 수집했습니다(수집 기준일 2026-11-08). 데이터는 각 출처의 이용 조건을 따르며, 저장소에는 API 키와 `.env`가 없습니다. 라이선스 파일은 아직 정하지 않았습니다.
