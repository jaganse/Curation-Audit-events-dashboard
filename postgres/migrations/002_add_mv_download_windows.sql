-- Migration 002: add mv_download_windows materialized view
-- Run once against existing databases that were initialized before this view
-- was added to init.sql.

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
