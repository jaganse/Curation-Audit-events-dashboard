import os

import psycopg2
import pytest

from etl.storage import upsert_events, upsert_policies

DB_URL = os.environ.get("DATABASE_URL", "postgresql://audit:audit@localhost:5432/audit")

TEST_ID_BASE = 9_999_000


@pytest.fixture
def conn():
    c = psycopg2.connect(DB_URL)
    yield c
    with c.cursor() as cur:
        cur.execute(
            "DELETE FROM event_policies WHERE event_id IN "
            "(SELECT id FROM audit_events WHERE package_name LIKE 'test-%')"
        )
        cur.execute("DELETE FROM audit_events WHERE package_name LIKE 'test-%'")
    c.commit()
    c.close()


def _event(seq=1, package_name="test-lodash", action="approved"):
    return {
        "id": TEST_ID_BASE + seq,
        "created_at": "2026-03-09T14:51:04Z",
        "action": action,
        "package_type": "npm",
        "package_name": package_name,
        "package_version": "1.0.0",
        "package_url": "https://registry.npmjs.org/test-lodash/-/test-lodash-1.0.0.tgz",
        "reason": "No policy violations",
        "event_origin": "Download to repository",
        "curated_repository_name": "test-repo",
        "curated_repository_server_name": "",
        "curated_project": "default",
        "username": "test@example.com",
        "user_mail": "test@example.com",
        "origin_repository_name": "test-repo",
        "origin_repository_server_name": "hts1",
        "origin_project": "default",
        "public_repo_url": "https://registry.npmjs.org",
        "public_repo_name": "npm registry",
        "policies": None,
    }


def test_upsert_inserts(conn):
    count = upsert_events(conn, [_event(1)], is_dry_run=False)
    assert count == 1
    with conn.cursor() as cur:
        cur.execute("SELECT action, is_dry_run FROM audit_events WHERE id = %s", (TEST_ID_BASE + 1,))
        assert cur.fetchone() == ("approved", False)


def test_upsert_idempotent(conn):
    upsert_events(conn, [_event(2)], is_dry_run=False)
    upsert_events(conn, [_event(2)], is_dry_run=False)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM audit_events WHERE id = %s", (TEST_ID_BASE + 2,))
        assert cur.fetchone()[0] == 1


def test_upsert_empty(conn):
    assert upsert_events(conn, [], is_dry_run=False) == 0


def test_upsert_sets_dry_run_flag(conn):
    upsert_events(conn, [_event(3, package_name="test-dry")], is_dry_run=True)
    with conn.cursor() as cur:
        cur.execute("SELECT is_dry_run FROM audit_events WHERE id = %s", (TEST_ID_BASE + 3,))
        assert cur.fetchone()[0] is True


def test_policies_inserts(conn):
    upsert_events(conn, [_event(4, package_name="test-blocked", action="blocked")], is_dry_run=False)
    policies = [
        {
            "policy_name": "security-policy",
            "rule_name": "high-cve",
            "policy_action": "block",
            "cve_id": "CVE-2021-44228",
            "severity": "CRITICAL",
        }
    ]
    count = upsert_policies(conn, TEST_ID_BASE + 4, policies)
    assert count == 1
    with conn.cursor() as cur:
        cur.execute(
            "SELECT policy_name, severity FROM event_policies WHERE event_id = %s",
            (TEST_ID_BASE + 4,),
        )
        assert cur.fetchone() == ("security-policy", "CRITICAL")


def test_policies_replaces_existing(conn):
    upsert_events(conn, [_event(5, package_name="test-replace", action="blocked")], is_dry_run=False)
    upsert_policies(conn, TEST_ID_BASE + 5, [{"policy_name": "old", "rule_name": "r", "policy_action": "block", "cve_id": None, "severity": None}])
    upsert_policies(conn, TEST_ID_BASE + 5, [{"policy_name": "new", "rule_name": "r", "policy_action": "block", "cve_id": None, "severity": None}])
    with conn.cursor() as cur:
        cur.execute("SELECT policy_name FROM event_policies WHERE event_id = %s", (TEST_ID_BASE + 5,))
        rows = [r[0] for r in cur.fetchall()]
    assert rows == ["new"]


def test_policies_empty(conn):
    upsert_events(conn, [_event(6, package_name="test-nopol")], is_dry_run=False)
    assert upsert_policies(conn, TEST_ID_BASE + 6, []) == 0
