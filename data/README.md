# CareerGraph 데이터

커리어넷 직업백과 552개 직업과 2023 한국직업전망의 검토된 근거를 정리한 데이터입니다. 수집 기준일은 2026-11-08이며, Neo4j 적재 및 벡터 인덱싱을 완료한 산출물은 아닙니다.

## 디렉터리

- `expanded_20261108/jobs.csv` / `jobs.json`: 직업 552개. 직업 코드 `job_code`가 식별자입니다.
- `expanded_20261108/graph_nodes.csv` / `graph_edges.csv`: 그래프 적재용 노드 1,541개, 중복 제거 관계 4,061개.
- `expanded_20261108/relations.csv`: API 원본 관계 4,070행. 중복 9행을 보존합니다.
- `expanded_20261108/retrieval_chunks.json`: API 청크 6,798개와 PDF 청크 180개. 각 청크의 출처와 필드·페이지 참조를 보존합니다.
- `expanded_20261108/cache/`: 목록 응답 56개와 직업 상세 응답 552개. API 관계의 근거를 `cache/job_<job_code>.json`에서 확인합니다.
- `expanded_20261108/evaluation_draft.json` / `.csv`: 일반·Multi-hop·안전·보류 등 41개 질문의 **초안**. 팀의 정답 및 원문 검토가 필요합니다.
- `expanded_20261108/pdf_existing_reviewed_links.csv`: 기존에 검토한 PDF–직업 대응 14개. 동등성 검토 3개는 재확인이 필요합니다.
- `expanded_20261108/pdf_mapping_candidates_review.csv`: 이름 유사도 기반 미검토 후보. 자동 연결하지 않습니다.
- `expanded_20261108/collection_report.json`, `graph_validation.json`, `validation.json`: 수집 수량과 검증 기록.
- `pdf/outlook_chunks.json`, `job_mapping.csv`, `mapping_evidence.json`, `pdf_sections.json`, `pdf_manifest.json`: 기존 2023 PDF 청크·직업 매핑·근거와 판본 메타데이터.

PDF 검색 청크에 있는 `../pdf/outlook_chunks.json`은 `expanded_20261108`을 기준으로 해석합니다. API 청크의 `cache/job_<코드>.json`도 `expanded_20261108` 기준 경로입니다. 평가 초안의 `raw_file`은 같은 cache 폴더의 파일명입니다. API 주소는 키를 제거한 식별 주소로, 로그인 없이 열리는 원문 페이지가 아닙니다.

## 출처와 주의사항

- 커리어넷: https://www.career.go.kr/cnet/front/openapi/jobCenter.do
- 한국직업전망 PDF 안내: https://www.data.go.kr/data/15140285/fileData.do
- PDF 메타데이터: https://www.data.go.kr/catalog/15140285/fileData.json

2023 한국직업전망은 포털에 공공누리 제2유형(출처표시·상업적 이용금지)으로 등록되어 있습니다. PDF 원본은 이 디렉터리에 포함하지 않았습니다. 팀 공유나 공개 저장소에 게시하기 전 현재 이용 조건과 권리 범위를 확인하세요.

관련 자격은 필수 자격이 아니며 빈 필드는 '없음'을 의미하지 않습니다. PDF의 동일·동등 연결 외 부분 대응과 미대응은 자동 병합하지 않습니다. 수집일·원문 수정일·조사연도를 구분합니다. 가상 충돌 평가 자료는 실제 검색 인덱스에 혼합하지 않습니다. RAGAS·Guardrails 평가는 미실시입니다.

API 키와 `.env` 파일은 포함하지 않았습니다.
