#!/usr/bin/env python3
"""Generate Grafana dashboard JSON files for provisioning.

Run: python scripts/generate_dashboards.py
Output: grafana/provisioning/dashboards/real-events.json
        grafana/provisioning/dashboards/dry-run.json
"""
import json
import os

OUT_DIR = "grafana/provisioning/dashboards"
DS_REF = {"type": "postgres", "uid": "curation_pg"}


def _stat(title, sql, color, grid_x, grid_y, grid_w=6):
    return {
        "type": "stat",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 4, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {
            "reduceOptions": {"calcs": ["lastNotNull"]},
            "colorMode": "value",
            "graphMode": "none",
        },
        "fieldConfig": {
            "defaults": {"color": {"fixedColor": color, "mode": "fixed"}},
            "overrides": [],
        },
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _timeseries(title, sql_approved, sql_blocked, grid_y, sql_waived=None):
    overrides = [
        {
            "matcher": {"id": "byName", "options": "approved"},
            "properties": [{"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}],
        },
        {
            "matcher": {"id": "byName", "options": "blocked"},
            "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}],
        },
    ]
    if sql_waived is not None:
        overrides.append({
            "matcher": {"id": "byName", "options": "waived"},
            "properties": [{"id": "color", "value": {"fixedColor": "#d29922", "mode": "fixed"}}],
        })
    targets = [
        {"datasource": DS_REF, "rawSql": sql_approved, "format": "time_series", "refId": "A"},
        {"datasource": DS_REF, "rawSql": sql_blocked,  "format": "time_series", "refId": "B"},
    ]
    if sql_waived is not None:
        targets.append({"datasource": DS_REF, "rawSql": sql_waived, "format": "time_series", "refId": "C"})
    return {
        "type": "timeseries",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": 24, "x": 0, "y": grid_y},
        "options": {
            "tooltip": {"mode": "multi"},
            "legend": {"displayMode": "list", "placement": "bottom"},
        },
        "fieldConfig": {
            "defaults": {"custom": {"lineWidth": 2, "fillOpacity": 10}},
            "overrides": overrides,
        },
        "targets": targets,
    }


def _table(title, sql, grid_y, grid_x=0, grid_w=12, field_overrides=None):
    return {
        "type": "table",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {"showHeader": True},
        "fieldConfig": {"defaults": {}, "overrides": field_overrides or []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _pie(title, sql, grid_y, grid_x=12, grid_w=12):
    return {
        "type": "piechart",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {
            "pieType": "pie",
            "displayLabels": ["name", "percent", "value"],
            "tooltip": {"mode": "single"},
            "legend": {
                "displayMode": "table",
                "placement": "right",
                "values": ["value", "percent"],
            },
        },
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _barchart(title, sql, grid_y, grid_x=0, grid_w=12, orientation="auto"):
    return {
        "type": "barchart",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {
            "orientation": orientation,
            "legend": {"displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi"},
        },
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _var(name, label, query, current=None):
    if current is None:
        current = {"selected": True, "text": "All", "value": "All"}
    return {
        "name": name,
        "label": label,
        "type": "query",
        "datasource": DS_REF,
        "query": query,
        "includeAll": False,
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": current,
    }


def _dashboard(title, uid, panels, variables):
    for i, panel in enumerate(panels, start=1):
        panel["id"] = i
    return {
        "__inputs": [
            {"name": "DS_POSTGRESQL", "label": "PostgreSQL", "type": "datasource", "pluginId": "postgres"}
        ],
        "__elements": {},
        "__requires": [{"type": "datasource", "id": "postgres", "name": "PostgreSQL"}],
        "annotations": {"list": []},
        "editable": True,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": panels,
        "refresh": "1h",
        "schemaVersion": 38,
        "tags": ["curation", "jfrog"],
        "templating": {"list": variables},
        "time": {"from": "now-30d", "to": "now"},
        "timepicker": {},
        "timezone": "browser",
        "title": title,
        "uid": uid,
        "version": 1,
    }


# ── SQL helpers ─────────────────────────────────────────────────────────────

def _where(dry_run_flag, extra_filters="", include_repo_filter=True, include_user_filter=True,
           include_instance_filter=True):
    tf       = "$__timeFilter(created_at)"
    pt       = "('$package_type'    = ANY(ARRAY['', 'All']) OR package_type             = '$package_type')"
    repo     = "('$repository'      = ANY(ARRAY['', 'All']) OR curated_repository_name  = '$repository')"
    instance = "('$jfrog_instance'  = ANY(ARRAY['', 'All']) OR jfrog_instance           = '$jfrog_instance')"
    user     = "('$username'        = ANY(ARRAY['', 'All']) OR username                 = '$username')"
    parts = [f"WHERE is_dry_run = {dry_run_flag}", f"AND {tf}", f"AND {pt}"]
    if include_repo_filter:
        parts.append(f"AND {repo}")
    if include_instance_filter:
        parts.append(f"AND {instance}")
    if include_user_filter:
        parts.append(f"AND {user}")
    if extra_filters:
        parts.append(extra_filters)
    return " ".join(parts)


def _trend_sql(dry_run_flag, action, include_repo_filter=True):
    w = _where(dry_run_flag, extra_filters=f"AND action = '{action}'", include_repo_filter=include_repo_filter)
    return f"""SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS {action}
FROM audit_events
{w}
GROUP BY 1
ORDER BY 1"""


# ── Real Events dashboard ────────────────────────────────────────────────────

def real_events():
    w          = _where("false")
    w_blocked  = _where("false", extra_filters="AND action = 'blocked'")
    w_approved = _where("false", extra_filters="AND action = 'approved'")
    w_waived   = _where("false", extra_filters="AND action = 'waived'")
    wj = (
        "WHERE ae.is_dry_run = false"
        " AND $__timeFilter(ae.created_at)"
        " AND ('$package_type'   = ANY(ARRAY['', 'All']) OR ae.package_type            = '$package_type')"
        " AND ('$repository'     = ANY(ARRAY['', 'All']) OR ae.curated_repository_name = '$repository')"
        " AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR ae.jfrog_instance          = '$jfrog_instance')"
        " AND ('$username'       = ANY(ARRAY['', 'All']) OR ae.username                = '$username')"
    )

    panels = [
        # ── Stats row (6 × w=4) ────────────────────────────────────────────
        _stat("Total Events",
              f"SELECT COUNT(*) FROM audit_events {w}",
              "blue",   0,  0, grid_w=4),
        _stat("% Blocked",
              f"SELECT ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)"
              f" / NULLIF(COUNT(*), 0), 1) AS pct_blocked FROM audit_events {w}",
              "orange", 4,  0, grid_w=4),
        _stat("Blocked",
              f"SELECT COUNT(*) FROM audit_events {w_blocked}",
              "red",    8,  0, grid_w=4),
        _stat("Approved",
              f"SELECT COUNT(*) FROM audit_events {w_approved}",
              "green",  12, 0, grid_w=4),
        _stat("Waived",
              f"SELECT COUNT(*) FROM audit_events {w_waived}",
              "#d29922", 16, 0, grid_w=4),
        _stat("Unique Packages",
              f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",
              "purple", 20, 0, grid_w=4),

        # ── Timeseries with waived ─────────────────────────────────────────
        _timeseries(
            "Blocked / Approved / Waived Over Time",
            _trend_sql("false", "approved"),
            _trend_sql("false", "blocked"),
            grid_y=4,
            sql_waived=_trend_sql("false", "waived"),
        ),

        # ── Ecosystem breakdown row (y=12) ─────────────────────────────────
        _barchart(
            "Approved / Blocked / Waived by Ecosystem",
            f"""SELECT
  package_type,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived
FROM audit_events
{w}
GROUP BY package_type
ORDER BY (SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END)) DESC""",
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _barchart(
            "% Blocked by Ecosystem",
            f"""SELECT
  package_type,
  ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1) AS pct_blocked
FROM audit_events
{w}
GROUP BY package_type
ORDER BY pct_blocked DESC""",
            grid_y=12, grid_x=12, grid_w=12, orientation="horizontal",
        ),

        # ── Condition analysis row (y=20) ──────────────────────────────────
        _table(
            "Top Blocked Packages",
            f"""SELECT
  package_name,
  package_type,
  COUNT(*) AS blocked_count,
  MAX(reason) AS last_reason
FROM audit_events
{w_blocked}
GROUP BY package_name, package_type
ORDER BY blocked_count DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=8,
        ),
        _pie(
            "Blocked by Condition Category",
            f"""SELECT
  COALESCE(ep.condition_category, 'N/A') AS condition_category,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_category != '$exclude_condition_category'
       OR '$exclude_condition_category' = '')
GROUP BY ep.condition_category
ORDER BY count DESC""",
            grid_y=20, grid_x=8, grid_w=8,
        ),
        _pie(
            "Blocked by Condition Name",
            f"""SELECT
  COALESCE(ep.condition_name, 'N/A') AS condition_name,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_name != '$exclude_condition_name'
       OR '$exclude_condition_name' = '')
GROUP BY ep.condition_name
ORDER BY count DESC""",
            grid_y=20, grid_x=16, grid_w=8,
        ),

        # ── Policy / waived / user-activity row (y=28) ────────────────────
        _table(
            "Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=28, grid_x=0, grid_w=8,
        ),
        _pie(
            "Waived by Ecosystem",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w_waived}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=28, grid_x=8, grid_w=8,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=28, grid_x=16, grid_w=8,
            field_overrides=[{
                "matcher": {"id": "byName", "options": "username"},
                "properties": [{
                    "id": "links",
                    "value": [{
                        "title": "Drill down to user",
                        "url": "/d/${__dashboard.uid}?${__url_time_range}&var-package_type=${package_type}&var-repository=${repository}&var-jfrog_instance=${jfrog_instance}&var-username=${__data.fields.username}",
                        "targetBlank": False,
                    }],
                }],
            }],
        ),

        # ── 12-hour window analysis (existing, pushed to y=36/44) ──────────
        _stat(
            "High-Persistence Users",
            """SELECT COUNT(DISTINCT username)
FROM (
  SELECT username,
    SUM(is_window_start) AS sessions
  FROM mv_download_windows
  WHERE is_dry_run = false AND action = 'blocked'
    AND $__timeFilter(created_at)
    AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type            = '$package_type')
    AND ('$repository'     = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
    AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance          = '$jfrog_instance')
    AND ('$username'       = ANY(ARRAY['', 'All']) OR username                = '$username')
  GROUP BY username, package_name
  HAVING SUM(is_window_start) >= 3
) sub""",
            "orange", 0, 36,
        ),
        _table(
            "Persistent Blocked Packages",
            """SELECT
  package_name,
  package_type,
  username,
  jfrog_instance,
  SUM(is_window_start) AS unique_sessions,
  COUNT(*) AS total_events,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'blocked'
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type            = '$package_type')
  AND ('$repository'     = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance          = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username                = '$username')
GROUP BY package_name, package_type, username, jfrog_instance
HAVING SUM(is_window_start) > 1
ORDER BY unique_sessions DESC
LIMIT 20""",
            grid_y=36, grid_x=6, grid_w=18,
        ),
        _timeseries(
            "Download Sessions Over Time",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS approved
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'approved'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type            = '$package_type')
  AND ('$repository'     = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance          = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username                = '$username')
GROUP BY 1
ORDER BY 1""",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS blocked
FROM mv_download_windows
WHERE is_dry_run = false AND action = 'blocked'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type            = '$package_type')
  AND ('$repository'     = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance          = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username                = '$username')
GROUP BY 1
ORDER BY 1""",
            grid_y=44,
        ),

        # ── User Events Log (y=52) ─────────────────────────────────────────
        _table(
            "User Events Log",
            f"""SELECT
  created_at,
  action,
  package_name,
  package_type,
  package_version,
  reason,
  curated_repository_name
FROM audit_events
{w}
ORDER BY created_at DESC
LIMIT 100""",
            grid_y=52, grid_x=0, grid_w=24,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "repository", "Repository",
            "SELECT 'All' AS curated_repository_name UNION SELECT DISTINCT curated_repository_name"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "jfrog_instance", "Instance",
            "SELECT 'All' AS jfrog_instance UNION SELECT DISTINCT jfrog_instance"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "username", "User",
            "SELECT 'All' AS username UNION SELECT DISTINCT username"
            " FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "exclude_condition_category", "Exclude Condition Category",
            "SELECT '' AS condition_category UNION SELECT DISTINCT condition_category"
            " FROM event_policies WHERE condition_category IS NOT NULL ORDER BY 1",
            current={"selected": True, "text": "", "value": ""},
        ),
        _var(
            "exclude_condition_name", "Exclude Condition Name",
            "SELECT '' AS condition_name UNION SELECT DISTINCT condition_name"
            " FROM event_policies WHERE condition_name IS NOT NULL ORDER BY 1",
            current={"selected": True, "text": "", "value": ""},
        ),
    ]

    return _dashboard("Curation Audit \u2014 Real Events", "curation-real-events", panels, variables)


# ── Dry Run dashboard ────────────────────────────────────────────────────────

def dry_run():
    w          = _where("true", include_repo_filter=False)
    w_blocked  = _where("true", extra_filters="AND action = 'blocked'", include_repo_filter=False)
    w_approved = _where("true", extra_filters="AND action = 'approved'", include_repo_filter=False)
    w_waived   = _where("true", extra_filters="AND action = 'waived'",  include_repo_filter=False)
    wj = (
        "WHERE ae.is_dry_run = true"
        " AND $__timeFilter(ae.created_at)"
        " AND ('$package_type'   = ANY(ARRAY['', 'All']) OR ae.package_type   = '$package_type')"
        " AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR ae.jfrog_instance = '$jfrog_instance')"
        " AND ('$username'       = ANY(ARRAY['', 'All']) OR ae.username        = '$username')"
    )

    panels = [
        # ── Stats row (6 × w=4) ────────────────────────────────────────────
        _stat("Total Dry-Run Events",
              f"SELECT COUNT(*) FROM audit_events {w}",
              "blue",    0,  0, grid_w=4),
        _stat("% Would-Be Blocked",
              f"SELECT ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)"
              f" / NULLIF(COUNT(*), 0), 1) AS pct_blocked FROM audit_events {w}",
              "orange",  4,  0, grid_w=4),
        _stat("Would-Be Blocked",
              f"SELECT COUNT(*) FROM audit_events {w_blocked}",
              "red",     8,  0, grid_w=4),
        _stat("Would-Be Approved",
              f"SELECT COUNT(*) FROM audit_events {w_approved}",
              "green",   12, 0, grid_w=4),
        _stat("Would-Be Waived",
              f"SELECT COUNT(*) FROM audit_events {w_waived}",
              "#d29922", 16, 0, grid_w=4),
        _stat("Unique Packages",
              f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",
              "purple",  20, 0, grid_w=4),

        # ── Timeseries with waived ─────────────────────────────────────────
        _timeseries(
            "Would-Be Blocked / Approved / Waived Over Time",
            _trend_sql("true", "approved", include_repo_filter=False),
            _trend_sql("true", "blocked",  include_repo_filter=False),
            grid_y=4,
            sql_waived=_trend_sql("true", "waived", include_repo_filter=False),
        ),

        # ── Ecosystem breakdown row (y=12) ─────────────────────────────────
        _barchart(
            "Would-Be Approved / Blocked / Waived by Ecosystem",
            f"""SELECT
  package_type,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived
FROM audit_events
{w}
GROUP BY package_type
ORDER BY (SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END)
        + SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END)) DESC""",
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _barchart(
            "% Would-Be Blocked by Ecosystem",
            f"""SELECT
  package_type,
  ROUND(100.0 * SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1) AS pct_blocked
FROM audit_events
{w}
GROUP BY package_type
ORDER BY pct_blocked DESC""",
            grid_y=12, grid_x=12, grid_w=12, orientation="horizontal",
        ),

        # ── Condition analysis row (y=20) ──────────────────────────────────
        _table(
            "Top Would-Be Blocked Packages",
            f"""SELECT
  package_name,
  package_type,
  COUNT(*) AS blocked_count,
  MAX(reason) AS last_reason
FROM audit_events
{w_blocked}
GROUP BY package_name, package_type
ORDER BY blocked_count DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=8,
        ),
        _pie(
            "Would-Be Blocked by Condition Category",
            f"""SELECT
  COALESCE(ep.condition_category, 'N/A') AS condition_category,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_category != '$exclude_condition_category'
       OR '$exclude_condition_category' = '')
GROUP BY ep.condition_category
ORDER BY count DESC""",
            grid_y=20, grid_x=8, grid_w=8,
        ),
        _pie(
            "Would-Be Blocked by Condition Name",
            f"""SELECT
  COALESCE(ep.condition_name, 'N/A') AS condition_name,
  COUNT(*) AS count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
  AND ae.action = 'blocked'
  AND (ep.condition_name != '$exclude_condition_name'
       OR '$exclude_condition_name' = '')
GROUP BY ep.condition_name
ORDER BY count DESC""",
            grid_y=20, grid_x=16, grid_w=8,
        ),

        # ── Policy / waived / user-activity row (y=28) ────────────────────
        _table(
            "Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
{wj}
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=28, grid_x=0, grid_w=8,
        ),
        _pie(
            "Would-Be Waived by Ecosystem",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w_waived}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=28, grid_x=8, grid_w=8,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked'  THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count,
  SUM(CASE WHEN action = 'waived'   THEN 1 ELSE 0 END) AS waived_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=28, grid_x=16, grid_w=8,
            field_overrides=[{
                "matcher": {"id": "byName", "options": "username"},
                "properties": [{
                    "id": "links",
                    "value": [{
                        "title": "Drill down to user",
                        "url": "/d/${__dashboard.uid}?${__url_time_range}&var-package_type=${package_type}&var-jfrog_instance=${jfrog_instance}&var-username=${__data.fields.username}",
                        "targetBlank": False,
                    }],
                }],
            }],
        ),

        # ── 12-hour window analysis (existing, pushed to y=36/44) ──────────
        _stat(
            "High-Persistence Users",
            """SELECT COUNT(DISTINCT username)
FROM (
  SELECT username,
    SUM(is_window_start) AS sessions
  FROM mv_download_windows
  WHERE is_dry_run = true AND action = 'blocked'
    AND $__timeFilter(created_at)
    AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type   = '$package_type')
    AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance = '$jfrog_instance')
    AND ('$username'       = ANY(ARRAY['', 'All']) OR username       = '$username')
  GROUP BY username, package_name
  HAVING SUM(is_window_start) >= 3
) sub""",
            "orange", 0, 36,
        ),
        _table(
            "Persistent Blocked Packages",
            """SELECT
  package_name,
  package_type,
  username,
  jfrog_instance,
  SUM(is_window_start) AS unique_sessions,
  COUNT(*) AS total_events,
  MIN(created_at) AS first_seen,
  MAX(created_at) AS last_seen
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'blocked'
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type   = '$package_type')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username       = '$username')
GROUP BY package_name, package_type, username, jfrog_instance
HAVING SUM(is_window_start) > 1
ORDER BY unique_sessions DESC
LIMIT 20""",
            grid_y=36, grid_x=6, grid_w=18,
        ),
        _timeseries(
            "Download Sessions Over Time",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS approved
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'approved'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type   = '$package_type')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username       = '$username')
GROUP BY 1
ORDER BY 1""",
            """SELECT
  $__timeGroupAlias(created_at,'1d'),
  COUNT(*) AS blocked
