# CareerGraph 직업 업무 임베딩 및 Neo4j 적재 인계서

> 문서 상태: 실행 계획. 적재 결과나 검색 성능을 보증하지 않는다. Neo4j의 현재 상태는 작업 시작 시 다시 확인한다.

## 1. 목적과 합의된 범위

커리어넷 직업의 `work`(하는 일)를 임베딩해 Neo4j Aura에서 의미 검색한다. 직업별 업무 설명 하나를 하나의 검색 단위로 사용한다. PDF, 적성, 전망 등 다른 설명은 이번 벡터 검색 범위에서 제외한다. 관련 학과·자격·능력은 기존 그래프 관계로 조회한다. 관련 자격을 필수 자격으로 단정하지 않는다.

- 문서와 사용자 질문 모델: `text-embedding-3-small`, **768차원**.
- 임베딩 입력 예시: `직업명: 일기예보관\n하는 일: <work 원문>` (`\n`은 실제 개행으로 구성).
- 검색 결과 메타데이터: `job_code`, `job_name`, 원본 `work` 텍스트 세 항목. 기존 `Job.source_id`, `Job.name`, `Job.work`에서 반환한다.
- 예시 벡터 속성: `Job.work_embedding`. 예시 인덱스: `job_work_embedding_768`, 코사인 유사도.
- 임베딩 모델·차원·입력 버전·텍스트 해시는 재실행과 변경 감지에 필요한 **운영 기록**으로 관리하며, 위 검색 결과 메타데이터와 구분한다.

## 2. 기존 상태와 주의점

이전 읽기 전용 확인에서 `Job` 552개에 `work` 속성이 있었다. 기존 `CareerApiChunk` 100개는 적성 95개·전망 5개이며 95개 직업에 연결됐다. 이 100개는 `text-embedding-3-small` 768차원으로, 별도 `career_api_chunk_768` 인덱스에 저장돼 있었다. 이 수치는 확인 당시의 기록이므로 현재 상태를 다시 조회한다.

**기존 100개는 work 벡터가 아니었다.** 따라서 work를 임베딩할 때는 100개를 뺀 나머지가 아니라, 업무 설명이 있는 전체 직업을 대상으로 한다. 기존 테스트 데이터·인덱스와 그래프는 삭제하지 않는다. 이미 다른 팀원이 같은 속성 또는 인덱스를 사용 중이면 소유자·설정을 확인하고 충돌 없이 조율한다.

Job 속성은 확인 당시 `id`(예: `job:5`), `source_id`(예: `5`), `name`, `work`였다. 실제 속성명과 값 타입은 착수 시 확인하고, 이름이 아닌 안정적인 ID로 정확히 매칭한다.

## 3. 환경 준비

1. 프로젝트 루트에서 작업하고 팀의 기존 가상환경과 의존성 관리 방식을 따른다. `.env.example`, README, 기존 적재 코드와 팀원의 최신 변경을 먼저 확인한다.
2. 로컬 `.env`에는 `OPENAI_API_KEY`, `NEO4J_URI`, `NEO4J_PASSWORD`와 사용자명(`NEO4J_USERNAME` 또는 팀 코드가 사용하는 이름), 필요 시 `NEO4J_DATABASE`를 설정한다. **값은 코드, 프롬프트, 로그, 스크린샷, 보고서, Git에 넣지 않는다.**
3. 비용은 토큰 사용량과 모델의 현재 요금으로 계산한다. 소량 시험 후 잔여 토큰과 예상 비용을 확인하고 호출한다. 네트워크·API 오류는 실패 건수와 재시도 결과를 남긴다.
4. 실제 DB 쓰기 권한을 사용하는 작업이다. 팀이 공유하는 Aura의 기존 데이터·동시 작업 여부를 먼저 확인한다. 임베딩은 로컬 또는 관리되는 배치 작업에서 수행하고 앱 시작마다 반복하지 않는다.

## 4. 사전 점검: 읽기 전용

먼저 노드, 실제 비어 있지 않은 `work`, 기존 벡터 수를 확인한다. 속성이 없으면 `count(j.work_embedding)`은 0이다.

```cypher
MATCH (j:Job)
RETURN count(j) AS total_jobs,
       count(CASE WHEN j.work IS NOT NULL AND trim(j.work) <> '' THEN 1 END) AS jobs_with_work,
       count(j.work_embedding) AS existing_work_embeddings;
```

