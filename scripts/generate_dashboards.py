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


def _stat(title, sql, color, grid_x, grid_y):
    return {
        "type": "stat",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 4, "w": 6, "x": grid_x, "y": grid_y},
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


def _timeseries(title, sql_approved, sql_blocked, grid_y):
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
            "overrides": [
                {
                    "matcher": {"id": "byName", "options": "approved"},
                    "properties": [{"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}],
                },
                {
                    "matcher": {"id": "byName", "options": "blocked"},
                    "properties": [{"id": "color", "value": {"fixedColor": "red", "mode": "fixed"}}],
                },
            ],
        },
        "targets": [
            {"datasource": DS_REF, "rawSql": sql_approved, "format": "time_series", "refId": "A"},
            {"datasource": DS_REF, "rawSql": sql_blocked, "format": "time_series", "refId": "B"},
        ],
    }


def _table(title, sql, grid_y, grid_x=0, grid_w=12):
    return {
        "type": "table",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": grid_w, "x": grid_x, "y": grid_y},
        "options": {"showHeader": True},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _pie(title, sql, grid_y, grid_x=12):
    return {
        "type": "piechart",
        "title": title,
        "datasource": DS_REF,
        "gridPos": {"h": 8, "w": 12, "x": grid_x, "y": grid_y},
        "options": {"pieType": "pie", "legend": {"displayMode": "table", "placement": "right"}},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "targets": [{"datasource": DS_REF, "rawSql": sql, "format": "table", "refId": "A"}],
    }


def _var(name, label, query):
    return {
        "name": name,
        "label": label,
        "type": "query",
        "datasource": DS_REF,
        "query": {"datasource": DS_REF, "rawSql": query, "format": "table"},
        "includeAll": False,
        "multi": False,
        "refresh": 2,
        "sort": 1,
        "current": {"selected": True, "text": "All", "value": "All"},
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

def _where(dry_run_flag, extra_filters="", include_repo_filter=True):
    tf = "$__timeFilter(created_at)"
    pt = "('$package_type' = ANY(ARRAY['', 'All']) OR package_type = '$package_type')"
    repo = "('$repository' = ANY(ARRAY['', 'All']) OR curated_repository_name = '$repository')"
    parts = [f"WHERE is_dry_run = {dry_run_flag}", f"AND {tf}", f"AND {pt}"]
    if include_repo_filter:
        parts.append(f"AND {repo}")
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
    w = _where("false")
    w_blocked = _where("false", extra_filters="AND action = 'blocked'")
    w_approved = _where("false", extra_filters="AND action = 'approved'")

    panels = [
        _stat("Total Events",    f"SELECT COUNT(*) FROM audit_events {w}",                        "blue",   0,  0),
        _stat("Blocked",         f"SELECT COUNT(*) FROM audit_events {w_blocked}",                "red",    6,  0),
        _stat("Approved",        f"SELECT COUNT(*) FROM audit_events {w_approved}",               "green",  12, 0),
        _stat("Unique Packages", f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",    "purple", 18, 0),
        _timeseries(
            "Blocked vs Approved Over Time",
            _trend_sql("false", "approved"),
            _trend_sql("false", "blocked"),
            grid_y=4,
        ),
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
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _table(
            "Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
WHERE ae.is_dry_run = false AND $__timeFilter(ae.created_at)
AND ('$package_type' = ANY(ARRAY['', 'All']) OR ae.package_type = '$package_type')
AND ('$repository' = ANY(ARRAY['', 'All']) OR ae.curated_repository_name = '$repository')
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=12, grid_x=12, grid_w=12,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=12,
        ),
        _pie(
            "Package Type Distribution",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=20, grid_x=12,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
        _var(
            "repository", "Repository",
            "SELECT 'All' AS curated_repository_name UNION SELECT DISTINCT curated_repository_name FROM audit_events WHERE is_dry_run = false ORDER BY 1",
        ),
    ]

    return _dashboard("Curation Audit \u2014 Real Events", "curation-real-events", panels, variables)


# ── Dry Run dashboard ────────────────────────────────────────────────────────

def dry_run():
    w = _where("true", include_repo_filter=False)
    w_blocked = _where("true", extra_filters="AND action = 'blocked'", include_repo_filter=False)
    w_approved = _where("true", extra_filters="AND action = 'approved'", include_repo_filter=False)

    panels = [
        _stat("Total Dry-Run Events",  f"SELECT COUNT(*) FROM audit_events {w}",                        "blue",   0,  0),
        _stat("Would Be Blocked",      f"SELECT COUNT(*) FROM audit_events {w_blocked}",                "red",    6,  0),
        _stat("Would Be Approved",     f"SELECT COUNT(*) FROM audit_events {w_approved}",               "green",  12, 0),
        _stat("Unique Packages",       f"SELECT COUNT(DISTINCT package_name) FROM audit_events {w}",    "purple", 18, 0),
        _timeseries(
            "Simulated Blocked vs Approved Over Time",
            _trend_sql("true", "approved", include_repo_filter=False),
            _trend_sql("true", "blocked", include_repo_filter=False),
            grid_y=4,
        ),
        _table(
            "Top Would-Be Blocked Packages",
            f"""SELECT
  package_name,
  package_type,
  COUNT(*) AS block_count
FROM audit_events
{w_blocked}
GROUP BY package_name, package_type
ORDER BY block_count DESC
LIMIT 20""",
            grid_y=12, grid_x=0, grid_w=12,
        ),
        _table(
            "Dry-Run Policy Breakdown",
            f"""SELECT
  ep.policy_name,
  COUNT(*) AS triggered_count
FROM audit_events ae
JOIN event_policies ep ON ae.id = ep.event_id
WHERE ae.is_dry_run = true AND $__timeFilter(ae.created_at)
AND ('$package_type' = ANY(ARRAY['', 'All']) OR ae.package_type = '$package_type')
GROUP BY ep.policy_name
ORDER BY triggered_count DESC""",
            grid_y=12, grid_x=12, grid_w=12,
        ),
        _table(
            "User Activity",
            f"""SELECT
  username,
  COUNT(*) AS total_events,
  SUM(CASE WHEN action = 'blocked' THEN 1 ELSE 0 END) AS blocked_count,
  SUM(CASE WHEN action = 'approved' THEN 1 ELSE 0 END) AS approved_count
FROM audit_events
{w}
GROUP BY username
ORDER BY total_events DESC
LIMIT 20""",
            grid_y=20, grid_x=0, grid_w=12,
        ),
        _pie(
            "Package Type Distribution",
            f"""SELECT
  package_type,
  COUNT(*) AS count
FROM audit_events
{w}
GROUP BY package_type
ORDER BY count DESC""",
            grid_y=20, grid_x=12,
        ),
    ]

    variables = [
        _var(
            "package_type", "Package Type",
            "SELECT 'All' AS package_type UNION SELECT DISTINCT package_type FROM audit_events WHERE is_dry_run = true ORDER BY 1",
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