FROM mv_download_windows
WHERE is_dry_run = true AND action = 'blocked'
  AND is_window_start = 1
  AND $__timeFilter(created_at)
  AND ('$package_type'   = ANY(ARRAY['', 'All']) OR package_type   = '$package_type')
  AND ('$jfrog_instance' = ANY(ARRAY['', 'All']) OR jfrog_instance = '$jfrog_instance')
  AND ('$username'       = ANY(ARRAY['', 'All']) OR username       = '$username')
GROUP BY 1
ORDER BY 1""",
            grid_y=44,
        ),

        # ── User Events Log (y=52) ─────────────────────────────────────────
        _table(
            "User Events Log (Dry Run)",
            f"""SELECT
  created_at,
  action,
  package_name,
  package_type,
  package_version,
  reason,
  curated_repository_name
FROM audit_events
{w}
ORDER BY created_at DESC
LIMIT 100""",
            grid_y=52, grid_x=0, grid_w=24,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type"
            " FROM audit_events WHERE is_dry_run = true ORDER BY 1",
        ),
        _var(
            "jfrog_instance", "Instance",
            "SELECT 'All' AS jfrog_instance UNION SELECT DISTINCT jfrog_instance"
            " FROM audit_events WHERE is_dry_run = true ORDER BY 1",
        ),
        _var(
            "username", "User",
            "SELECT 'All' AS username UNION SELECT DISTINCT username"
            " FROM audit_events WHERE is_dry_run = true ORDER BY 1",
        ),
        _var(
            "exclude_condition_category", "Exclude Condition Category",
            "SELECT '' AS condition_category UNION SELECT DISTINCT condition_category"
            " FROM event_policies WHERE condition_category IS NOT NULL ORDER BY 1",
            current={"selected": True, "text": "", "value": ""},
        ),
        _var(
            "exclude_condition_name", "Exclude Condition Name",
            "SELECT '' AS condition_name UNION SELECT DISTINCT condition_name"
            " FROM event_policies WHERE condition_name IS NOT NULL ORDER BY 1",
            current={"selected": True, "text": "", "value": ""},
        ),
    ]

    return _dashboard("Curation Audit \u2014 Dry Run", "curation-dry-run", panels, variables)


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    for filename, dash in [("real-events.json", real_events()), ("dry-run.json", dry_run())]:
        path = os.path.join(OUT_DIR, filename)
        with open(path, "w") as f:
            json.dump(dash, f, indent=2)
        print(f"Written: {path}")