중복과 누락 ID도 확인한다.

```cypher
MATCH (j:Job)
RETURN count(j) AS total,
       count(j.id) AS with_id,
       count(DISTINCT j.id) AS distinct_ids,
       count(j.source_id) AS with_source_id,
       count(DISTINCT j.source_id) AS distinct_source_ids;
```

기존 인덱스의 이름·라벨·속성·차원·상태를 확인한다.

```cypher
SHOW INDEXES
YIELD name, type, state, labelsOrTypes, properties, options
WHERE type = 'VECTOR'
RETURN name, type, state, labelsOrTypes, properties, options;
```

기존 `job_work_embedding_768` 또는 `work_embedding`이 있으면 임의로 삭제·덮어쓰지 않는다. 모델, 차원, 입력 생성 방식, 대상 범위를 확인해 팀과 조율한다. 이름이 같다는 이유로 호환된다고 가정하지 않는다.

## 5. 임베딩 및 적재 순서

1. **입력 확정:** 비어 있지 않은 `work`와 직업명을 가져온다. 원문 `work`는 원형으로 보존한다. 임베딩 입력의 포맷·모델·차원·버전을 고정한다. 문서가 모델 입력 제한을 초과하는지는 토큰으로 사전 확인하고, 초과 항목은 조용히 잘라 넣지 않고 별도 기록·처리한다.
2. **소량 시험:** 5~10개를 `text-embedding-3-small`, `dimensions=768`로 호출한다. 반환 개수·벡터 차원과 직업 ID가 일치하는지 확인한다. 기존 Job에만 기록하고 찾지 못한 ID는 오류로 기록한다.
3. **재실행 안전성:** 기존 벡터의 모델·차원과 입력 텍스트 해시가 같으면 건너뛴다. 벡터만 있고 출처 정보가 불명확하거나 입력이 달라진 경우 무조건 건너뛰거나 덮어쓰지 말고 대상·처리 방식을 팀과 조율한다. 운영 기록에는 성공·실패 ID, 입력 버전·해시, 모델·차원, 토큰 사용량을 남긴다.
4. **전체 처리:** 소량 검증 성공 후 나머지를 배치로 임베딩해 `Job.work_embedding`에 저장한다. 모델 호출과 DB 기록을 분리해 실패한 항목을 재개할 수 있게 한다. 실패가 나면 오류 유형을 확인하고 제한을 고려해 재시도한다.
5. **인덱스 생성:** 아래 인덱스가 없을 때만 생성한다. 존재하면 속성과 차원을 확인한다. 필요 시 팀과 이름을 합의한다.

```cypher
CREATE VECTOR INDEX job_work_embedding_768 IF NOT EXISTS
FOR (j:Job) ON j.work_embedding
OPTIONS {indexConfig: {
  `vector.dimensions`: 768,
  `vector.similarity_function`: 'cosine'
}};
```

벡터 인덱스가 `ONLINE`이 된 뒤 검색한다. `IF NOT EXISTS`가 기존 인덱스 설정이 올바른지 확인해 주지는 않는다. Aura의 실제 버전·권한·용량 및 인덱스 호환성은 실행 환경에서 검증한다.

## 6. 적재 후 검증

```cypher
MATCH (j:Job)
RETURN count(j) AS total_jobs,
       count(CASE WHEN j.work IS NOT NULL AND trim(j.work) <> '' THEN 1 END) AS jobs_with_work,
       count(j.work_embedding) AS embedded_jobs,
       count(CASE WHEN j.work_embedding IS NOT NULL
                  AND size(j.work_embedding) <> 768 THEN 1 END) AS wrong_dimension;
```

- 각 값은 실제 데이터 상태를 따른다. 앞선 확인 당시 552개 직업에 `work` 속성이 있었으나, 빈 값·기존 벡터의 모델과 해시는 별도로 확인한다.
- `SHOW INDEXES`로 인덱스가 원하는 `Job.work_embedding`, 768차원, cosine, `ONLINE`인지 확인한다.
- 성공·건너뜀·빈 값·실패 건수의 합이 대상과 맞는지 확인한다. 샘플 직업에서 벡터가 올바른 ID에 저장됐는지 비교한다.
- 동일 모델·차원의 질문 벡터로 “일기예보관은 어떤 일을 하나요?”, “날씨 관측 자료를 분석해 예보하는 직업은?”을 검색하고 반환된 직업명·원문을 확인한다. 인덱스 상태만으로 품질을 보증하지 않는다.
- 검색된 `source_id`에서 기존 학과·자격 관계를 실제로 조회한다. 관련 자격은 필수라는 뜻이 아니다.
- 평가 초안 중 업무 검색 항목은 정답을 확인한 후 사용한다. 직업명을 그대로 포함한 8개 질문만으로 일반화하지 말고 직업명을 생략한 질문도 별도 검토한다.

