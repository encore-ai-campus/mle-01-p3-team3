# 가상 회원 SQLite 사용 안내

`careergraph_demo.db`는 가짜 회원 3명의 시연용 **초기 스냅샷**이다. `users`, `current_careers`, `future_careers`만 포함하며, `phone`·`address`에는 테스트 전용 가짜 값이 들어 있다. 실제 인물·개인정보를 넣지 않는다. 회원 선택은 실제 인증이 아니다. 회원 조회는 서버에서 현재 세션 ID로 제한해야 한다.

## 초기 DB 생성

프로젝트 루트에서 실행한다. 기존 파일이 있으면 중단하며 덮어쓰지 않는다. 로컬 `graph_nodes.csv`에서 시드 이름이 유형별로 유일하게 존재하는지 확인한다. Aura의 실제 노드·관계는 별도 검증한다.

```powershell
python data/init_careergraph_demo_db.py
```

다른 위치의 새 파일에 생성하려면 `--database`로 지정한다. 기존 DB 삭제·수정은 하지 않는다.

```powershell
python data/init_careergraph_demo_db.py --database data/demo_copy.db
```

## 읽기 전용 조회

배포용 DB를 읽기 전용으로 열면 이 연결로 파일에 쓸 수 없다. 사용자 식별은 서버 세션에서 제공해야 하며, 아래 값은 시연 예시다.

```python
import sqlite3
from pathlib import Path

path = Path('data/careergraph_demo.db').resolve()
with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
    row = db.execute(
        'SELECT job_name, major_name, certificate_name FROM current_careers WHERE user_id = ?',
        ('U001',),  # 실제 앱에서는 서버에서 확정한 세션 ID를 사용
    ).fetchone()
```

이 코드는 연결 및 SQL 예시이며 접근 제어 구현이 아니다. 읽기 전용 SQLite 연결은 앱 수준의 본인 확인을 대체하지 않는다.

## Git LFS와 런타임 변경

`.gitattributes`는 이 스냅샷 파일만 LFS로 지정한다. `git add`·커밋·푸시는 팀이 수행하며, Streamlit Community Cloud에서 LFS 객체가 정상 내려왔는지 실제 배포 로그와 앱에서 확인한다. LFS는 파일의 크기 관리 방식이지 SQLite 변경을 숨기지 않는다. 원본은 읽기 전용으로 사용하고, 쓰기나 체크포인트 DB는 Git 추적 대상과 분리한다.

현재·목표 값을 웹에서 수정해야 한다면 초기 스냅샷을 무시되는 런타임 경로에 복사해 사용하거나 외부 영속 DB를 사용한다. Streamlit Community Cloud의 로컬 파일은 영속이 보장되지 않는다. 동시 세션이 하나의 런타임 DB를 공유하는 점과 접근 제어를 별도로 설계한다. `-wal`, `-shm`, `-journal`은 실행 중 SQLite가 관리하므로 임의로 삭제하지 않는다.

원인 진단은 `git status --short`, `git diff --stat`, DB 파일 해시를 조회 전후 비교해 실제 DB 본문이 바뀐 것인지 보조 파일이 생긴 것인지 구분한다. 쿼리 외의 초기화, 스키마 변경, 연결 설정, 체크포인트도 확인한다. `assume-unchanged`나 `skip-worktree`로 변경을 숨기지 않는다.
## Neo4j 이름 매칭

직업·학과·자격 이름을 각각 `Job.name`, `Major.name`, `Certificate.name`에 정확히 일치시켜 찾는다. 유형을 반드시 구분하고 0건이면 확인 불가, 여러 건이면 모호함으로 처리한다. 이름만 같다고 임의 선택하지 않는다. 실제 관계의 존재도 따로 확인하며, 수집 데이터와 Aura가 변경되면 재검증한다.
