"""CareerGraph 가상 회원 초기 DB 생성. 기존 파일은 수정하지 않는다."""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
USERS = [
    ('U001', '데모 회원 1', 'user01@example.com', '010-0000-0001', '가상시 데모구 예시로 1'),
    ('U002', '데모 회원 2', 'user02@example.com', '010-0000-0002', '가상시 데모구 예시로 2'),
    ('U003', '데모 회원 3', 'user03@example.com', '010-0000-0003', '가상시 데모구 예시로 3'),
]
CURRENT = [
    ('U001', '일기예보관', '대기과학과', '기상기사'),
    ('U002', '간호사', '간호학과', '간호사'),
    ('U003', '게임기획자', '컴퓨터공학과', '게임기획전문가'),
]
FUTURE = [
    ('U001', '기상연구원', '대기과학과', '기상예보기술사'),
    ('U002', '호스피스전문간호사', '간호학과', '간호사'),
    ('U003', '비디오게임디자이너', '게임공학과', None),
]


def validate_nodes(path: Path) -> None:
    with path.open(encoding='utf-8-sig', newline='') as f:
        nodes = [(row['name'], row['type']) for row in csv.DictReader(f)]
    problems = []
    for _, job, major, certificate in CURRENT + FUTURE:
        for name, kind in ((job, 'Job'), (major, 'Major'), (certificate, 'Certificate')):
            if name is not None and nodes.count((name, kind)) != 1:
                problems.append(f'{kind}: {name} (일치 {nodes.count((name, kind))}건)')
    if problems:
        raise ValueError('그래프 이름 누락 또는 중복: ' + ', '.join(problems))



def create_database(destination: Path, graph_nodes: Path) -> None:
    validate_nodes(graph_nodes)
    destination = destination.resolve()
    if not destination.parent.is_dir():
        raise FileNotFoundError(f'상위 디렉터리가 없습니다: {destination.parent}')
    # O_EXCL로 기존 파일을 덮어쓰거나 같은 파일에 동시 생성하는 것을 방지한다.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        con = sqlite3.connect(destination)
        try:
            con.execute('PRAGMA foreign_keys=ON')
            with con:
                con.execute('CREATE TABLE users (user_id TEXT NOT NULL PRIMARY KEY, display_name TEXT NOT NULL, email TEXT, phone TEXT, address TEXT)')
                for table in ('current_careers', 'future_careers'):
                    con.execute(f'CREATE TABLE {table} (user_id TEXT NOT NULL PRIMARY KEY REFERENCES users(user_id), job_name TEXT, major_name TEXT, certificate_name TEXT)')
                con.executemany('INSERT INTO users VALUES (?, ?, ?, ?, ?)', USERS)
                con.executemany('INSERT INTO current_careers VALUES (?, ?, ?, ?)', CURRENT)
                con.executemany('INSERT INTO future_careers VALUES (?, ?, ?, ?)', FUTURE)
                if con.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('외래 키 검사 실패')
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite 무결성 검사 실패')
        finally:
            con.close()
    except BaseException:
        # 이 프로세스가 독점 생성한 불완전한 파일만 삭제한다.
        destination.unlink(missing_ok=True)
        raise
    print(f'생성 완료: {destination} (가상 회원 3명, 현재·목표 커리어 각 3건)')
    print('그래프 이름은 로컬 CSV에서 유형별 유일성을 확인했습니다. Aura는 별도 확인하세요.')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DATA_DIR / 'careergraph_demo.db')
    parser.add_argument('--graph-nodes', type=Path, default=DATA_DIR / 'expanded_20261108' / 'graph_nodes.csv')
    args = parser.parse_args()
    create_database(args.database, args.graph_nodes)


if __name__ == '__main__':
    main()