## 7. 앱 연결과 시연

이전 확인 시 앱 설정은 `text-embedding-3-large`, 768차원, 검색 인덱스 기본값 `career_embedding_index`였고 검색 코드는 `content`, `source`를 반환하려 했다. 실제로 작업을 시작할 때 최신 코드를 다시 확인한다. 이번 인덱스를 사용하려면 **질문 모델 small·768차원**, 인덱스 `job_work_embedding_768`, 반환 속성 `source_id`, `name`, `work`를 일치시켜야 한다. 같은 차원이더라도 서로 다른 모델의 벡터를 혼용하지 않는다.

또한 이전 확인 당시 `.env` 사용자명은 `NEO4J_USERNAME`이었고 앱 설정은 `NEO4J_USER` 또는 `AURA_USER`를 읽었다. 실제 환경과 코드의 변수명을 맞춰 연결을 검증한다. 사용할 Cypher 벡터 검색 문법은 팀의 Aura 버전과 코드에 맞춰 검토한다.

인덱싱은 오프라인에서 실행한다. 사용자 질문만 검색 시 임베딩하며 외부 API의 비용·지연·오류를 처리한다. Streamlit과 Aura에서 실제 질문으로 동작하는지 별도 검증한다.

## 8. 동료에게 전달할 Codex 프롬프트

```text
CareerGraph 프로젝트에서 커리어넷 직업 업무 설명을 Neo4j Aura에
벡터 검색용으로 적재하려고 해. 프로젝트 docs의 이 인계서를 읽고 시작해 줘.

먼저 프로젝트 코드와 현재 Neo4j 상태를 읽기 전용으로 확인해 줘.
접속 정보는 프로젝트 루트의 .env에 있으며, 키나 비밀번호는 출력하거나
문서·로그·Git에 저장하지 마.

조건:
- 대상: 기존 Neo4j Job 노드의 비어 있지 않은 work 속성
- 단위: 직업 1개당 work 1개
- 모델: OpenAI text-embedding-3-small, dimensions=768
- 임베딩 입력: 직업명과 work를 구분해서 함께 전달
- 기존 Job 노드의 work_embedding에 저장
- 검색 결과 반환: source_id(job_code), name(job_name), 원본 work
- 인덱스: job_work_embedding_768, cosine, 768차원
- PDF는 사용하지 않고 학과·관련 자격·능력은 기존 Neo4j 관계 사용
- 기존 career_api_chunk_768 테스트 인덱스와 기존 그래프는 보존
- 검색 메타데이터 세 항목과 재실행용 운영 기록을 구분

작업 순서:
1. Job 수, 비어 있지 않은 work 수, 중복 식별자, 기존 벡터와 인덱스 확인.
2. 기존 적재 코드와 팀원의 최신 변경을 확인하고 재사용 가능성 판단.
3. 5~10개 직업으로 임베딩·차원·노드 매칭 시험.
4. 성공하면 나머지를 배치 처리. 재실행 시 모델·차원·입력 해시가
   같은 경우 건너뛰고, 불일치·출처 미상은 조율. 실패와 토큰 수 기록.
5. 전용 인덱스가 없으면 생성. 이미 있으면 설정을 확인하고 보존.
6. 전체·성공·건너뜀·빈 값·실패 건수, 차원, ONLINE 상태 검증.
7. 실제 질문 검색과 검색 결과의 직업 코드·이름·업무 원문 확인.
8. 앱의 질문 임베딩 모델·차원·인덱스·결과 속성을 맞추고 검증.
9. 실행 전후 건수, 질문별 검색 결과, 실패, 사용 토큰과 비용을 보고.

기존 팀원 작업과 DB 상태를 보존하고, 실제 확인하지 않은 결과는
완료됐다고 표시하지 마.
```

## 9. 관련 문서

- [기초 시스템 설계도](CareerGraph_기초_시스템_설계도.md)
- [역할 분담과 일정](CareerGraph_5일_역할분담_일정.md)
- [데이터 안내](../data/README.md)