"""PostgreSQL upsert helpers for audit_events and event_policies.

Callers are responsible for conn.commit() after calling these functions.
On exception, callers must call conn.rollback() before reusing the connection.
"""

from psycopg2.extras import execute_values

_UPSERT_SQL = """
INSERT INTO audit_events (
    id, created_at, action, is_dry_run, package_type, package_name, package_version,
    package_url, reason, event_origin, curated_repository_name,
    curated_repository_server_name, curated_project, username, user_mail,
    origin_repository_name, origin_repository_server_name, origin_project,
    public_repo_url, public_repo_name
) VALUES %s
ON CONFLICT (id) DO UPDATE SET
    action                         = EXCLUDED.action,
    reason                         = EXCLUDED.reason,
    username                       = EXCLUDED.username,
    user_mail                      = EXCLUDED.user_mail,
    package_version                = EXCLUDED.package_version,
    package_type                   = EXCLUDED.package_type,
    package_name                   = EXCLUDED.package_name,
    package_url                    = EXCLUDED.package_url,
    event_origin                   = EXCLUDED.event_origin,
    curated_repository_name        = EXCLUDED.curated_repository_name,
    curated_repository_server_name = EXCLUDED.curated_repository_server_name,
    curated_project                = EXCLUDED.curated_project,
    origin_repository_name         = EXCLUDED.origin_repository_name,
    origin_repository_server_name  = EXCLUDED.origin_repository_server_name,
    origin_project                 = EXCLUDED.origin_project,
    public_repo_url                = EXCLUDED.public_repo_url,
    public_repo_name               = EXCLUDED.public_repo_name
    -- is_dry_run intentionally excluded: dry-run status is immutable once written
"""

_DELETE_POLICIES = "DELETE FROM event_policies WHERE event_id = %s"

_INSERT_POLICIES = """
INSERT INTO event_policies (event_id, policy_name, rule_name, policy_action, cve_id, severity)
VALUES %s
"""


def upsert_events(conn, events: list, is_dry_run: bool) -> int:
    """Upsert a list of API event dicts into audit_events. Returns count processed."""
    if not events:
        return 0
    rows = [_event_row(e, is_dry_run) for e in events]
    with conn.cursor() as cur:
        execute_values(cur, _UPSERT_SQL, rows)
    return len(rows)


def upsert_policies(conn, event_id: int, policies: list) -> int:
    """Replace all policy rows for an event. Returns count inserted."""
    with conn.cursor() as cur:
        cur.execute(_DELETE_POLICIES, (event_id,))
    if not policies:
        return 0
    rows = [
        (
            event_id,
            p.get("policy_name") or p.get("name"),
            p.get("rule_name") or p.get("rule"),
            p.get("policy_action") or p.get("action"),
            p.get("cve_id"),
            p.get("severity"),
        )
        for p in policies
    ]
    with conn.cursor() as cur:
        execute_values(cur, _INSERT_POLICIES, rows)
    return len(rows)


def _event_row(event: dict, is_dry_run: bool) -> tuple:
    return (
        event["id"],
        event["created_at"],
        event.get("action"),
        is_dry_run,
        event.get("package_type"),
        event.get("package_name"),
        event.get("package_version"),
        event.get("package_url"),
        event.get("reason"),
        event.get("event_origin"),
        event.get("curated_repository_name"),
        event.get("curated_repository_server_name"),
        event.get("curated_project"),
        event.get("username"),
        event.get("user_mail"),
        event.get("origin_repository_name"),
        event.get("origin_repository_server_name"),
        event.get("origin_project"),
        event.get("public_repo_url"),
        event.get("public_repo_name"),
    )
