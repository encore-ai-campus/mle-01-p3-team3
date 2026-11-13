# 선택한 사용자 ID를 기준으로 개인정보와 현재·목표 커리어를 조회한다.
import sqlite3
from pathlib import Path


# profile.py -> tools -> app -> 프로젝트 루트 -> data
DATABASE_PATH = (
    Path(__file__).resolve().parents[2]
    /'data'
    /'careergraph_demo.db'
)

def load_own_career(user_id: str | None) -> dict:
    """선택한 회원 한 명의 개인정보와 현재·목표 커리어를 반환한다."""

    if not user_id:
        return {}

    # mode=ro: 기존 DB를 읽기 전용으로 연다.
    database_uri=DATABASE_PATH.as_uri() + '?mode=ro'

    with sqlite3.connect(database_uri,uri=True) as connection:
        # 조회 결과를 컬럼명으로 접근할 수 있게 한다.
        connection.row_factory = sqlite3.Row

        row = connection.execute(
            """
            SELECT
                u.user_id,
                u.display_name,
                u.email,
                u.phone,
                u.address,
                c.job_name AS current_job,
                c.major_name AS current_major,
                c.certificate_name AS current_certificate,
                f.job_name AS target_job,
                f.major_name AS target_major,
                f.certificate_name AS target_certificate
            From users AS u
            LEFT JOIN current_careers AS c ON u.user_id = c.user_id
            LEFT JOIN future_careers AS f ON u.user_id = f.user_id
            WHERE u.user_id =?
            """,(user_id,)
        ).fetchone()

        return dict(row) if row is not None else {}


if __name__ == "__main__":
    profile = load_own_career("U001")
    print(profile)






