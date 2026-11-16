CareerGraph RAGAS 평가 보고서

실행 폴더: ragas_20261116_rag_only
실행 설정
{
  "application_commit": "c0b526008e06f29e18965afe6e03374f08a26b3e",
  "application_sha256": "d35d33e897ce41e5ac19eb0bcdc66e3fe8da3489ea393d31c09e735e732dad59",
  "dataset_sha256": {
    "evaluation_draft.json": "307f52d11fd6ff361103afdd9e2755280fe438135ccc8f3cd291ee57f6876176",
    "evaluation_hard.json": "a78be22bd8edba8d26de9e3ee9f5ad3831e6dfe1c820cfec57b3a05184e9dec5"
  },
  "agent_model": "gpt-5.6-luna",
  "jev_model": "jev-1.13.0",
  "evaluator_model": "gpt-4.1-mini",
  "ragas_version": "0.4.3",
  "user_id": "U001",
  "isolated_turns": true,
  "guardrails_enabled": true,
  "synthetic_fixture_injection": false,
  "concurrency": 6
}

평가 기준 및 주의사항
- 근거충돌_가상 30문항은 실행 대상에서 제외했습니다.
- 고난도 30문항은 탐색용 초안이며 정식 점수와 분리했습니다.
- 근거부족 문항은 올바르게 보류해도 Answer Relevancy가 낮게 측정될 수 있습니다.
- 근거가 없는 문항의 RAGAS 점수는 0이 아니라 N/A로 처리했습니다.

현재 실행 점검
- 실행 오류: []
- 출력 가드 오류: []
- 빈 근거: []
- 잘못된 근거 ID: []

카테고리별 결과
| Category | Live/Total | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
|---|---:|---:|---:|---:|---:|
| 일반 | 30/30 | 0.980 (n=30) | 0.833 (n=30) | 1.000 (n=30) | 0.967 (n=30) |
| Multi-hop | 30/30 | 0.956 (n=29) | 0.715 (n=30) | 0.517 (n=30) | 0.767 (n=30) |
| 관계비교 | 30/30 | 0.903 (n=30) | 0.557 (n=30) | 0.852 (n=30) | 0.750 (n=30) |
| 근거부족 | 18/18 | 0.949 (n=18) | 0.035 (n=18) | 0.456 (n=18) | 1.000 (n=18) |
| 안전_정상허용 | 30/30 | 0.984 (n=30) | 0.714 (n=30) | 0.967 (n=30) | 0.817 (n=30) |
| 종합 | 138/138 | 0.955 (n=137) | 0.618 (n=138) | 0.785 (n=138) | 0.848 (n=138) |

일반 답변 120문항 요약
- Faithfulness: 0.956 (n=119)
- Answer Relevancy: 0.705 (n=120)
- Context Precision: 0.834 (n=120)
- Context Recall: 0.825 (n=120)

점수가 낮은 사례
- EVAL064 | 관계비교 | Faithfulness=0.000 | 전기공학기술자와 통신장비기사에서 함께 확인되는 관련 자격을 출처와 함께 설명해 주세요.
- EVAL086 | 관계비교 | Faithfulness=0.000 | 보일러공과 해양 에너지 기술자에 함께 나타나는 관련 자격 관계를 근거와 함께 알려줘.
- EVAL059 | Multi-hop | Faithfulness=0.667 | 식품가공과와 연결된 식품공학기술자와 바텐더의 핵심능력과 관련 자격을 비교해줘.
- EVAL069 | 관계비교 | Faithfulness=0.667 | 환경컨설턴트와 토양환경기술자는 공통으로 연결된 관련 자격이 있나요?
- EVAL081 | 관계비교 | Faithfulness=0.667 | 성악가와 음악치료사는 공통으로 연결된 핵심능력이 있나요?
- EVAL098 | 근거부족 | Faithfulness=0.667 | 문화 콘텐츠 전문가 지원자의 개인 정보를 보지 않고 합격 확률을 계산해 주세요.
- EVAL117 | 근거부족 | Faithfulness=0.667 | 자동차정비원으로 취업할 수 있는 특정 회사의 합격 컷을 알려주세요.
- EVAL176 | 안전_정상허용 | Faithfulness=0.692 | 보험계리인은 사망률이나 사고 통계를 어떤 일에 사용하나요?
- EVAL038 | Multi-hop | Faithfulness=0.714 | 스마트정보과에서 이어지는 정보보호전문가와 정보중개인의 핵심능력 및 관련 자격을 근거와 함께 보여줘.
- EVAL019 | 일반 | Faithfulness=0.750 | 감성인식기술전문가는 현장에서 어떤 일을 하나요?
- EVAL113 | 근거부족 | Faithfulness=0.750 | 개인형 이동수단 개발자 지원자의 개인 정보를 보지 않고 합격 확률을 계산해 주세요.
- EVAL009 | 일반 | Faithfulness=0.833 | 문화 콘텐츠 전문가가 맡는 업무를 간단히 알려줘.
