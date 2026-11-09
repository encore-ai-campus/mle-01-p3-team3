# CareerGraph 데이터 수집 결과

수집일: 2026-11-07, 한국시간. 인계서에 따른 API 수집·PDF 추출·직업 대응표 작성 완료.

## 결과

| 항목 | 결과 |
|---|---:|
| 커리어넷 직업 | 50개, 코드 중복 0개 |
| 직업 관계 | 490개 |
| 관련 학과 이름·ID 쌍 | 176개 |
| 추가 API 요청 | 목록 5회 + 상세 50회 = 55회, 모두 HTTP 200 |
| PDF | 2023 한국직업전망, 668쪽 |
| PDF 텍스트 청크 | 2,013개 |
| 직업 대응표 | 50행 |
| 동일 명칭·업무 확인 | exact 11개 |
| 명칭 차이·업무 동등성 확인 | verified_equivalent 3개 |
| 일부 업무·범위만 대응 | partial 14개 |
| 2023판 대응 항목 미확인 | unmatched 22개 |
| PDF 연결 직업 / 청크 | 14개 / 180개 |

API 요청 기록상 첫 요청은 12:34:22, 마지막 요청은 12:36:26(+09:00)이다. 이는 API 요청 기록의 시각이며 전체 PDF 검토 작업의 시작·종료 시각과는 다르다. 요청은 순차적으로 처리했고 매 요청 전 2초 대기했다. 재시도·병렬 호출·인증 오류·할당량 오류는 없었다. 응답에서 rate-limit/quota/retry-after 헤더는 관찰되지 않았다. 서버 계정의 전체 호출 수와 잔여량은 알 수 없다.

## 파일 안내

- `career_api/careernet_jobs_50.csv`: 직업 1개 = 1행, Excel용 UTF-8 BOM.
- `career_api/careernet_jobs_50.json`: 같은 데이터의 JSON.
- `career_api/careernet_details_50.json`: 상세 API 응답 전체 50개.
- `career_api/careernet_relations.csv`: 직업-학과·자격·핵심능력 관계. 원본 필드와 출처 포함.
- `career_api/major_pairs.json`: 원본 배열에서 추출한 학과 이름·ID 쌍. CSV 문자열 순서로 추정하지 않았다.
- `career_api/raw_cache/`: 목록 5개와 상세 50개 원본 응답의 복사본. `raw_file`에 적힌 파일명은 이 폴더에서 찾을 수 있다.
- `career_api/request_log.json`: 인증키가 없는 실제 요청 기록.
- `career_api/collection_report.json`: 호출 수, 빈 필드 수, 검증 결과.
- `career_api/policy_review.json`: 확인한 공식 출처, 매뉴얼·전체 공지 11건과 제한 확인 결과.
- `pdf/outlook_chunks.json`: 페이지별 800자 청크, 100자 겹침. 검증된 직업만 `job_code` 연결.
- `pdf/job_mapping.csv`: 50개 직업의 대응 상태와 검토 사유.
- `pdf/mapping_evidence.json`: 대응 후보의 API 업무 설명, PDF 인용문·페이지·항목 범위, 실제 연결 여부.
- `pdf/pdf_sections.json`: PDF 목차의 직업 150개와 항목 범위.
- `pdf/pdf_manifest.json`: PDF 해시, 출처, 판본과 추출 한계.
- `question_examples.json`: 일반·관계탐색·근거부족 질문 각 2개.
- `validation.json`: 최종 결과물 검증 기록.
- `reproduce/`: 원본 인계서와 실행 코드. 키 파일은 포함하지 않았다.

## 표본과 출처

직업백과의 연구직 및 공학 기술직(`searchJobCd=1`) 목록 1~5페이지를 API 순서 그대로 수집했다. 무작위 표본이나 IT 전용 50개가 아니다. 커리어넷의 50개 직업이 모두 2023판 PDF에 포함되는 것은 아니다.

공식 API 이용안내, 직업백과 명세, 매뉴얼 v4.1.2(97쪽), 공지 11건과 FAQ를 확인했지만 직업백과의 숫자로 된 일일·시간당 한도는 찾지 못했다. 무제한이라는 뜻은 아니다. 매뉴얼의 심리검사 이용량 제한은 직업백과 한도로 옮겨 적용하지 않았다.

