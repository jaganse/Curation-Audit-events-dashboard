CREATE TABLE IF NOT EXISTS audit_events (
    id                             BIGINT PRIMARY KEY,
    created_at                     TIMESTAMPTZ NOT NULL,
    action                         VARCHAR(20),
    is_dry_run                     BOOLEAN NOT NULL DEFAULT FALSE,
    package_type                   VARCHAR(50),
    package_name                   VARCHAR(255),
    package_version                VARCHAR(100),
    package_url                    TEXT,
    reason                         TEXT,
    event_origin                   VARCHAR(255),
    curated_repository_name        VARCHAR(255),
    curated_repository_server_name VARCHAR(255),
    curated_project                VARCHAR(255),
    username                       VARCHAR(255),
    user_mail                      VARCHAR(255),
    origin_repository_name         VARCHAR(255),
    origin_repository_server_name  VARCHAR(255),
    origin_project                 VARCHAR(255),
    public_repo_url                TEXT,
    public_repo_name               VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_audit_events_created_at   ON audit_events (created_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_action        ON audit_events (action);
CREATE INDEX IF NOT EXISTS idx_audit_events_is_dry_run    ON audit_events (is_dry_run);
CREATE INDEX IF NOT EXISTS idx_audit_events_package_type  ON audit_events (package_type);
CREATE INDEX IF NOT EXISTS idx_audit_events_username      ON audit_events (username);
CREATE INDEX IF NOT EXISTS idx_audit_events_is_dry_run_created_at ON audit_events (is_dry_run, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_is_dry_run_action_created_at ON audit_events (is_dry_run, action, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_events_curated_repository_name ON audit_events (curated_repository_name);

CREATE TABLE IF NOT EXISTS event_policies (
    id                 SERIAL PRIMARY KEY,
    event_id           BIGINT NOT NULL REFERENCES audit_events(id) ON DELETE CASCADE,
    policy_name        VARCHAR(255),
    rule_name          VARCHAR(255),
    policy_action      VARCHAR(50),
    cve_id             VARCHAR(50),
    severity           VARCHAR(20),
    condition_name     VARCHAR(255),
    condition_category VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_event_policies_event_id    ON event_policies (event_id);
CREATE INDEX IF NOT EXISTS idx_event_policies_policy_name ON event_policies (policy_name);

-- =============================================================================
-- mv_download_windows
--
-- Implements a 12-hour session window count per (is_dry_run, user, package,
-- version, action). A new window is counted each time an event occurs >= 12h
-- after the immediately preceding event in the same group (sorted by
-- created_at).
--
-- This is a gap-from-previous approximation of the greedy window sweep in
-- GetAuditTimeWindow.py. It is exact when events are spaced >= 12h apart and
-- slightly under-counts in the edge case where 3+ events fall within a 12–24h
-- drift window (e.g. T+0, T+6h, T+13h counts as 1 window instead of 2).
-- For the "persistence of behavior" use case this approximation is accurate.
--
-- Refreshed after each ETL run via REFRESH MATERIALIZED VIEW CONCURRENTLY.
-- The unique index on event_id is required for CONCURRENTLY refresh.
-- =============================================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_download_windows AS
WITH ranked AS (
    SELECT
        ae.id                      AS event_id,
        ae.created_at,
        ae.is_dry_run,
        ae.action,
        ae.username,
        ae.package_name,
        ae.package_version,
        ae.package_type,
        ae.curated_repository_name,
        LAG(ae.created_at) OVER (
            PARTITION BY ae.is_dry_run,
                         ae.username,
                         ae.package_name,
                         ae.package_version,
                         ae.action
            ORDER BY ae.created_at
        ) AS prev_created_at
    FROM audit_events ae
),
windowed AS (
    SELECT
        event_id,
        created_at,
        is_dry_run,
        action,
        username,
        package_name,
        package_version,
        package_type,
        curated_repository_name,
        CASE
            WHEN prev_created_at IS NULL
              OR created_at - prev_created_at >= INTERVAL '12 hours'
            THEN 1
            ELSE 0
        END AS is_window_start
    FROM ranked
)
SELECT
    event_id,
    created_at,
    is_dry_run,
    action,
    username,
    package_name,
    package_version,
    package_type,
    curated_repository_name,
    is_window_start,
    SUM(is_window_start) OVER (
        PARTITION BY is_dry_run,
                     username,
                     package_name,
                     package_version,
                     action
        ORDER BY created_at
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_window_number
FROM windowed
WITH DATA;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_download_windows_event_id
    ON mv_download_windows (event_id);
CREATE INDEX IF NOT EXISTS idx_mv_dw_user_pkg
    ON mv_download_windows (is_dry_run, username, package_name, package_version);
CREATE INDEX IF NOT EXISTS idx_mv_dw_action_created_at
    ON mv_download_windows (is_dry_run, action, created_at);
