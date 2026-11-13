import argparse
import csv
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "expanded_20261108"
BATCH_SIZE = 200

LABELS = {
    "Job": "Job",
    "Major": "Major",
    "Certificate": "Certificate",
    "Ability": "Ability",
}

RELATIONS = {
    "관련학과": "RELATED_MAJOR",
    "관련자격": "RELATED_CERTIFICATE",
    "핵심능력": "HAS_CORE_ABILITY",
}


def read_csv(name):
    with (DATA / name).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def batches(rows):
    for start in range(0, len(rows), BATCH_SIZE):
        yield rows[start : start + BATCH_SIZE]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--load", action="store_true", help="Aura에 실제 적재")
    args = parser.parse_args()

    nodes = read_csv("graph_nodes.csv")
    edges = read_csv("graph_edges.csv")
    jobs = read_csv("jobs.csv")

    node_ids = {row["id"] for row in nodes}
    job_codes = {row["job_code"] for row in jobs}

    if len(nodes) != len(node_ids):
        raise ValueError("중복 노드 ID가 있습니다.")
    if len(jobs) != len(job_codes):
        raise ValueError("중복 직업 코드가 있습니다.")
    if any(
        row["start_id"] not in node_ids or row["end_id"] not in node_ids
        for row in edges
    ):
        raise ValueError("관계의 시작 또는 끝 노드가 없습니다.")
    if any(row["type"] not in LABELS for row in nodes):
        raise ValueError("알 수 없는 노드 종류가 있습니다.")
    if any(row["relation"] not in RELATIONS for row in edges):
        raise ValueError("알 수 없는 관계 종류가 있습니다.")

    print("노드:", len(nodes), dict(Counter(r["type"] for r in nodes)))
    print("관계:", len(edges), dict(Counter(r["relation"] for r in edges)))
    print("직업 속성 행:", len(jobs))

    if not args.load:
        print("파일 점검만 완료. Aura에는 쓰지 않았습니다.")
        return

    load_dotenv(ROOT / ".env", override=True)
    uri = os.environ["NEO4J_URI"]
    user = os.environ["NEO4J_USERNAME"]
    password = os.environ["NEO4J_PASSWORD"]
    database = os.getenv("NEO4J_DATABASE", "neo4j")

    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        print("Aura 연결 성공. 대상 DB:", database)

        for label in LABELS.values():
            driver.execute_query(
                f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.id IS UNIQUE",
                database_=database,
            )

        for node_type, label in LABELS.items():
            selected = [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "source": row["source"],
                    "source_id": row["source_id"] or None,
                }
                for row in nodes
                if row["type"] == node_type
            ]
            query = (
                f"UNWIND $rows AS row "
                f"MERGE (n:{label} {{id: row.id}}) "
                f"SET n.name = row.name, "
                f"n.source = row.source, "
                f"n.source_id = row.source_id"
            )
            for batch in batches(selected):
                driver.execute_query(query, rows=batch, database_=database)
            print("노드 적재:", label, len(selected))

        job_rows = []
        for row in jobs:
            properties = {
                "job_group": row["job_group"],
                "occupation_class": row["occupation_class"],
                "work": row["work"],
                "certificate_guidance": row["certificate_guidance"],
                "curriculum": row["curriculum"],
                "training": row["training"],
                "recruitment": row["recruitment"],
                "aptitude": row["aptitude"],
                "interests": row["interests"],
                "knowledge": row["knowledge"],
                "forecast": row["forecast"],
                "source_updated": row["source_updated"],
                "collected_date": row["collected_date"],
                "source_file": f"cache/{row['raw_file']}",
            }
            job_rows.append({
                "id": f"job:{row['job_code']}",
                "properties": {
                    key: value
                    for key, value in properties.items()
                    if value != ""
                },
            })

        for batch in batches(job_rows):
            driver.execute_query(
                "UNWIND $rows AS row "
                "MATCH (j:Job {id: row.id}) "
                "SET j += row.properties",
                rows=batch,
                database_=database,
            )
        print("직업 속성 보강:", len(job_rows))

        for original_name, relationship_type in RELATIONS.items():
            selected = [
                row for row in edges
                if row["relation"] == original_name
            ]
            query = (
                f"UNWIND $rows AS row "
                f"MATCH (a {{id: row.start_id}}) "
                f"MATCH (b {{id: row.end_id}}) "
                f"MERGE (a)-[r:{relationship_type}]->(b) "
                f"SET r.source_file = row.source_file, "
                f"r.source_field = row.source_field, "
                f"r.source_url_without_key = row.source_url_without_key, "
                f"r.evidence_type = row.evidence_type"
            )
            for batch in batches(selected):
                driver.execute_query(query, rows=batch, database_=database)
            print("관계 적재:", relationship_type, len(selected))

        records, _, _ = driver.execute_query(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS count "
            "ORDER BY count DESC",
            database_=database,
        )
        print("DB 노드 결과:", [dict(record) for record in records])

        records, _, _ = driver.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count "
            "ORDER BY count DESC",
            database_=database,
        )
        print("DB 관계 결과:", [dict(record) for record in records])


if __name__ == "__main__":
    main()