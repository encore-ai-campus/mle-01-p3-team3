"""Neo4j 드라이버 접속 설정 테스트 (실제 Aura 에는 접속하지 않는다)."""

import certifi
from neo4j import TrustCustomCAs

from app.tools.search import _driver_target


def test_secure_scheme_uses_certifi_ca_with_verification_on():
    uri, security = _driver_target("neo4j+s://abcd1234.databases.neo4j.io")

    assert uri == "neo4j://abcd1234.databases.neo4j.io"
    assert security["encrypted"] is True
    trusted = security["trusted_certificates"]
    assert isinstance(trusted, TrustCustomCAs)
    assert trusted.certs == (certifi.where(),)


def test_bolt_secure_scheme_is_handled_the_same_way():
    uri, security = _driver_target("bolt+s://abcd1234.databases.neo4j.io:7687")

    assert uri == "bolt://abcd1234.databases.neo4j.io:7687"
    assert security["encrypted"] is True


def test_other_schemes_are_left_unchanged():
    for raw in ("neo4j://localhost:7687", "bolt://localhost:7687", "neo4j+ssc://host"):
        assert _driver_target(raw) == (raw, {})