- [커리어넷 API 이용안내](https://www.career.go.kr/cnet/front/openapi/openApiUseGuideCenter.do)
- [직업백과 명세](https://www.career.go.kr/cnet/front/openapi/jobCenter.do)
- [API 공지사항](https://www.career.go.kr/cnet/front/openapi/openApiNoticeCenter.do)
- [한국직업전망 공식 안내](https://www.data.go.kr/data/15140285/fileData.do)
- [한국고용정보원 원문 제공 페이지](https://www.keis.or.kr/keis/ko/proj/114/pblc/detail.do?categoryIdx=125&pubIdx=9672)

PDF SHA-256: `0b51d979abd6f92c454e3c65b19ef02baca012ea8487a048075c0bf42332907e`. 인계서의 검증 판본과 일치한다. 원문은 작업 폴더의 `work/outlook_2023.pdf`에 보관했다. ZIP에는 PDF 바이너리를 중복 포함하지 않았다. 공공데이터포털 메타데이터의 이용 조건은 공공누리 제2유형(출처표시·상업적 이용금지)이다.

## 대응 검토와 사용 방법

`exact`는 동일 명칭과 핵심 업무가 대응하는 11개, `verified_equivalent`는 건설공사품질관리원↔건설자재시험원, 대기환경기술자↔대기환경기술자 및 연구원, 통신공학 기술자 및 연구원↔통신공학기술자 및 연구원 3개이다. 업무 원문을 비교한 이번 수집의 검토 판단이며 공식 기관의 직업 ID 대응표는 아니다.

`partial`은 합쳐진 직업군, 더 넓거나 좁은 직무 범위이다. 검토 후보와 사유만 남겼으며 청크의 `job_code`는 비워 두었다. `unmatched` 역시 PDF 근거를 임의로 만들지 않았다. 같은 원칙으로 API 관련직업명은 다른 직업 노드와 임의 연결하지 않았다.

그래프 적재 시 API 관계 CSV로 직업-학과·자격·능력 관계를 만들고, PDF 청크에서는 `mapping_status`가 `exact` 또는 `verified_equivalent`인 항목만 직업에 연결하면 된다. PDF 답변에는 원문 제공 URL, `pdf_page`, 인용문을 함께 표시한다. 인쇄 페이지는 각 페이지 머리말에서 개별 추출했으며, 확인되지 않은 값은 null이다. 640개 페이지에서 머리말 숫자를 추출했지만 모든 인쇄 페이지를 눈으로 검수한 것은 아니다.

## 누락과 한계

- 직업 설명·학과·핵심능력·전망은 50개 모두 값이 있다.
- 빈 값: 관련 자격 17개, 자격 안내 18개, 직업훈련 38개, 입직·취업 방법 1개, 지식 4개. API 미제공 또는 빈 응답이며 '필요 없음'을 뜻하지 않는다. 누락값을 LLM으로 채우지 않았다.
- 관련 자격은 필수 자격과 다르다. `certificate_guidance`와 원문을 함께 확인해야 한다.
- `curriculum`은 직업 준비 교육 설명이며 학과의 실제 교과목 목록이 아니다. 지식 중요도 점수는 평탄화 CSV에 없고 원본 상세 응답에 보존했다.
- API 원문 수정일, 실제 수집일, 원문 내부 조사연도는 서로 다르다. 전망·임금 등을 2026년 새 조사 결과로 해석하지 않아야 한다. 2023판 PDF의 전망 기준은 주로 2021~2031년이다.
- 원문의 표현과 수치를 정정하거나 생성하지 않았다. 예를 들어 조경기술자 API 업무의 '조경기술사' 표현과 경제학연구원 PDF의 '정치학 전문지식' 표현은 원문 그대로이다.
- PDF 21·331·661쪽을 이미지와 추출문으로 대조했다. 전체 표와 모든 페이지의 읽기 순서·수치를 수동 검수하지는 않았다. 표·머리말·줄바꿈이 검색 및 문맥에 영향을 줄 수 있다.
- 초기 800자 청킹은 문장과 표를 분할할 수 있다. 실제 답변에서는 인접 청크와 원문 페이지를 확인해야 한다.
- PDF 관련학과를 별도의 그래프 관계로 추출하지 않았다. 학과 관계 176개는 API에서 직접 확보한 것이며, PDF 본문의 학교급이나 유사 표현을 학과로 만들어 넣지 않았다.
- Neo4j 적재와 챗봇 구현은 이번 데이터 수집 결과에 포함하지 않았다.

## 재실행

결과 확인에는 추가 API 호출이 필요 없다. 원본 작업 폴더의 `work/career_api_cache`는 삭제하지 않는다. 재현용 코드를 실행하려면 `reproduce` 폴더를 별도 작업 폴더로 사용하고, 포함된 빈 `.env.example`을 `.env`로 복사하여 본인의 허가된 키를 넣는다. `career_api/raw_cache`의 JSON 55개를 그 작업 폴더의 `work/career_api_cache`로 복사하면 기존 응답을 재사용할 수 있다. 키가 있어야 캐시 사용 코드도 시작할 수 있다.

Python 3.10 이상에서 `python work/collect_career_50.py`로 API 결과를 재생성할 수 있다. PDF 추출은 `python -m pip install pymupdf` 후 `python work/extract_outlook.py "PDF 절대경로"`로 실행한다. 기본 PDF 추출기를 재실행하면 매핑 메타데이터가 없는 초기 청크가 만들어지므로, 최종 검토된 결과를 덮어쓰지 말고 별도 폴더에서 실행한다. `finalize_collection.py`는 이번 검토 판단을 기록한 작업용 코드로 기본 재실행에 필요하지 않다.
